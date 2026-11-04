//go:build windows

package launch

import (
	"errors"
	"os"
	"os/exec"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/process"
)

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
