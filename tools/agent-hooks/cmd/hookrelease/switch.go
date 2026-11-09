package main

import (
	"crypto/rand"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"runtime"
	"strings"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/logsink"
)

var (
	homeKey    = regexp.MustCompile(`^[a-z0-9-]+$`)
	releaseDir = regexp.MustCompile(`^[0-9a-f]{16}$`)
)

func switchCommand(args []string) (string, error) {
	if runtime.GOOS == "windows" {
		return "", errors.New("switch is not wired on Windows in PR 3")
	}
	flags := flag.NewFlagSet("switch", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	var root, home string
	flags.StringVar(&root, "root", "", "agent-hooks data root")
	flags.StringVar(&home, "home", "", "home key")
	if err := flags.Parse(args); err != nil {
		return "", err
	}
	if flags.NArg() != 1 || !homeKey.MatchString(home) {
		return "", errors.New("usage: hookrelease switch --home KEY [--root DIR] PATH; KEY uses lowercase ASCII letters, digits, and -")
	}
	if root == "" {
		var err error
		root, err = dataRoot()
		if err != nil {
			return "", err
		}
	}
	root, err := filepath.Abs(root)
	if err != nil {
		return "", err
	}
	// Sync, uninstall, install, and gc take the same lock, and a change they
	// left unfinished is theirs to finish or restore first.
	state, err := switchState()
	if err != nil {
		return "", err
	}
	lock, err := takeSwitchLock(systemDisk{}, state, os.Args)
	if err != nil {
		return "", err
	}
	defer lock.release()
	pending, err := filepath.Glob(filepath.Join(state, "switch-*.json"))
	if err != nil {
		return "", err
	}
	if len(pending) > 0 {
		return "", fmt.Errorf("a registration change is unfinished (%s); run just sync-agents to finish or restore it first", strings.Join(pending, ", "))
	}
	return switchLink(systemDisk{}, root, home, flags.Arg(0))
}

// switchState is <state>/dotfiles/agent-hooks, the directory of the lock and
// the journals: the file log's state directory (logsink.Base).
func switchState() (string, error) {
	base, ok := logsink.Base(os.LookupEnv)
	if !ok {
		return "", errors.New("no state directory: XDG_STATE_HOME or HOME must be an absolute path")
	}
	return filepath.Join(base, "dotfiles", "agent-hooks"), nil
}

// switchLink points root's current/<home>/agent-hook at the release target
// names, resolved: a new symlink under a temporary name, renamed over the old
// one. It syncs the parent of each directory it makes, and the link's
// directory after the rename, so the link reaches the disk named. It returns
// the old target, or "" when there was none.
func switchLink(disk releaseDisk, root, home, target string) (string, error) {
	target, err := filepath.Abs(target)
	if err != nil {
		return "", err
	}
	target, err = filepath.EvalSymlinks(target)
	if err != nil {
		return "", err
	}
	if err := isRelease(root, target); err != nil {
		return "", err
	}
	dir := filepath.Join(root, "current", home)
	if err := makeDirectories(disk, dir, 0o755); err != nil {
		return "", err
	}
	link := filepath.Join(dir, "agent-hook")
	previous, err := os.Readlink(link)
	if err != nil && !errors.Is(err, os.ErrNotExist) {
		return "", err
	}
	tmp := filepath.Join(dir, ".agent-hook-"+rand.Text())
	if err := os.Symlink(target, tmp); err != nil {
		return "", err
	}
	defer os.Remove(tmp)
	if err := disk.Rename(tmp, link); err != nil {
		return "", err
	}
	if err := disk.SyncDirectory(dir); err != nil {
		return "", err
	}
	return previous, nil
}

// makeDirectories makes path and its missing parents one level at a time,
// and syncs the parent of each directory it makes, so each new name reaches
// the disk before anything is put in it.
func makeDirectories(disk releaseDisk, path string, mode os.FileMode) error {
	var missing []string
	for dir := path; ; dir = filepath.Dir(dir) {
		_, err := os.Lstat(dir)
		if err == nil {
			break
		}
		if !errors.Is(err, os.ErrNotExist) {
			return err
		}
		missing = append(missing, dir)
		if filepath.Dir(dir) == dir {
			break
		}
	}
	for i := len(missing) - 1; i >= 0; i-- {
		if err := os.Mkdir(missing[i], mode); err != nil && !errors.Is(err, os.ErrExist) {
			return err
		}
		if err := disk.SyncDirectory(filepath.Dir(missing[i])); err != nil {
			return err
		}
	}
	return nil
}

// isRelease checks that target is one of root's releases: a regular file
// named agent-hook in <root>/releases/<16 lowercase hex>/. A home's link
// may name nothing else, since the registrations run what it names.
func isRelease(root, target string) error {
	stat, err := os.Lstat(target)
	if err != nil {
		return err
	}
	if !stat.Mode().IsRegular() || filepath.Base(target) != "agent-hook" {
		return fmt.Errorf("not a release binary: %s", target)
	}
	dir := filepath.Dir(target)
	if !releaseDir.MatchString(filepath.Base(dir)) {
		return fmt.Errorf("not in a release directory: %s", target)
	}
	resolvedRoot, err := filepath.EvalSymlinks(root)
	if err != nil {
		return err
	}
	releases := filepath.Join(resolvedRoot, "releases")
	if filepath.Dir(dir) != releases {
		return fmt.Errorf("not one of %s's releases: %s", releases, target)
	}
	return nil
}
