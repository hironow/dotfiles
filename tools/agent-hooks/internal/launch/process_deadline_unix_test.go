//go:build !windows

package launch_test

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/launch"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/process"
)

func TestExecMachineHonorsTheEarlierCommandLimit(t *testing.T) {
	for _, timeoutFirst := range []bool{false, true} {
		t.Run(map[bool]string{false: "stage deadline", true: "command timeout"}[timeoutFirst], func(t *testing.T) {
			deadline, timeout := 60*time.Millisecond, time.Second
			if timeoutFirst {
				deadline, timeout = timeout, deadline
			}
			start := time.Now()
			_, err := (launch.ExecMachine{}).Run(process.Command{
				Path: "/bin/sh", Args: []string{"sh", "-c", "exec sleep 0.4"},
				Deadline: start.Add(deadline), Timeout: timeout,
			})
			if !errors.Is(err, context.DeadlineExceeded) || time.Since(start) > 300*time.Millisecond {
				t.Errorf("Run took %s, error %v; want the earlier deadline", time.Since(start), err)
			}
		})
	}
}
