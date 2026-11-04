//go:build !windows

package launch

import (
	"os"
	"syscall"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/process"
)

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

// Getwd is the physical working directory, as Python's os.getcwd: the
// kernel's, never $PWD's spelling of it.
func (ExecMachine) Getwd() string {
	cwd, err := syscall.Getwd()
	if err != nil {
		return ""
	}
	return cwd
}
