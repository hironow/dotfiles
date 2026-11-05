package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"go/build"
	"io"
	"os"
	"os/exec"
	"path/filepath"
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
	plan := releasePlan{target: target}
	dir, err := os.Getwd()
	if err != nil {
		return plan, err
	}
	dir, err = filepath.EvalSymlinks(dir)
	if err != nil {
		return plan, err
	}
	plan.goTool = goTool{dir: dir, env: normalizedEnvironment(userCacheEnvironment(dir), target)}
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
	Dir                                            string
	Module                                         *struct{ Main bool }
	GoFiles, SFiles, HFiles, SysoFiles, EmbedFiles []string
}

func (p releasePlan) inputs() ([]fileDigest, error) {
	out, err := p.run(false, "list", "-deps", "-json", "./cmd/agent-hook")
	if err != nil {
		return nil, err
	}
	paths := map[string]bool{"go.mod": true, "go.sum": true}
	decoder := jsontext.NewDecoder(bytes.NewReader(out))
	for {
		var pkg listedPackage
		if err := json.UnmarshalDecode(decoder, &pkg); errors.Is(err, io.EOF) {
			break
		} else if err != nil {
			return nil, fmt.Errorf("decode go list: %w", err)
		}
		if pkg.Module == nil || !pkg.Module.Main {
			continue
		}
		if err := refuseForeignInputs(pkg.Dir, p.target); err != nil {
			return nil, err
		}
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

func refuseForeignInputs(dir string, target buildTarget) error {
	// go list drops C and Swig files when cgo is off. Inspect the same
	// package with cgo enabled to refuse those files, without compiling them.
	context := build.Default
	context.GOOS, context.GOARCH, context.CgoEnabled = target.OS, target.Arch, true
	context.BuildTags = nil
	pkg, err := context.ImportDir(dir, 0)
	if err != nil {
		return fmt.Errorf("inspect release inputs: %w", err)
	}
	for _, files := range [][]string{pkg.CgoFiles, pkg.CFiles, pkg.CXXFiles, pkg.MFiles, pkg.FFiles, pkg.SwigFiles, pkg.SwigCXXFiles} {
		if len(files) != 0 {
			return fmt.Errorf("unsupported C source files or related inputs in %s: %v", dir, files)
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

func (p releasePlan) build(releases string, stderr io.Writer) (string, error) {
	releases, err := filepath.Abs(releases)
	if err != nil {
		return "", err
	}
	created, err := makeReleaseParents(releases)
	if err != nil {
		return "", err
	}
	defer removeEmptyDirectories(created)
	pattern := ".agent-hook-*"
	if p.target.OS == "windows" {
		pattern += ".exe"
	}
	tmp, err := os.CreateTemp(releases, pattern)
	if err != nil {
		return "", err
	}
	defer os.Remove(tmp.Name())
	if err := tmp.Close(); err != nil {
		return "", err
	}
	if _, err := p.run(false, "build", "-trimpath", "-buildvcs=false", "-pgo=off", "-ldflags="+linkFlags(p.module, p.id), "-o", tmp.Name(), "./cmd/agent-hook"); err != nil {
		return "", err
	}
	if err := os.Chmod(tmp.Name(), 0o755); err != nil {
		return "", err
	}
	if err := verifyBuild(tmp.Name(), p.version, p.target); err != nil {
		return "", err
	}
	if p.target.OS == runtime.GOOS && p.target.Arch == runtime.GOARCH {
		if err := p.ownChecks(tmp.Name()); err != nil {
			return "", err
		}
	} else {
		fmt.Fprintf(stderr, "hookrelease: %s/%s is not the host; skipping version and selftest\n", p.target.OS, p.target.Arch)
	}
	return p.publish(tmp.Name(), releases)
}

func removeEmptyDirectories(paths []string) {
	for _, path := range paths {
		_ = os.Remove(path)
	}
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

func (p releasePlan) publish(tmp, releases string) (string, error) {
	dir := filepath.Join(releases, p.id)
	name := "agent-hook"
	if p.target.OS == "windows" {
		name += ".exe"
	}
	path := filepath.Join(dir, name)
	if err := os.Mkdir(dir, 0o755); errors.Is(err, os.ErrExist) {
		old, err := fileSHA256(path)
		if err != nil {
			return "", err
		}
		fresh, err := fileSHA256(tmp)
		if err != nil {
			return "", err
		}
		if old != fresh {
			return "", fmt.Errorf("release %s is not reproducible; existing binary kept", p.id)
		}
		return path, nil
	} else if err != nil {
		return "", err
	}
	defer os.Remove(dir) // Remove only an empty directory on failure.
	if err := os.Chmod(dir, 0o755); err != nil {
		return "", err
	}
	if err := os.Rename(tmp, path); err != nil {
		return "", err
	}
	return path, nil
}
