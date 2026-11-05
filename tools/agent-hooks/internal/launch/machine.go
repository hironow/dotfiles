package launch

import (
	"context"
	"errors"
	"io/fs"
	"os"
	"path/filepath"
	"runtime"
	"time"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/osrand"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/process"
)

// waitDelay bounds how long a command's output pipes may stay open after it
// exits or is killed (a child it left behind may hold them).
const waitDelay = 2 * time.Second

// ExecMachine is the machine this process runs on, reached with os/exec.
type ExecMachine struct{}

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

// Now is time.Now.
func (ExecMachine) Now() time.Time { return time.Now() }

// Random fills p with OS randomness without crashing on failure.
func (ExecMachine) Random(p []byte) error { return osrand.Read(p) }

// LookupEnv is os.LookupEnv: the variable's value, and whether it is set.
func (ExecMachine) LookupEnv(name string) (string, bool) { return os.LookupEnv(name) }

func commandContext(command process.Command) (context.Context, context.CancelFunc) {
	deadline := command.Deadline
	if command.Timeout > 0 {
		timeout := time.Now().Add(command.Timeout)
		if deadline.IsZero() || timeout.Before(deadline) {
			deadline = timeout
		}
	}
	if !deadline.IsZero() {
		return context.WithDeadline(context.Background(), deadline)
	}
	return context.WithCancel(context.Background())
}
