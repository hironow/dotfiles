package launch

import (
	"context"
	"os/exec"
	"time"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/fileguard"
)

// basenameProbeTimeout bounds `basename --version`, which answers at once.
const basenameProbeTimeout = 5 * time.Second

// ExecMachine is the machine this process runs on, reached with os/exec.
type ExecMachine struct{}

// Basename runs `basename --version` from PATH, as the shell guard would find
// basename(1). Only GNU's takes --version; any failure, including no basename
// on PATH, reads as BSD's.
func (ExecMachine) Basename() fileguard.Basename {
	ctx, cancel := context.WithTimeout(context.Background(), basenameProbeTimeout)
	defer cancel()
	if exec.CommandContext(ctx, "basename", "--version").Run() == nil {
		return fileguard.GNUBasename
	}
	return fileguard.BSDBasename
}
