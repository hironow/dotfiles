package main

import (
	"os"
	"path/filepath"
	"runtime"
	"testing"
)

// release makes a stand-in release binary under root's releases directory.
func release(t *testing.T, root, id string) string {
	t.Helper()
	dir := filepath.Join(root, "releases", id)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(dir, "agent-hook")
	if err := os.WriteFile(path, []byte("release"), 0o755); err != nil {
		t.Fatal(err)
	}
	resolved, err := filepath.EvalSymlinks(path)
	if err != nil {
		t.Fatal(err)
	}
	return resolved
}

func TestSwitchKeepsHomesIndependent(t *testing.T) {
	root := t.TempDir()
	one, two := release(t, root, "0123456789abcdef"), release(t, root, "fedcba9876543210")
	if runtime.GOOS == "windows" {
		if code, _, _ := releaseCommand(t, "switch", "--root", root, "--home", "claude", one); code != 2 {
			t.Fatalf("Windows switch exit = %d, want 2", code)
		}
		return
	}
	for _, tc := range []struct{ home, path, previous string }{
		{"claude", one, ""}, {"codex", one, ""}, {"claude", two, one},
	} {
		code, previous, stderr := releaseCommand(t, "switch", "--root", root, "--home", tc.home, tc.path)
		if code != 0 || previous != tc.previous {
			t.Fatalf("switch %s: exit %d, previous %q, want %q: %s", tc.home, code, previous, tc.previous, stderr)
		}
	}
	for home, want := range map[string]string{"claude": two, "codex": one} {
		link := filepath.Join(root, "current", home, "agent-hook")
		if got, err := os.Readlink(link); err != nil || got != want {
			t.Fatalf("%s target = %q (%v), want %q", home, got, err, want)
		}
		entries, err := os.ReadDir(filepath.Dir(link))
		if err != nil || len(entries) != 1 {
			t.Fatalf("switch left temporary files: %v (%v)", entries, err)
		}
	}
	for _, key := range []string{"", "../escape", "Upper", "has_space", "日本語", "x/y"} {
		if code, _, stderr := releaseCommand(t, "switch", "--root", root, "--home", key, one); code != 2 {
			t.Fatalf("invalid key %q exit %d, want 2: %s", key, code, stderr)
		}
	}
}

func TestSwitchPointsOnlyAtAReleaseOfItsOwnRoot(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("switch is not wired on Windows")
	}
	root := t.TempDir()
	good := release(t, root, "0123456789abcdef")
	other := release(t, t.TempDir(), "0123456789abcdef")
	stray := filepath.Join(root, "agent-hook")
	if err := os.WriteFile(stray, []byte("not a release"), 0o755); err != nil {
		t.Fatal(err)
	}
	short := release(t, root, "0123abc")
	upper := release(t, root, "0123456789ABCDEF")
	// given paths that are not one of this root's releases
	for _, path := range []string{stray, other, short, upper, filepath.Join(filepath.Dir(good), "other-name")} {
		// when a home is switched to one, then it is refused, and no link is made
		if code, _, _ := releaseCommand(t, "switch", "--root", root, "--home", "claude", path); code != 2 {
			t.Errorf("switch to %s: exit %d, want 2", path, code)
		}
	}
	if _, err := os.Lstat(filepath.Join(root, "current", "claude", "agent-hook")); err == nil {
		t.Error("a refused switch made the link")
	}
	// the control: this root's release
	if code, _, stderr := releaseCommand(t, "switch", "--root", root, "--home", "claude", good); code != 0 {
		t.Fatalf("switch to a release: exit %d: %s", code, stderr)
	}
}

func TestSwitchRefusesEscapingReleaseSymlink(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("switch is not wired on Windows")
	}
	// A resolved root (macOS's temporary directory is under a link), so
	// only resolving the whole target can tell where the release is.
	root, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	good := release(t, root, "0123456789abcdef")
	if code, _, stderr := releaseCommand(t, "switch", "--root", root, "--home", "claude", good); code != 0 {
		t.Fatalf("initial switch exit %d: %s", code, stderr)
	}
	outside := release(t, t.TempDir(), "fedcba9876543210")
	escape := filepath.Join(root, "releases", "fedcba9876543210")
	if err := os.Symlink(filepath.Dir(outside), escape); err != nil {
		t.Fatal(err)
	}
	if code, _, stderr := releaseCommand(t, "switch", "--root", root, "--home", "claude", filepath.Join(escape, "agent-hook")); code != 2 {
		t.Fatalf("escaping switch exit %d, want 2: %s", code, stderr)
	}
	if got, err := os.Readlink(filepath.Join(root, "current", "claude", "agent-hook")); err != nil || got != good {
		t.Fatalf("refused switch changed link to %q (%v), want %q", got, err, good)
	}
}

func TestSwitchUsesRootFlag(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("switch is not wired on Windows")
	}
	root := t.TempDir()
	path := release(t, root, "0123456789abcdef")
	if code, _, stderr := releaseCommand(t, "switch", "--root", root, "--home", "claude", path); code != 0 {
		t.Fatalf("switch --root exit %d: %s", code, stderr)
	}
	if code, _, _ := releaseCommand(t, "switch", "--into", root, "--home", "claude", path); code != 2 {
		t.Fatalf("obsolete --into exit %d, want 2", code)
	}
}
