package main_test

import (
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func TestVersionPrintsTheReleaseAndTheGoVersion(t *testing.T) {
	// given the binary these tests built (no release ID: "dev"), and one
	// built with a release ID, as the release build sets it
	release := filepath.Join(t.TempDir(), "agent-hook")
	// Audited: go builds this package into the test's own directory.
	// nosemgrep: go.lang.security.audit.dangerous-exec-command.dangerous-exec-command
	build := exec.Command("go", "build", "-ldflags=-X github.com/hironow/dotfiles/tools/agent-hooks/internal/logline.Release=0123456789abcdef",
		"-o", release, ".")
	if out, err := build.CombinedOutput(); err != nil {
		t.Fatalf("go build: %v\n%s", err, out)
	}
	for bin, id := range map[string]string{binary: "dev", release: "0123456789abcdef"} {
		// when each is asked its version
		exit, stdout, stderr := runBinaryIn(t, bin, t.TempDir(), nil, "version")
		// then it prints its release ID and the Go version it was built with
		want := "agent-hook " + id + " " + runtime.Version() + "\n"
		if exit != 0 || stdout != want || stderr != "" {
			t.Errorf("%s version: exit %d, stdout %q, stderr %q; want %q", bin, exit, stdout, stderr, want)
		}
	}
}

func TestSelftestPassesAndTakesNoArgument(t *testing.T) {
	state := t.TempDir()
	// given a state directory, when the binary answers its own cases
	exit, stdout, stderr := runIn(t, state, nil, "selftest")
	// then they all pass, and nothing is logged
	if exit != 0 || !strings.HasPrefix(stdout, "agent-hook selftest: ") || stderr != "" {
		t.Errorf("selftest: exit %d, stdout %q, stderr %q; want exit 0 and the count", exit, stdout, stderr)
	}
	if entries, err := os.ReadDir(state); err != nil || len(entries) != 0 {
		t.Errorf("selftest wrote to the state directory: %v (%v)", entries, err)
	}
	for _, args := range [][]string{{"selftest", "x"}, {"version", "x"}} {
		if exit, _, stderr := runIn(t, state, nil, args...); exit != 64 || !strings.Contains(stderr, "usage") {
			t.Errorf("agent-hook %q: exit %d, stderr %q; want exit 64 and the usage", args, exit, stderr)
		}
	}
}
