//go:build !windows && !darwin && !linux

package launch

import (
	"errors"
	"fmt"
)

// waitExit refuses platforms without a watcher that reserves the leader's PID.
func waitExit(pid int) error {
	return fmt.Errorf("watch process %d without reaping: %w", pid, errors.ErrUnsupported)
}
