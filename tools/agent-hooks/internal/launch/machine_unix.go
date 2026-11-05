//go:build !windows

package launch

import (
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"os/user"
	"runtime"
	"syscall"
	"time"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/process"
)

// Run owns a process group until its output is read and its leader is reaped.
func (ExecMachine) Run(command process.Command) (process.Result, error) {
	ctx, cancel := commandContext(command)
	defer cancel()
	if err := ctx.Err(); err != nil {
		return process.Result{}, err
	}
	// Audited: hooks run the programs found on PATH or returned by mise,
	// with the same arguments as the scripts they replace. Payloads reach
	// arguments or stdin, never the executable path. No shell is invoked here.
	// nosemgrep: dangerous-exec-command, go.lang.security.audit.dangerous-exec-command.dangerous-exec-command
	cmd := exec.Command(command.Path) //nolint:gosec // G204: audited above
	cmd.Args, cmd.Dir = command.Args, command.Dir
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	pipes, err := openCommandPipes(cmd, command)
	if err != nil {
		return process.Result{}, err
	}
	defer pipes.close()
	if err := cmd.Start(); err != nil {
		return process.Result{}, err
	}
	drained := pipes.serve(command.Stdin)
	err = finishProcess(unixProcess{cmd: cmd}, drained, ctx.Done())
	pipes.close()
	<-drained
	if pipes.stdinDone != nil {
		<-pipes.stdinDone
	}
	if ctx.Err() != nil {
		return process.Result{}, ctx.Err()
	}
	result := pipes.result()
	var exitErr *exec.ExitError
	switch {
	case err == nil:
		return result, nil
	case errors.As(err, &exitErr):
		result.Exit, result.Signaled = exitErr.ExitCode(), signaled(exitErr)
		return result, nil
	default:
		return process.Result{}, err
	}
}

type unixProcess struct {
	cmd *exec.Cmd
}

func (p unixProcess) WaitExit() error { return waitExit(p.cmd.Process.Pid) }

func (p unixProcess) KillGroup() error {
	err := syscall.Kill(-p.cmd.Process.Pid, syscall.SIGKILL)
	if errors.Is(err, syscall.ESRCH) {
		return nil
	}
	if err != nil {
		return fmt.Errorf("kill process group %d: %w", p.cmd.Process.Pid, err)
	}
	return err
}

func (p unixProcess) Reap() error { return p.cmd.Wait() }

// processLifetime keeps the group ID reserved until its owner finishes cleanup.
type processLifetime interface {
	WaitExit() error
	KillGroup() error
	Reap() error
}

// finishProcess is the only owner that signals the group and reaps its leader.
func finishProcess(life processLifetime, drained <-chan struct{}, deadline <-chan struct{}) error {
	exited := make(chan error, 1)
	go func() { exited <- life.WaitExit() }()
	var exitErr, killErr, limitErr error
	select {
	case exitErr = <-exited:
	case <-deadline:
		limitErr = context.DeadlineExceeded
		killErr = life.KillGroup()
		exitErr = <-exited
	}
	if exitErr == nil {
		delay := time.NewTimer(waitDelay)
		defer delay.Stop()
		select {
		case <-drained:
		case <-deadline:
			limitErr = context.DeadlineExceeded
		case <-delay.C:
		}
	}
	cleanupErr := life.KillGroup()
	// macOS skips zombies when signaling a group and returns EPERM when
	// none remain alive. Keep the command's result after its unreaped exit.
	if exitErr == nil && runtime.GOOS == "darwin" && errors.Is(cleanupErr, syscall.EPERM) {
		cleanupErr = nil
	}
	killErr = errors.Join(killErr, cleanupErr)
	reapErr := life.Reap()
	return errors.Join(limitErr, exitErr, killErr, reapErr)
}

// signaled reports whether a signal ended the process.
func signaled(exitErr *exec.ExitError) bool {
	status, ok := exitErr.Sys().(syscall.WaitStatus)
	return ok && status.Signaled()
}

// xOK is access(2)'s X_OK.
const xOK = 0x1

// LookPath finds a program on PATH as Python's shutil.which and bash do
// (process.Search), not as Go's exec.LookPath, which cleans each candidate
// and so can find another program through "link/..".
func (ExecMachine) LookPath(name string) (process.Program, bool) {
	return process.Search(os.Getenv("PATH"), name, isExecutableFile)
}

// isExecutableFile is shutil.which's check: an existing non-directory that
// access(2) lets this process execute.
func isExecutableFile(path string) bool {
	info, err := os.Stat(path)
	return err == nil && !info.IsDir() && syscall.Access(path, xOK) == nil
}

// IsExecutable is os.access(path, X_OK).
func (ExecMachine) IsExecutable(path string) bool {
	return syscall.Access(path, xOK) == nil
}

// HomeDir is Node's os.homedir() (libuv's uv_os_homedir): $HOME when it
// is set, even to "", else the password entry's home directory. Built
// without cgo, os/user reads /etc/passwd, which may not list the user (macOS
// keeps users elsewhere); then the home is unknown, and a ~ path is not
// resolved, which the files guard blocks.
func (ExecMachine) HomeDir() (string, bool) {
	if home, ok := os.LookupEnv("HOME"); ok {
		return home, true
	}
	current, err := user.Current()
	if err != nil || current.HomeDir == "" {
		return "", false
	}
	return current.HomeDir, true
}

// Getwd is the physical working directory, as Python's os.getcwd: the
// kernel's, never $PWD's spelling of it.
func (ExecMachine) Getwd() string {
	cwd, err := syscall.Getwd()
	if err != nil {
		return ""
	}
	return cwd
}
