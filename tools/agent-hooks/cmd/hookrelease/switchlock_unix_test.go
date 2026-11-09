//go:build unix

package main

import (
	"errors"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
	"time"
)

func TestSwitchWaitsForTheLockThenNamesItsHolder(t *testing.T) {
	root := t.TempDir()
	target := release(t, root, "0123456789abcdef")
	state := isolatedSwitchState(t)
	// given another run holding the lock sync and switch share
	held, err := os.OpenFile(filepath.Join(state, "switch.lock"), os.O_RDWR|os.O_CREATE, 0o600)
	if err != nil {
		t.Fatal(err)
	}
	defer held.Close()
	if err := syscall.Flock(int(held.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); err != nil {
		t.Fatal(err)
	}
	if _, err := held.WriteString(`{"pid":4242,"argv":["sync-agents"],"started":"2026-11-06T00:00:00Z"}` + "\n"); err != nil {
		t.Fatal(err)
	}
	defer func(wait time.Duration) { switchLockWait = wait }(switchLockWait)
	switchLockWait = 300 * time.Millisecond
	// when a switch runs, then it waits, stops, names the holder, and links nothing
	code, _, stderr := releaseCommand(t, "switch", "--root", root, "--home", "claude", target)
	if _, err := os.Lstat(filepath.Join(root, "current", "claude", "agent-hook")); code != 2 || !strings.Contains(stderr, "4242") || !strings.Contains(stderr, "sync-agents") || !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("exit %d, link %v: %s; want a refusal naming pid 4242 and no link", code, err, stderr)
	}
}
