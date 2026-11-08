//go:build !windows && !darwin && !linux

package launch

import (
	"errors"
	"os"
	"testing"
	"time"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/process"
)

func TestUnsupportedUnixCommandsFail(t *testing.T) {
	if err := waitExit(os.Getpid()); !errors.Is(err, errors.ErrUnsupported) {
		t.Errorf("waitExit = %v, want unsupported", err)
	}
	got, err := (ExecMachine{}).Run(process.Command{
		Path: "/bin/sh", Args: []string{"sh", "-c", "printf partial; exit 0"}, Timeout: time.Second,
	})
	if !errors.Is(err, errors.ErrUnsupported) || len(got.Stdout) != 0 || len(got.Stderr) != 0 {
		t.Errorf("Run = %+v, %v; want unsupported and no output", got, err)
	}
}
