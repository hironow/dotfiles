//go:build windows

package launch

import (
	"bytes"
	"errors"
	"os"
	"os/exec"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/process"
)

// Run stops the direct child at the earlier command or stage deadline.
func (ExecMachine) Run(command process.Command) (process.Result, error) {
	ctx, cancel := commandContext(command)
	defer cancel()
	// Audited: hooks run the programs found on PATH or returned by mise,
	// with the same arguments as the scripts they replace. Payloads reach
	// arguments or stdin, never the executable path. No shell is invoked here.
	// nosemgrep: dangerous-exec-command, go.lang.security.audit.dangerous-exec-command.dangerous-exec-command
	cmd := exec.CommandContext(ctx, command.Path) //nolint:gosec // G204: audited above
	cmd.Args = command.Args
	cmd.Dir = command.Dir
	cmd.WaitDelay = waitDelay
	if command.Stdin != nil {
		cmd.Stdin = bytes.NewReader(command.Stdin)
	}
	var stdout, stderr bytes.Buffer
	cmd.Stdout, cmd.Stderr = &stdout, &stderr
	if command.Combined {
		cmd.Stderr = &stdout
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
		result.Signaled = signaled(exitErr)
		return result, nil
	default:
		return process.Result{}, err
	}
}

// LookPath is Go's exec.LookPath on Windows, which knows PATHEXT. A program
// found relative to the current directory is not found: the binary never
// runs one.
func (ExecMachine) LookPath(name string) (process.Program, bool) {
	path, err := exec.LookPath(name)
	if err != nil {
		if errors.Is(err, exec.ErrDot) {
			return process.Program{Path: path, Relative: true}, true
		}
		return process.Program{}, false
	}
	return process.Program{Path: path}, true
}

// IsExecutable is os.access(path, X_OK) on Windows, which only asks whether
// the path exists.
func (ExecMachine) IsExecutable(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}

// signaled is false on Windows: a process there ends with an exit code.
func signaled(*exec.ExitError) bool { return false }

// HomeDir is Node's os.homedir() on Windows as far as an environment
// variable tells it: USERPROFILE when it is set. Pi's paths are resolved
// only on POSIX (internal/pipath), so nothing reads it yet.
func (ExecMachine) HomeDir() (string, bool) {
	return os.LookupEnv("USERPROFILE")
}

// Getwd is the working directory.
func (ExecMachine) Getwd() string {
	cwd, err := os.Getwd()
	if err != nil {
		return ""
	}
	return cwd
}
