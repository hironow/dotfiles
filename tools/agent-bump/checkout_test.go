package main

import (
	"context"
	"os/exec"
	"path/filepath"
	"testing"
)

func git(t *testing.T, dir string, args ...string) {
	t.Helper()
	cmd := exec.CommandContext(context.Background(), "git", append([]string{"-C", dir}, args...)...)
	cmd.Env = append(cmd.Environ(), "GIT_CONFIG_GLOBAL=", "GIT_CONFIG_NOSYSTEM=1")
	if out, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("git %v: %v\n%s", args, err, out)
	}
}

// The installers resolve repo paths (the hironow-plugins marketplace, Pi
// extension links) from the checkout they run in; from a linked worktree they
// would point every agent home at a directory that is deleted later.
func TestALinkedWorktreeIsToldApartFromTheMainCheckout(t *testing.T) {
	main := t.TempDir()
	git(t, main, "init", "-q")
	git(t, main, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "commit", "-q", "--allow-empty", "-m", "init")
	linked := filepath.Join(t.TempDir(), "wt")
	git(t, main, "worktree", "add", "-q", linked)

	if wt, err := (checkout{root: main}).LinkedWorktree(); err != nil || wt {
		t.Fatalf("main checkout: linked=%v err=%v", wt, err)
	}
	if wt, err := (checkout{root: linked}).LinkedWorktree(); err != nil || !wt {
		t.Fatalf("linked worktree: linked=%v err=%v", wt, err)
	}
}
