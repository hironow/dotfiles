package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"runtime"
	"strings"

	"github.com/goccy/go-json/jsontext"
	json "github.com/goccy/go-json/v2"
)

type goTool struct {
	dir string
	env []string
}

func (g goTool) run(download bool, args ...string) ([]byte, error) {
	// Audited: go is the user's toolchain on PATH. Arguments are fixed here
	// or are target/output values passed directly, without a shell.
	cmd := exec.Command("go", args...) //nolint:gosec // G204: audited above
	cmd.Dir = g.dir
	cmd.Env = append([]string{}, g.env...)
	if !download {
		cmd.Env = append(cmd.Env, "GOPROXY=off")
	}
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	out, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("go %s: %w: %s", strings.Join(args, " "), err, stderr.String())
	}
	return out, nil
}

type releasePlan struct {
	goTool
	target              buildTarget
	version, module, id string
}

func prepareRelease(target buildTarget) (releasePlan, error) {
	return prepareReleaseInCache(target, "")
}

func prepareReleaseInCache(target buildTarget, cache string) (releasePlan, error) {
	plan := releasePlan{target: target}
	dir, err := os.Getwd()
	if err != nil {
		return plan, err
	}
	dir, err = filepath.EvalSymlinks(dir)
	if err != nil {
		return plan, err
	}
	plan.goTool = goTool{dir: dir, env: normalizedEnvironment(userCacheEnvironment(dir), target, runtime.GOOS)}
	if cache != "" {
		plan.env = append(plan.env, "GOCACHE="+cache)
	}
	out, err := plan.run(false, "env", "-json", "GOVERSION", "GOCACHE", "GOMODCACHE", "GOPATH")
	if err != nil {
		return plan, err
	}
	var settings map[string]string
	if err := json.Unmarshal(out, &settings); err != nil {
		return plan, fmt.Errorf("decode go env: %w", err)
	}
	plan.version = settings["GOVERSION"]
	for _, key := range []string{"GOCACHE", "GOMODCACHE", "GOPATH"} {
		plan.env = append(plan.env, key+"="+settings[key])
	}
	if err := plan.readModule(); err != nil {
		return plan, err
	}
	if _, err := plan.run(true, "mod", "download"); err != nil {
		return plan, err
	}
	if _, err := plan.run(false, "mod", "verify"); err != nil {
		return plan, err
	}
	files, err := plan.inputs()
	if err != nil {
		return plan, err
	}
	plan.id = releaseID(plan.version, target, plan.module, files)
	return plan, nil
}

func userCacheEnvironment(dir string) []string {
	user := os.Environ()
	keys := []string{"GOCACHE", "GOMODCACHE", "GOPATH"}
	missing := false
	for _, key := range keys {
		missing = missing || os.Getenv(key) == ""
	}
	if !missing {
		return user
	}
	// Read the user's cache locations before dropping their Go settings.
	// Keep the lookup local, even with a different toolchain configured.
	plain := goTool{dir: dir, env: append(append([]string{}, user...), "GOTOOLCHAIN=local")}
	out, err := plain.run(false, "env", "-json", "GOCACHE", "GOMODCACHE", "GOPATH")
	var caches map[string]string
	if err != nil || json.Unmarshal(out, &caches) != nil {
		return user // A polluted environment may prevent this optional lookup.
	}
	for _, key := range keys {
		if os.Getenv(key) == "" && caches[key] != "" {
			user = append(user, key+"="+caches[key])
		}
	}
	return user
}

func (p *releasePlan) readModule() error {
	out, err := p.run(false, "mod", "edit", "-json")
	if err != nil {
		return err
	}
	var module struct {
		Module  struct{ Path string }
		Replace []jsontext.Value
	}
	if err := json.Unmarshal(out, &module); err != nil {
		return fmt.Errorf("decode go.mod: %w", err)
	}
	if len(module.Replace) != 0 {
		return errors.New("go.mod replace directives are not allowed in a release")
	}
	p.module = module.Module.Path
	return nil
}

type listedPackage struct {
	Dir                                                                 string
	Module                                                              *struct{ Main bool }
	GoFiles, SFiles, HFiles, SysoFiles, EmbedFiles                      []string
	CgoFiles, CFiles, CXXFiles, MFiles, FFiles, SwigFiles, SwigCXXFiles []string
}

func (g goTool) packages() ([]listedPackage, error) {
	out, err := g.run(false, "list", "-deps", "-json", "./cmd/agent-hook")
	if err != nil {
		return nil, err
	}
	var packages []listedPackage
	decoder := jsontext.NewDecoder(bytes.NewReader(out))
	for {
		var pkg listedPackage
		if err := json.UnmarshalDecode(decoder, &pkg); errors.Is(err, io.EOF) {
			break
		} else if err != nil {
			return nil, fmt.Errorf("decode go list: %w", err)
		}
		if pkg.Module != nil && pkg.Module.Main {
			packages = append(packages, pkg)
		}
	}
	return packages, nil
}

