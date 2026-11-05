//go:build !windows

package launch_test

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strconv"
	"syscall"
	"testing"
	"time"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/launch"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/process"
)

func TestProcessLeaderLeavesItsGroup(t *testing.T) {
	if len(os.Args) != 6 || os.Args[3] != "--leave-group" {
		return
	}
	pgid, err := strconv.Atoi(os.Args[4])
	if err != nil {
		t.Fatal(err)
	}
	if err := syscall.Setpgid(0, pgid); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(os.Args[5], nil, 0o600); err != nil {
		t.Fatal(err)
	}
	// Bound the fixture even when the adapter fails to kill the moved leader.
	time.Sleep(2 * time.Second)
}

func TestExecMachineKillsALeaderThatLeftItsGroup(t *testing.T) {
	path, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	left := filepath.Join(t.TempDir(), "left-group")
	start := time.Now()
	limit := 300 * time.Millisecond
	_, err = (launch.ExecMachine{}).Run(process.Command{
		Path: path, Args: []string{path, "-test.run=^TestProcessLeaderLeavesItsGroup$", "--", "--leave-group", strconv.Itoa(syscall.Getpgrp()), left},
		Deadline: start.Add(limit),
	})
	if !errors.Is(err, context.DeadlineExceeded) || time.Since(start) > limit+300*time.Millisecond {
		t.Errorf("moved leader returned after %s: %v", time.Since(start), err)
	}
	if _, err := os.Stat(left); err != nil {
		t.Fatalf("leader did not leave its group: %v", err)
	}
}

func TestExecMachineHonorsTheEarlierCommandLimit(t *testing.T) {
	for _, timeoutFirst := range []bool{false, true} {
		t.Run(map[bool]string{false: "stage deadline", true: "command timeout"}[timeoutFirst], func(t *testing.T) {
			deadline, timeout := 60*time.Millisecond, time.Second
			if timeoutFirst {
				deadline, timeout = timeout, deadline
			}
			start := time.Now()
			_, err := (launch.ExecMachine{}).Run(process.Command{
				Path: "/bin/sh", Args: []string{"sh", "-c", "exec sleep 0.4"},
				Deadline: start.Add(deadline), Timeout: timeout,
			})
			if !errors.Is(err, context.DeadlineExceeded) || time.Since(start) > 300*time.Millisecond {
				t.Errorf("Run took %s, error %v; want the earlier deadline", time.Since(start), err)
			}
		})
	}
}
