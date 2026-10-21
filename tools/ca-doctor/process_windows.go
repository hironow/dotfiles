package main

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"time"
)

func configureProcess(cmd *exec.Cmd) {
	cmd.Cancel = func() error {
		cleanupProcess(cmd)
		if cmd.Process == nil {
			return os.ErrProcessDone
		}
		return cmd.Process.Kill()
	}
}

// Native probes do not spawn children. For native PATH shims, make a bounded
// best-effort tree cleanup too. WaitDelay is the hard pipe-drain bound even
// when System32/taskkill is unavailable or the parent already exited.
func cleanupProcess(cmd *exec.Cmd) {
	if cmd.Process == nil {
		return
	}
	root := os.Getenv("SystemRoot")
	if root == "" {
		return
	}
	ctx, cancel := context.WithTimeout(context.Background(), 300*time.Millisecond)
	defer cancel()
	kill := exec.CommandContext(ctx, filepath.Join(root, "System32", "taskkill.exe"), "/PID", strconv.Itoa(cmd.Process.Pid), "/T", "/F")
	kill.WaitDelay = 100 * time.Millisecond
	_ = kill.Run()
}