func (p releasePlan) inputs() ([]fileDigest, error) {
	if err := p.refuseForeignInputs(); err != nil {
		return nil, err
	}
	packages, err := p.packages()
	if err != nil {
		return nil, err
	}
	paths := map[string]bool{"go.mod": true, "go.sum": true}
	for _, pkg := range packages {
		for _, files := range [][]string{pkg.GoFiles, pkg.SFiles, pkg.HFiles, pkg.SysoFiles, pkg.EmbedFiles} {
			for _, file := range files {
				rel, err := filepath.Rel(p.dir, filepath.Join(pkg.Dir, file))
				if err != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) || filepath.IsAbs(rel) {
					return nil, fmt.Errorf("release input outside module: %s/%s", pkg.Dir, file)
				}
				paths[filepath.ToSlash(rel)] = true
			}
		}
	}
	var files []fileDigest
	for path := range paths {
		digest, err := fileSHA256(filepath.Join(p.dir, filepath.FromSlash(path)))
		if err != nil {
			return nil, err
		}
		files = append(files, fileDigest{Path: path, SHA256: digest})
	}
	return files, nil
}

func (p releasePlan) refuseForeignInputs() error {
	// go list drops C and Swig files when cgo is off. Inspect the same
	// dependencies with cgo enabled under the normalized target's tool tags.
	probe := p.goTool
	probe.env = append(append([]string{}, p.env...), "CGO_ENABLED=1")
	packages, err := probe.packages()
	if err != nil {
		return err
	}
	for _, pkg := range packages {
		for _, files := range [][]string{pkg.CgoFiles, pkg.CFiles, pkg.CXXFiles, pkg.MFiles, pkg.FFiles, pkg.SwigFiles, pkg.SwigCXXFiles} {
			if len(files) != 0 {
				return fmt.Errorf("unsupported C source files or related inputs in %s: %v", pkg.Dir, files)
			}
		}
	}
	return nil
}

func fileSHA256(path string) (string, error) {
	f, err := os.OpenInRoot(filepath.Dir(path), filepath.Base(path))
	if err != nil {
		return "", err
	}
	defer f.Close()
	hash := sha256.New()
	if _, err := io.Copy(hash, f); err != nil {
		return "", err
	}
	return hex.EncodeToString(hash.Sum(nil)), nil
}

func (p releasePlan) compile(path string) error {
	_, err := p.run(false, "build", "-trimpath", "-buildvcs=false", "-pgo=off", "-ldflags="+linkFlags(p.module, p.id), "-o", path, "./cmd/agent-hook")
	return err
}

// binaryName is the release binary's file name on target.
func binaryName(target buildTarget) string {
	if target.OS == "windows" {
		return "agent-hook.exe"
	}
	return "agent-hook"
}

// buildDirectory is the name os.MkdirTemp gives a build's temporary
// directory (buildPattern), and nothing else in a releases directory.
var buildDirectory = regexp.MustCompile(`^\.tmp-agent-hook-[0-9]+$`)

const buildPattern = ".tmp-agent-hook-*"

// build builds the host's release under the lock on releases, so builds of
// one directory run one at a time.
func (p releasePlan) build(releases string, stderr io.Writer) (string, error) {
	if p.target.OS != runtime.GOOS || p.target.Arch != runtime.GOARCH {
		return "", errors.New("build publishes only the host's release")
	}
	releases, err := filepath.Abs(releases)
	if err != nil {
		return "", err
	}
	lock, err := lockReleases(releases, stderr)
	if err != nil {
		return "", err
	}
	defer lock.release()
	if err := removeDeadBuilds(releases); err != nil {
		return "", err
	}
	tmp, err := os.MkdirTemp(releases, buildPattern)
	if err != nil {
		return "", err
	}
	defer os.RemoveAll(tmp)
	if err := os.Chmod(tmp, 0o755); err != nil {
		return "", err
	}
	path := filepath.Join(tmp, binaryName(p.target))
	if err := p.compile(path); err != nil {
		return "", err
	}
	if err := os.Chmod(path, 0o755); err != nil {
		return "", err
	}
	if err := verifyBuild(path, p.version, p.target); err != nil {
		return "", err
	}
	if err := p.ownChecks(path); err != nil {
		return "", err
	}
	return p.publish(systemDisk{}, tmp, releases)
}

func removeEmptyDirectories(paths []string) {
	for _, path := range paths {
		_ = os.Remove(path)
	}
}

