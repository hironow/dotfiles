package main

import (
	"errors"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	json "github.com/goccy/go-json/v2"
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

// linkCase is one row of testdata/link-cases.json, which sync's link switch
// (scripts/agent_hook_wiring.py) reads too, so both keep one rule.
type linkCase struct {
	Name string `json:"name"`
	Make []struct {
		File    string `json:"file"`
		Dir     string `json:"dir"`
		Symlink string `json:"symlink"`
		To      string `json:"to"`
	} `json:"make"`
	Target string  `json:"target"`
	Want   *string `json:"want"`
}

func TestSwitchFollowsTheSharedLinkCases(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("switch is refused on Windows")
	}
	data, err := os.ReadFile(filepath.Join("testdata", "link-cases.json"))
	if err != nil {
		t.Fatal(err)
	}
	var table struct {
		About string     `json:"about"`
		Cases []linkCase `json:"cases"`
	}
	if err := json.Unmarshal(data, &table, json.RejectUnknownMembers(true)); err != nil || len(table.Cases) == 0 {
		t.Fatalf("link cases: %v", err)
	}
	for _, c := range table.Cases {
		t.Run(c.Name, func(t *testing.T) {
			// given the case's files below a data root
			base := t.TempDir()
			root := filepath.Join(base, "root")
			if err := os.MkdirAll(root, 0o755); err != nil {
				t.Fatal(err)
			}
			t.Setenv("XDG_STATE_HOME", filepath.Join(base, "state"))
			for _, entry := range c.Make {
				switch {
				case entry.File != "":
					path := filepath.Join(root, entry.File)
					mustMkdir(t, filepath.Dir(path))
					if err := os.WriteFile(path, []byte("release"), 0o755); err != nil {
						t.Fatal(err)
					}
				case entry.Dir != "":
					mustMkdir(t, filepath.Join(root, entry.Dir))
				case entry.Symlink != "":
					path := filepath.Join(root, entry.Symlink)
					mustMkdir(t, filepath.Dir(path))
					if err := os.Symlink(entry.To, path); err != nil {
						t.Fatal(err)
					}
				}
			}
			// when the link is switched to the case's target
			code, _, stderr := releaseCommand(t, "switch", "--root", root, "--home", "k", filepath.Join(root, c.Target))
			link := filepath.Join(root, "current", "k", "agent-hook")
			// then a refusal leaves no link, and a release is linked as resolved
			if c.Want == nil {
				if _, err := os.Lstat(link); code != 2 || !errors.Is(err, os.ErrNotExist) {
					t.Fatalf("exit %d, link %v; want a refusal and no link: %s", code, err, stderr)
				}
				return
			}
			resolvedRoot, err := filepath.EvalSymlinks(root)
			if err != nil {
				t.Fatal(err)
			}
			got, err := os.Readlink(link)
			if code != 0 || err != nil || got != filepath.Join(resolvedRoot, *c.Want) {
				t.Fatalf("exit %d, link %q (%v); want %q: %s", code, got, err, filepath.Join(resolvedRoot, *c.Want), stderr)
			}
		})
	}
}

func mustMkdir(t *testing.T, path string) {
	t.Helper()
	if err := os.MkdirAll(path, 0o755); err != nil {
		t.Fatal(err)
	}
}

// isolatedSwitchState is the state directory a switch locks and reads
// journals in, below an isolated XDG_STATE_HOME.
func isolatedSwitchState(t *testing.T) string {
	t.Helper()
	base := t.TempDir()
	t.Setenv("XDG_STATE_HOME", base)
	dir := filepath.Join(base, "dotfiles", "agent-hooks")
	mustMkdir(t, dir)
	return dir
}

func TestSwitchRefusesWhileAJournalIsPending(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("switch is refused on Windows")
	}
	root := t.TempDir()
	target := release(t, root, "0123456789abcdef")
	state := isolatedSwitchState(t)
	// given a registration change sync left unfinished
	if err := os.WriteFile(filepath.Join(state, "switch-work-a.json"), []byte("{}"), 0o600); err != nil {
		t.Fatal(err)
	}
	// when a switch runs, then it refuses, naming the journal, and links nothing
	code, _, stderr := releaseCommand(t, "switch", "--root", root, "--home", "claude", target)
	if _, err := os.Lstat(filepath.Join(root, "current", "claude", "agent-hook")); code != 2 || !strings.Contains(stderr, "switch-work-a.json") || !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("exit %d, link %v: %s; want a refusal naming the journal", code, err, stderr)
	}
}

func TestSwitchSyncsWhatItCreatesAndRenames(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("switch is refused on Windows")
	}
	root := t.TempDir()
	target := release(t, root, "0123456789abcdef")
	resolvedRoot, err := filepath.EvalSymlinks(root)
	if err != nil {
		t.Fatal(err)
	}
	disk := &recordingDisk{releases: resolvedRoot}
	// when a first switch makes current/ and current/claude/
	if _, err := switchLink(disk, resolvedRoot, "claude", target); err != nil {
		t.Fatal(err)
	}
	// then each new directory's parent is synced, then the rename, then its
	// directory, so the link reaches the disk named
	if len(disk.steps) != 4 || disk.steps[0] != "sync-dir ." || disk.steps[1] != "sync-dir current" ||
		!strings.HasPrefix(disk.steps[2], "rename current/claude/.agent-hook-") || !strings.HasSuffix(disk.steps[2], " current/claude/agent-hook") ||
		disk.steps[3] != "sync-dir current/claude" {
		t.Fatalf("steps %q", disk.steps)
	}
}
