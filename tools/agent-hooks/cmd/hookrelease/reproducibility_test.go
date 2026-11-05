package main

import (
	"bytes"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func mustRead(t *testing.T, path string) []byte {
	t.Helper()
	content, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	return content
}

func mustWrite(t *testing.T, path string, content []byte) {
	t.Helper()
	if err := os.WriteFile(path, content, 0o600); err != nil {
		t.Fatal(err)
	}
}

func builtRelease(t *testing.T, releases string) string {
	t.Helper()
	code, path, stderr := releaseCommand(t, "build", "--into", releases)
	if code != 0 {
		t.Fatalf("build exit %d: %s", code, stderr)
	}
	return path
}

func exerciseReleaseBuild(t *testing.T, module, path, releases string) {
	t.Helper()
	original := mustRead(t, path)
	id := filepath.Base(filepath.Dir(path))
	t.Run("different checkout and Git state", func(t *testing.T) {
		testCheckoutCopy(t, module, id, original)
	})
	t.Run("polluted environment", func(t *testing.T) {
		goenv := filepath.Join(t.TempDir(), "goenv")
		mustWrite(t, goenv, []byte("GOFLAGS=-tags=x\nCGO_ENABLED=1\n"))
		t.Setenv("GOENV", goenv)
		t.Setenv("GOFLAGS", "-tags=x")
		t.Setenv("GOEXPERIMENT", "not-a-real-experiment")
		t.Setenv("GOTOOLCHAIN", "not-a-real-toolchain")
		for file, content := range map[string]string{
			filepath.Join(filepath.Dir(module), "go.work"):             "go 1.27.3\nuse ./does-not-exist\n",
			filepath.Join(module, "cmd", "agent-hook", "default.pgo"):  "invalid PGO profile",
			filepath.Join(module, "cmd", "agent-hook", "pollution.go"): "//go:build x\n\npackage main\nfunc init() { panic(\"ambient GOFLAGS leaked\") }\n",
		} {
			mustWrite(t, file, []byte(content))
			t.Cleanup(func() { os.Remove(file) })
		}
		other := builtRelease(t, t.TempDir())
		if filepath.Base(filepath.Dir(other)) != id || !bytes.Equal(original, mustRead(t, other)) {
			t.Fatal("ambient settings, workspace, or PGO changed the release")
		}
	})
	t.Run("user cache locations from go env", func(t *testing.T) {
		testUserCacheLocations(t, id, original)
	})
	t.Run("compiled inputs change ID", func(t *testing.T) {
		for _, relative := range []string{"harnesses/claude/harness.json", "cmd/agent-hook/own.go", "go.sum"} {
			t.Run(relative, func(t *testing.T) {
				file := filepath.Join(module, filepath.FromSlash(relative))
				before := mustRead(t, file)
				mustWrite(t, file, append(bytes.Clone(before), '\n'))
				defer os.WriteFile(file, before, 0o600)
				other := builtRelease(t, releases)
				if filepath.Base(filepath.Dir(other)) == id {
					t.Fatalf("changing %s did not change ID", relative)
				}
			})
		}
	})
	t.Run("excluded inputs change neither ID nor bytes", func(t *testing.T) {
		otherOS := "windows"
		if runtime.GOOS == otherOS {
			otherOS = "linux"
		}
		for file, content := range map[string]string{
			"README.md":                                  "not a build input\n",
			"cmd/agent-hook/release_test.go":             "package main\n// Not a build input.\n",
			"cmd/agent-hook/excluded_" + otherOS + ".go": "package main\nfunc init() { panic(\"wrong target\") }\n",
		} {
			name := filepath.Join(module, filepath.FromSlash(file))
			mustWrite(t, name, []byte(content))
			t.Cleanup(func() { os.Remove(name) })
		}
		other := builtRelease(t, t.TempDir())
		if filepath.Base(filepath.Dir(other)) != id || !bytes.Equal(original, mustRead(t, other)) {
			t.Fatal("test, README, or other-target file changed ID or bytes")
		}
	})
	t.Run("existing release stays immutable", func(t *testing.T) {
		before, err := os.Stat(path)
		if err != nil {
			t.Fatal(err)
		}
		if got := builtRelease(t, releases); got != path {
			t.Fatalf("repeat build path = %q, want %q", got, path)
		}
		after, err := os.Stat(path)
		if err != nil || !before.ModTime().Equal(after.ModTime()) {
			t.Fatalf("repeat build rewrote the existing release: %v", err)
		}
		changed := bytes.Clone(original)
		changed[len(changed)/2] ^= 1
		if err := os.WriteFile(path, changed, 0o755); err != nil {
			t.Fatal(err)
		}
		defer os.WriteFile(path, original, 0o755)
		code, _, stderr := releaseCommand(t, "build", "--into", releases)
		if code == 0 || !strings.Contains(stderr, "not reproducible") || !bytes.Equal(changed, mustRead(t, path)) {
			t.Fatalf("conflicting release replaced or accepted: exit %d: %s", code, stderr)
		}
	})
	t.Run("checkout mismatch reports both IDs", func(t *testing.T) {
		file := filepath.Join(module, "go.sum")
		before := mustRead(t, file)
		mustWrite(t, file, append(bytes.Clone(before), '\n'))
		defer os.WriteFile(file, before, 0o600)
		other := builtRelease(t, releases)
		otherID := filepath.Base(filepath.Dir(other))
		code, _, stderr := releaseCommand(t, "check", path)
		if code != 1 || !strings.Contains(stderr, id) || !strings.Contains(stderr, otherID) {
			t.Fatalf("checkout mismatch exit %d: %s", code, stderr)
		}
		if code, _, stderr := releaseCommand(t, "check", filepath.Join(t.TempDir(), "missing")); code != 2 {
			t.Fatalf("missing binary exit %d, want 2: %s", code, stderr)
		}
	})
	t.Run("foreign target", func(t *testing.T) {
		testForeignTarget(t, releases, id)
	})
	t.Run("ARM level", func(t *testing.T) {
		code, _, stderr := releaseCommand(t, "build", "--into", releases, "--goos", "linux", "--goarch", "arm")
		if code != 0 {
			t.Fatalf("ARM build exit %d: %s", code, stderr)
		}
	})
	t.Run("refusals and cleanup", func(t *testing.T) {
		testReleaseRefusals(t, module)
	})
	entries, err := os.ReadDir(releases)
	if err != nil {
		t.Fatal(err)
	}
	for _, entry := range entries {
		if !entry.IsDir() {
			t.Fatalf("temporary build file left behind: %s", entry.Name())
		}
	}
}

func testUserCacheLocations(t *testing.T, id string, original []byte) {
	t.Helper()
	var settings strings.Builder
	for _, key := range []string{"GOCACHE", "GOMODCACHE", "GOPATH"} {
		settings.WriteString(key + "=" + os.Getenv(key) + "\n")
		t.Setenv(key, "")
	}
	settings.WriteString("GOFLAGS=-tags=x\n")
	file := filepath.Join(t.TempDir(), "goenv")
	mustWrite(t, file, []byte(settings.String()))
	t.Setenv("GOENV", file)
	// The fallback GOPATH cannot be created. Only the user's cache locations
	// from go env can make this build pass.
	mustWrite(t, filepath.Join(os.Getenv("HOME"), "go"), []byte("not a directory"))
	other := builtRelease(t, t.TempDir())
	if filepath.Base(filepath.Dir(other)) != id || !bytes.Equal(original, mustRead(t, other)) {
		t.Fatal("user cache locations changed the release")
	}
}

func testCheckoutCopy(t *testing.T, module, id string, original []byte) {
	t.Helper()
	copyDir := filepath.Join(t.TempDir(), "git checkout")
	if err := os.CopyFS(copyDir, os.DirFS(module)); err != nil {
		t.Fatal(err)
	}
	for _, args := range [][]string{
		{"init", "-q", copyDir},
		{"-C", copyDir, "add", "."},
		{"-C", copyDir, "-c", "user.name=Release Test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false", "commit", "-qm", "fixture"},
		{"-C", copyDir, "-c", "user.name=Release Test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false", "commit", "--allow-empty", "-qm", "extra commit"},
	} {
		if out, err := exec.Command("git", args...).CombinedOutput(); err != nil {
			t.Fatalf("git %v: %v: %s", args, err, out)
		}
	}
	t.Chdir(copyDir)
	other := builtRelease(t, t.TempDir())
	if filepath.Base(filepath.Dir(other)) != id || !bytes.Equal(original, mustRead(t, other)) {
		t.Fatal("checkout location or Git history changed the release ID or bytes")
	}
}

func testForeignTarget(t *testing.T, releases, hostID string) {
	t.Helper()
	otherOS := "windows"
	if runtime.GOOS == otherOS {
		otherOS = "linux"
	}
	code, other, stderr := releaseCommand(t, "build", "--into", releases, "--goos", otherOS, "--goarch", "amd64")
	if code != 0 || !strings.Contains(stderr, "skipping version and selftest") {
		t.Fatalf("cross build exit %d: %s", code, stderr)
	}
	if filepath.Base(filepath.Dir(other)) == hostID || (otherOS == "windows" && filepath.Ext(other) != ".exe") {
		t.Fatalf("cross build release path = %q", other)
	}
	if code, _, stderr := releaseCommand(t, "check", other); code != 0 {
		t.Fatalf("cross build check exit %d: %s", code, stderr)
	}
}

func testReleaseRefusals(t *testing.T, module string) {
	t.Helper()
	for _, tc := range []struct{ name, file, text, reason string }{
		{"replace", "go.mod", "\nreplace example.invalid/unused => ../elsewhere\n", "replace"},
		{"C source", "cmd/agent-hook/unsupported.c", "void unsupported(void) {}\n", "C source files"},
		{"failed selftest", "internal/selftest/answers.go", "", "selftest"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			file := filepath.Join(module, filepath.FromSlash(tc.file))
			before, readErr := os.ReadFile(file)
			if readErr != nil && !errors.Is(readErr, os.ErrNotExist) {
				t.Fatal(readErr)
			}
			t.Cleanup(func() {
				if readErr == nil {
					os.WriteFile(file, before, 0o600)
				} else {
					os.Remove(file)
				}
			})
			changed := append(bytes.Clone(before), tc.text...)
			if tc.name == "failed selftest" {
				changed = []byte(strings.Replace(string(before), `exit: 0, stdout: "", stderr: ""`, `exit: 0, stdout: "wrong answer", stderr: ""`, 1))
				if bytes.Equal(before, changed) {
					t.Fatal("selftest answer fixture was not changed")
				}
			}
			mustWrite(t, file, changed)
			releases := filepath.Join(t.TempDir(), "releases")
			code, _, stderr := releaseCommand(t, "build", "--into", releases)
			if code == 0 || !strings.Contains(stderr, tc.reason) {
				t.Fatalf("refusal exit %d, want %s: %s", code, tc.reason, stderr)
			}
			if _, err := os.Stat(releases); !errors.Is(err, os.ErrNotExist) {
				t.Fatalf("failed build left its release directory: %v", err)
			}
		})
	}
}
