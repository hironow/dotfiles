package main

import (
	"context"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"time"
)

const captureLimit = 4096

type CommandResult struct {
	Stdout, Stderr string
	Code           int
	Truncated      bool
}

type Commands interface {
	Run(context.Context, string, ...string) CommandResult
}

type OSCommands struct{}

// Batch wrappers are not executables and cannot safely be interpolated into a
// shell command. Missing native executables remain unverified on Windows.
func ExecutableSupported(path, goos string) bool {
	if goos != "windows" {
		return true
	}
	return strings.EqualFold(filepath.Ext(path), ".exe")
}

type cappedOutput struct {
	mu        sync.Mutex
	text      []byte
	truncated bool
}

func (b *cappedOutput) Write(p []byte) (int, error) {
	b.mu.Lock()
	defer b.mu.Unlock()
	remaining := captureLimit - len(b.text)
	if len(p) > remaining {
		b.text = append(b.text, p[:remaining]...)
		b.truncated = true
	} else {
		b.text = append(b.text, p...)
	}
	// Always consume, including discarded bytes, so the child never blocks on
	// a full in-memory buffer. WaitDelay bounds inherited pipe lifetimes.
	return len(p), nil
}

func (OSCommands) Run(ctx context.Context, path string, args ...string) CommandResult {
	if !ExecutableSupported(path, runtime.GOOS) {
		return CommandResult{Code: -1}
	}
	bounded, cancel := context.WithTimeout(ctx, 4*time.Second)
	defer cancel()
	// Paths come from explicit discovery; arguments are never shell-expanded.
	cmd := exec.CommandContext(bounded, path, args...)
	// Version probes must not turn into compiler/toolchain installation via
	// Go's module-directed selection, mise shims, or rustup overrides.
	cmd.Env = append(os.Environ(), "GOTOOLCHAIN=local", "MISE_AUTO_INSTALL=false", "RUSTUP_AUTO_INSTALL=0")
	cmd.WaitDelay = 150 * time.Millisecond
	configureProcess(cmd)
	var stdout, stderr cappedOutput
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	err := cmd.Run()
	code := 0
	if err != nil {
		code = -1
		var exited *exec.ExitError
		if errors.As(err, &exited) {
			code = exited.ExitCode()
		}
		cleanupProcess(cmd)
	}
	return CommandResult{Stdout: string(stdout.text), Stderr: string(stderr.text), Code: code, Truncated: stdout.truncated || stderr.truncated}
}
