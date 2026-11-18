//go:build windows

package main

import (
	"errors"
	"os/exec"
	"syscall"
)

// createNoWindow is CREATE_NO_WINDOW: the child is a console process that
// runs without a console window.
const createNoWindow = 0x08000000

// command is args[0] with args[1:], started without a console window. Its
// standard streams are NUL: no one reads a task's window.
func command(args []string) *exec.Cmd {
	// Audited: the program and its arguments are the scheduled task's own
	// command line, written by the dotfiles installers; no shell is involved.
	// nosemgrep: dangerous-exec-command, go.lang.security.audit.dangerous-exec-command.dangerous-exec-command
	cmd := exec.Command(args[0], args[1:]...) //nolint:gosec // G204: audited above
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: createNoWindow}
	return cmd
}

// run starts the program, waits for it, and returns its exit code.
func run(args []string) int {
	if len(args) == 0 {
		return 2
	}
	err := command(args).Run()
	if exit, ok := errors.AsType[*exec.ExitError](err); ok {
		return exit.ExitCode()
	}
	if err != nil {
		return 1
	}
	return 0
}
