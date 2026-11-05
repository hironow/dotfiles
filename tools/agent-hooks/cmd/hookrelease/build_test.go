package main

import (
	"bytes"
	"debug/buildinfo"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func releaseCommand(t *testing.T, args ...string) (int, string, string) {
	t.Helper()
	var stdout, stderr bytes.Buffer
	code := run(args, &stdout, &stderr)
	return code, strings.TrimSpace(stdout.String()), stderr.String()
}

func TestCheckHelpExplainsFreshCache(t *testing.T) {
	code, _, stderr := releaseCommand(t, "check", "--help")
	if code != 0 || !strings.Contains(stderr, "slower") || !strings.Contains(stderr, "temporary GOCACHE") {
		t.Fatalf("check help exit %d: %s", code, stderr)
	}
}

func shellLiteral(value string) string {
	return "'" + strings.ReplaceAll(value, "'", "'\\''") + "'"
}

func installGoWrapper(t *testing.T, commands string) {
	t.Helper()
	if runtime.GOOS == "windows" {
		t.Skip("test go wrapper requires a POSIX shell")
	}
	realGo, err := exec.LookPath("go")
	if err != nil {
		t.Fatal(err)
	}
	dir := t.TempDir()
	script := "#!/bin/sh\nreal_go=" + shellLiteral(realGo) + "\n" + commands + "\nexec \"$real_go\" \"$@\"\n"
	if err := os.WriteFile(filepath.Join(dir, "go"), []byte(script), 0o755); err != nil {
		t.Fatal(err)
	}
	t.Setenv("PATH", dir+string(os.PathListSeparator)+os.Getenv("PATH"))
}

func isolatedModule(t *testing.T) string {
	t.Helper()
	source, err := filepath.Abs("../..")
	if err != nil {
		t.Fatal(err)
	}
	for _, key := range []string{"GOCACHE", "GOMODCACHE", "GOPATH"} {
		out, err := exec.Command("go", "env", key).Output()
		if err != nil {
			t.Fatal(err)
		}
		t.Setenv(key, strings.TrimSpace(string(out)))
	}
	root := t.TempDir()
	t.Setenv("HOME", root)
	t.Setenv("USERPROFILE", root)
	t.Setenv("LOCALAPPDATA", filepath.Join(root, "local"))
	t.Setenv("XDG_DATA_HOME", filepath.Join(root, "data"))
	t.Setenv("XDG_STATE_HOME", filepath.Join(root, "state"))
	module := filepath.Join(root, "module with spaces")
	if err := os.CopyFS(module, os.DirFS(source)); err != nil {
		t.Fatal(err)
	}
	t.Chdir(module)
	return module
}

func TestReleaseBuild(t *testing.T) {
	module := isolatedModule(t)
	releases := filepath.Join(t.TempDir(), "releases")
	code, path, stderr := releaseCommand(t, "build", "--into", releases)
	if code != 0 {
		t.Fatalf("build exit %d: %s", code, stderr)
	}
	id := filepath.Base(filepath.Dir(path))
	if len(id) != 16 || filepath.Dir(filepath.Dir(path)) != releases {
		t.Fatalf("unexpected release path %q", path)
	}
	metadata, err := buildinfo.ReadFile(path)
	if err != nil || metadata.GoVersion != runtime.Version() {
		t.Fatalf("build metadata = %v (%v)", metadata, err)
	}
	// Audited: path is the release this test built in its temporary directory.
	// Its build information was checked above. The argument is fixed; no shell runs.
	// nosemgrep: dangerous-exec-command, go.lang.security.audit.dangerous-exec-command.dangerous-exec-command
	version, err := exec.Command(path, "version").CombinedOutput()
	if err != nil || string(version) != "agent-hook "+id+" "+runtime.Version()+"\n" {
		t.Fatalf("version = %q (%v)", version, err)
	}
	// Audited: path is the same test-built release checked above.
	// The fixed selftest command uses in-memory fakes; no shell runs.
	// nosemgrep: dangerous-exec-command, go.lang.security.audit.dangerous-exec-command.dangerous-exec-command
	selftest, err := exec.Command(path, "selftest").CombinedOutput()
	if err != nil || !strings.Contains(string(selftest), "cases pass") {
		t.Fatalf("selftest = %q (%v)", selftest, err)
	}
	for _, name := range []string{path, filepath.Dir(path)} {
		stat, err := os.Stat(name)
		if err != nil || (runtime.GOOS != "windows" && stat.Mode().Perm() != 0o755) {
			t.Fatalf("release permissions: %s: %v (%v)", name, stat, err)
		}
	}
	t.Run("check", func(t *testing.T) {
		checkPath := path
		if runtime.GOOS != "windows" {
			root := filepath.Dir(releases)
			if code, _, stderr := releaseCommand(t, "switch", "--root", root, "--home", "claude", path); code != 0 {
				t.Fatalf("switch exit %d: %s", code, stderr)
			}
			checkPath = filepath.Join(root, "current", "claude", "agent-hook")
		}
		if code, _, stderr := releaseCommand(t, "check", checkPath); code != 0 {
			t.Fatalf("check exit %d: %s", code, stderr)
		}
		original, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		changed := bytes.Clone(original)
		changed[len(changed)/2] ^= 1
		if err := os.WriteFile(path, changed, 0o755); err != nil {
			t.Fatal(err)
		}
		defer os.WriteFile(path, original, 0o755)
		if code, _, stderr := releaseCommand(t, "check", checkPath); code != 1 {
			t.Fatalf("changed binary check exit %d, want 1: %s", code, stderr)
		}
	})
	exerciseReleaseBuild(t, module, path, releases)
}
