package launch

import (
	"bytes"
	"context"
	"errors"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"time"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/fileguard"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/process"
)

// basenameProbeTimeout bounds `basename --version`, which answers at once.
const basenameProbeTimeout = 5 * time.Second

// waitDelay bounds how long a command's output pipes may stay open after it
// exits or is killed (a child it left behind may hold them).
const waitDelay = 2 * time.Second

// ExecMachine is the machine this process runs on, reached with os/exec.
type ExecMachine struct{}

// Basename runs `basename --version` from PATH, found as bash finds it. Only
// GNU's takes --version; any failure, including no basename on PATH, reads
// as BSD's. A basename found through a relative PATH entry is not run: GNU's
// flavor is assumed, the one that reads on past --help and so can only block
// more.
func (m ExecMachine) Basename() fileguard.Basename {
	program, found := m.LookPath("basename")
	if !found {
		return fileguard.BSDBasename
	}
	if program.Relative {
		return fileguard.GNUBasename
	}
	result, err := m.Run(process.Command{
		Path: program.Path, Args: []string{"basename", "--version"}, Timeout: basenameProbeTimeout,
	})
	if err == nil && result.Exit == 0 {
		return fileguard.GNUBasename
	}
	return fileguard.BSDBasename
}

// IsWindows reports whether this process runs on Windows.
func (ExecMachine) IsWindows() bool { return runtime.GOOS == "windows" }

// IsRegularFile is `[ -f path ]`: a regular file, following symlinks.
func (ExecMachine) IsRegularFile(path string) bool {
	info, err := os.Stat(path)
	return err == nil && info.Mode().IsRegular()
}

// RealPath follows every symlink in an absolute path.
func (ExecMachine) RealPath(path string) (string, error) {
	return filepath.EvalSymlinks(path)
}

// Exists reports whether there is an entry at the path, a final symlink not
// followed. "No such file" is no entry; any other error is the lookup's.
func (ExecMachine) Exists(path string) (bool, error) {
	_, err := os.Lstat(path)
	switch {
	case err == nil:
		return true, nil
	case errors.Is(err, fs.ErrNotExist):
		return false, nil
	default:
		return false, err
	}
}

// Run runs the command in this process's environment, as the old scripts'
// commands ran, and in its working directory unless the command names
// another. With Combined, stdout and stderr share one pipe, as `2>&1` makes
// them, and Result.Stdout holds both.
func (ExecMachine) Run(command process.Command) (process.Result, error) {
	ctx := context.Background()
	if command.Timeout > 0 {
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(ctx, command.Timeout)
		defer cancel()
	}
	// Audited: the hooks run what the old scripts ran, found the way they
	// found it (process.Search on PATH, or mise's answer), never a program
	// found through a relative PATH entry; the arguments are the scripts'.
	// nosemgrep: go.lang.security.audit.dangerous-exec-command.dangerous-exec-command
	cmd := exec.CommandContext(ctx, command.Path) //nolint:gosec // G204: audited above
	cmd.Args = command.Args
	cmd.Dir = command.Dir
	cmd.WaitDelay = waitDelay
	if command.Stdin != nil {
		cmd.Stdin = bytes.NewReader(command.Stdin)
	}
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	if command.Combined {
		cmd.Stderr = &stdout // the same writer: one pipe, as 2>&1
	}
	err := cmd.Run()
	if ctx.Err() != nil {
		return process.Result{}, ctx.Err()
	}
	result := process.Result{Stdout: stdout.Bytes(), Stderr: stderr.Bytes()}
	var exitErr *exec.ExitError
	switch {
	case err == nil:
		return result, nil
	case errors.As(err, &exitErr):
		result.Exit = exitErr.ExitCode()
		return result, nil
	default:
		return process.Result{}, err
	}
}
