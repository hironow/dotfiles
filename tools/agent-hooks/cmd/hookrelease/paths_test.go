package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestDefaultReleaseDirectory(t *testing.T) {
	skipBuildOnWindows(t)
	isolatedModule(t)
	for _, tc := range []struct{ name, xdg string }{
		{"absolute XDG", filepath.Join(t.TempDir(), "xdg")},
		{"relative XDG", "relative-data"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			t.Setenv("XDG_DATA_HOME", tc.xdg)
			code, path, stderr := releaseCommand(t)
			if code != 0 {
				t.Fatalf("default build exit %d: %s", code, stderr)
			}
			root := filepath.Join(os.Getenv("HOME"), ".local", "share")
			if filepath.IsAbs(tc.xdg) {
				root = tc.xdg
			}
			if got, want := filepath.Dir(filepath.Dir(path)), filepath.Join(root, "dotfiles", "agent-hooks", "releases"); got != want {
				t.Fatalf("releases = %q, want %q", got, want)
			}
			if code, _, stderr := releaseCommand(t, "switch", "--home", "claude", path); code != 0 {
				t.Fatalf("default switch exit %d: %s", code, stderr)
			}
			link := filepath.Join(root, "dotfiles", "agent-hooks", "current", "claude", "agent-hook")
			resolved, err := filepath.EvalSymlinks(path)
			if err != nil {
				t.Fatal(err)
			}
			if got, err := os.Readlink(link); err != nil || got != resolved {
				t.Fatalf("default switch = %q (%v), want %q", got, err, resolved)
			}
		})
	}
	into := t.TempDir()
	if code, path, stderr := releaseCommand(t, "--into", into); code != 0 || !strings.HasPrefix(path, into) {
		t.Fatalf("implicit build with flags: exit %d, path %q: %s", code, path, stderr)
	}
}
