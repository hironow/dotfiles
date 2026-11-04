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

// Getwd is the working directory.
func (ExecMachine) Getwd() string {
	cwd, err := os.Getwd()
	if err != nil {
		return ""
	}
	return cwd
}
