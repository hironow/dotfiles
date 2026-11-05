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
	flags.StringVar(&root, "into", "", "agent-hooks data root")
	flags.StringVar(&home, "home", "", "home key")
	if err := flags.Parse(args); err != nil {
		return "", err
	}
	if flags.NArg() != 1 || !homeKey.MatchString(home) {
		return "", errors.New("usage: hookrelease switch --home KEY [--into DIR] PATH; KEY uses lowercase ASCII letters, digits, and -")
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
	target, err := filepath.Abs(flags.Arg(0))
	if err != nil {
		return "", err
	}
	if err := isRelease(root, target); err != nil {
		return "", err
	}
	dir := filepath.Join(root, "current", home)
	if err := os.MkdirAll(dir, 0o755); err != nil {
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
	if err := os.Rename(tmp, link); err != nil {
		return "", err
	}
	return previous, nil
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
	releases, err := filepath.EvalSymlinks(filepath.Join(root, "releases"))
	if err != nil {
		return err
	}
	parent, err := filepath.EvalSymlinks(filepath.Dir(dir))
	if err != nil {
		return err
	}
	if parent != releases {
		return fmt.Errorf("not one of %s's releases: %s", releases, target)
	}
	return nil
}
