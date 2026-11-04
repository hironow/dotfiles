//go:build !windows

package launch_test

import (
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/launch"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/process"
)

// script writes an executable /bin/sh script and returns its path.
func script(t *testing.T, body string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "rtk")
	if err := os.WriteFile(path, []byte("#!/bin/sh\n"+body+"\n"), 0o700); err != nil {
		t.Fatal(err)
	}
	return path
}

func TestExecMachineTellsWhatPisRtkNeedsToKnow(t *testing.T) {
	// What the fake machine's replay cannot show: how a real process ends
	// and what a whole read of its stdout gives.
	m := launch.ExecMachine{}
	run := func(body string, timeout time.Duration) (process.Result, error) {
		return m.Run(process.Command{Path: script(t, body), Args: []string{"rtk", "rewrite", "x"}, Timeout: timeout})
	}
	// A signal after printing: the output, and that a signal ended it.
	got, err := run(`printf 'rtk git status'; kill -TERM $$`, 5*time.Second)
	if err != nil || !got.Signaled || string(got.Stdout) != "rtk git status" {
		t.Errorf("a signal: %+v, %v; want the output and Signaled", got, err)
	}
	// An exit: no signal.
	got, err = run(`printf 'rtk ls'; exit 3`, 5*time.Second)
	if err != nil || got.Signaled || got.Exit != 3 {
		t.Errorf("exit 3: %+v, %v", got, err)
	}
	// A character split across two writes, a pause between: read whole
	// (rtk-split-utf8). The bytes are U+96EA's.
	got, err = run(`printf 'rtk echo \351'; sleep 0.1; printf '\233\252'`, 5*time.Second)
	if err != nil || string(got.Stdout) != "rtk echo 雪" {
		t.Errorf("a split character: %q, %v; want it whole", got.Stdout, err)
	}
	// Output a descendant writes after rtk exits is kept, while the pipe is
	// open (rtk-late-output).
	got, err = run(`printf 'rtk git status'; (sleep 0.35; printf ' --short') & exit 0`, 5*time.Second)
	if err != nil || string(got.Stdout) != "rtk git status --short" {
		t.Errorf("late output: %q, %v; want the tail kept", got.Stdout, err)
	}
	// A timeout is an error: the call did not end.
	if got, err = run(`exec sleep 3`, 200*time.Millisecond); err == nil {
		t.Errorf("a timeout: %+v, nil; want an error", got)
	}
}

func TestExecMachineLooksUpTheEnvironment(t *testing.T) {
	t.Setenv("AGENT_HOOK_PROBE", "")
	if got, ok := (launch.ExecMachine{}).LookupEnv("AGENT_HOOK_PROBE"); !ok || got != "" {
		t.Errorf("LookupEnv = %q, %v; want set and empty", got, ok)
	}
	if _, ok := (launch.ExecMachine{}).LookupEnv("AGENT_HOOK_PROBE_UNSET_NAME"); ok {
		t.Error("LookupEnv of an unset name: ok, want not set")
	}
}
