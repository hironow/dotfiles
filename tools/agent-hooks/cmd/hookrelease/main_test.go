package main

import (
	"fmt"
	"os"
	"path/filepath"
	"testing"
)

// TestMain points every state and data directory at a temporary one, so no
// test of this package can reach the real ~/.local/state or ~/.local/share:
// switch takes its lock in the state directory, and build and switch default
// to the data directory. A test that needs its own sets it with t.Setenv.
func TestMain(m *testing.M) {
	base, err := os.MkdirTemp("", "hookrelease-test-")
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	for name, dir := range map[string]string{"XDG_STATE_HOME": "state", "XDG_DATA_HOME": "data", "LOCALAPPDATA": "local"} {
		if err := os.Setenv(name, filepath.Join(base, dir)); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
	}
	code := m.Run()
	os.RemoveAll(base)
	os.Exit(code)
}

func TestNoTestReachesTheRealStateOrData(t *testing.T) {
	// given TestMain's directories, then the switch's state is below them
	state, err := switchState()
	if err != nil {
		t.Fatal(err)
	}
	home, err := os.UserHomeDir()
	if err != nil {
		t.Fatal(err)
	}
	for _, real := range []string{filepath.Join(home, ".local", "state"), filepath.Join(home, ".local", "share")} {
		if rel, err := filepath.Rel(real, state); err == nil && filepath.IsLocal(rel) {
			t.Fatalf("switch state %s is below the real %s", state, real)
		}
	}
	data, err := dataRoot()
	if err != nil {
		t.Fatal(err)
	}
	if rel, err := filepath.Rel(filepath.Join(home, ".local", "share"), data); err == nil && filepath.IsLocal(rel) {
		t.Fatalf("data root %s is below the real ~/.local/share", data)
	}
}