// removeDeadBuilds removes every build directory in releases. The caller
// holds the lock, and a build holds it until it ends, so each one is what a
// killed build left, whatever its age.
func removeDeadBuilds(releases string) error {
	entries, err := os.ReadDir(releases)
	if err != nil {
		return err
	}
	for _, entry := range entries {
		if entry.IsDir() && buildDirectory.MatchString(entry.Name()) {
			if err := os.RemoveAll(filepath.Join(releases, entry.Name())); err != nil {
				return err
			}
		}
	}
	return nil
}

// makeReleaseParents records only directories this build created.
func makeReleaseParents(dir string) ([]string, error) {
	err := os.Mkdir(dir, 0o755)
	if err == nil {
		return []string{dir}, nil
	}
	if errors.Is(err, os.ErrExist) {
		return nil, nil
	}
	if !errors.Is(err, os.ErrNotExist) {
		return nil, err
	}
	parents, err := makeReleaseParents(filepath.Dir(dir))
	if err != nil {
		return nil, err
	}
	if err := os.Mkdir(dir, 0o755); err == nil {
		return append([]string{dir}, parents...), nil
	} else if !errors.Is(err, os.ErrExist) {
		removeEmptyDirectories(parents)
		return nil, err
	}
	return parents, nil
}

func (p releasePlan) ownChecks(path string) error {
	for _, arg := range []string{"version", "selftest"} {
		// Audited: path is the temporary binary built and inspected above.
		// Only its own version and in-memory selftest commands run.
		// nosemgrep: dangerous-exec-command, go.lang.security.audit.dangerous-exec-command.dangerous-exec-command
		cmd := exec.Command(path, arg) //nolint:gosec // G204: audited above
		cmd.Env = p.env
		out, err := cmd.CombinedOutput()
		if err != nil {
			return fmt.Errorf("agent-hook %s: %w: %s", arg, err, out)
		}
		if arg == "version" && string(out) != "agent-hook "+p.id+" "+p.version+"\n" {
			return fmt.Errorf("unexpected agent-hook version: %q", out)
		}
	}
	return nil
}

// releaseDisk is the file system as a publish needs it. The order of these
// steps makes a release reach the disk whole or not at all.
type releaseDisk interface {
	SyncFile(path string) error
	SyncDirectory(path string) error
	Rename(oldpath, newpath string) error
}

// systemDisk is this machine's releaseDisk.
type systemDisk struct{}

func (systemDisk) SyncFile(path string) error {
	root, err := os.OpenRoot(filepath.Dir(path))
	if err != nil {
		return err
	}
	defer root.Close()
	// Windows flushes only a handle open for writing. Linux's fsync needs no
	// write access, and there opening for writing a binary that is running,
	// or that ran a moment ago (its own checks), fails with ETXTBSY.
	flag := os.O_RDWR
	if runtime.GOOS == "linux" {
		flag = os.O_RDONLY
	}
	file, err := root.OpenFile(filepath.Base(path), flag, 0)
	if err != nil {
		return err
	}
	err = file.Sync()
	return errors.Join(err, file.Close())
}

func (systemDisk) SyncDirectory(path string) error { return syncDirectory(path) }

func (systemDisk) Rename(oldpath, newpath string) error { return os.Rename(oldpath, newpath) }

// publish moves a checked build from tmp to releases/<id>. The caller holds
// the lock on releases, so what it finds there no other build is changing.
func (p releasePlan) publish(disk releaseDisk, tmp, releases string) (string, error) {
	dir := filepath.Join(releases, p.id)
	name := binaryName(p.target)
	path := filepath.Join(dir, name)
	if _, err := os.Lstat(dir); err == nil {
		old, err := fileSHA256(path)
		if errors.Is(err, os.ErrNotExist) {
			// An ID without its binary is an incomplete publish, not a release.
			if err := os.RemoveAll(dir); err != nil {
				return "", err
			}
		} else if err != nil {
			return "", err
		} else {
			fresh, err := fileSHA256(filepath.Join(tmp, name))
			if err != nil {
				return "", err
			}
			if old != fresh {
				return "", fmt.Errorf("release %s is not reproducible; existing binary kept", p.id)
			}
			return path, nil
		}
	} else if !errors.Is(err, os.ErrNotExist) {
		return "", err
	}
	// The binary and its directory reach the disk before the rename names
	// them, and the rename reaches it after.
	if err := disk.SyncFile(filepath.Join(tmp, name)); err != nil {
		return "", err
	}
	if err := disk.SyncDirectory(tmp); err != nil {
		return "", err
	}
	if err := disk.Rename(tmp, dir); err != nil {
		return "", err
	}
	if err := disk.SyncDirectory(releases); err != nil {
		return "", err
	}
	return path, nil
}

func syncDirectory(path string) error {
	if runtime.GOOS == "windows" {
		return nil // Windows does not support Sync on a directory handle.
	}
	dir, err := os.OpenInRoot(path, ".")
	if err != nil {
		return err
	}
	defer dir.Close()
	return dir.Sync()
}
