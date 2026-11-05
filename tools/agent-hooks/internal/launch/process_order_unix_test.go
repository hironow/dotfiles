//go:build !windows

package launch

import (
	"context"
	"errors"
	"os/exec"
	"runtime"
	"slices"
	"syscall"
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/fake"
)

func TestProcessOwnerSignalsOnlyBeforeReaping(t *testing.T) {
	for _, name := range []string{"normal", "deadline", "descendant"} {
		t.Run(name, func(t *testing.T) {
			life := &fake.ProcessLifetime{Exit: make(chan error, 1), ExitOnKill: name == "deadline"}
			drained := make(chan struct{})
			deadline := make(chan struct{})
			want := []string{"exit", "kill", "reap"}
			if name == "deadline" {
				close(deadline)
				want = []string{"kill", "exit", "kill", "reap"}
			} else {
				life.Exit <- nil
			}
			if name != "descendant" {
				close(drained)
			}
			err := finishProcess(life, drained, deadline)
			var wantErr error
			switch name {
			case "deadline":
				wantErr = context.DeadlineExceeded
			case "descendant":
				wantErr = exec.ErrWaitDelay
			}
			if !errors.Is(err, wantErr) {
				t.Errorf("finishProcess = %v", err)
			}
			if events := life.Events(); !slices.Equal(events, want) {
				t.Errorf("lifetime %v, want %v", events, want)
			}
		})
	}
}

func TestAnExitedMacOSGroupDoesNotLoseItsCommandResult(t *testing.T) {
	if runtime.GOOS != "darwin" {
		t.Skip("macOS reports EPERM for a group containing only zombies")
	}
	life := &fake.ProcessLifetime{Exit: make(chan error, 1), KillError: syscall.EPERM}
	life.Exit <- nil
	drained := make(chan struct{})
	close(drained)
	if err := finishProcess(life, drained, nil); err != nil {
		t.Errorf("post-exit cleanup replaced the command result: %v", err)
	}
	if got := life.Events(); !slices.Equal(got, []string{"exit", "kill", "reap"}) {
		t.Errorf("lifetime = %v", got)
	}
}
