//go:build darwin || linux

package launch_test

import (
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"testing"
	"time"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/launch"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/process"
)

const processTreeScript = `#!/bin/sh
if [ "$1" = heartbeat ]; then
  echo $$ >> "$2/pids"
  if [ "$3" = closed ]; then exec </dev/null >/dev/null 2>&1; fi
  printf x >> "$2/heartbeat"
  if [ "$3" = late ]; then
    sleep 0.2
    printf rtk-late-output
    exec </dev/null >/dev/null 2>&1
  fi
  while [ ! -f "$2/stop" ]; do printf x >> "$2/heartbeat"; sleep 0.05; done
fi
echo $$ >> "$1/pids"
child=closed
case "$2" in late|held) child="$2";; post-exit-deadline) child=held;; esac
"$0" heartbeat "$1" "$child" &
while [ ! -s "$1/heartbeat" ]; do sleep 0.01; done
case "$2" in
  deadline) exec sleep 3;;
  held) printf partial-output; printf partial-error >&2;;
  large)
    dd if=/dev/zero bs=1048576 count=1 2>/dev/null
    (dd if=/dev/zero bs=1048576 count=1 2>/dev/null) >&2;;
  ordered) printf A; printf B >&2; printf C;;
esac
exit 0
`

func recordedPIDs(t *testing.T, dir string) []int {
	t.Helper()
	encoded, err := os.ReadFile(filepath.Join(dir, "pids"))
	if err != nil {
		t.Fatal(err)
	}
	var pids []int
	for field := range strings.FieldsSeq(string(encoded)) {
		pid, err := strconv.Atoi(field)
		if err != nil || pid <= 0 {
			t.Fatalf("bad recorded pid %q: %v", field, err)
		}
		pids = append(pids, pid)
	}
	if len(pids) != 2 {
		t.Fatalf("recorded PIDs %v, want parent and descendant", pids)
	}
	return pids
}

func stopProcessTree(t *testing.T, dir string) {
	t.Helper()
	// A failed assertion must still stop the fixture. A file lets it exit
	// without signaling a PID that may already have been reused.
	if err := os.WriteFile(filepath.Join(dir, "stop"), nil, 0o600); err != nil {
		t.Error(err)
	}
	encoded, _ := os.ReadFile(filepath.Join(dir, "pids"))
	until := time.Now().Add(time.Second)
	for field := range strings.FieldsSeq(string(encoded)) {
		pid, _ := strconv.Atoi(field)
		for pid > 0 && syscall.Kill(pid, 0) == nil && time.Now().Before(until) {
			time.Sleep(10 * time.Millisecond)
		}
	}
}

func TestExecMachineLeavesNoDescendant(t *testing.T) {
	// One script for every case, written before the parallel cases start.
	// Written by a case, it could be open for writing in a sibling's fork
	// when this case runs it: "text file busy" (golang/go#22315).
	path := filepath.Join(t.TempDir(), "agent-hook-test")
	if err := os.WriteFile(path, []byte(processTreeScript), 0o700); err != nil {
		t.Fatal(err)
	}
	for _, mode := range []string{"closed", "late", "held", "deadline", "post-exit-deadline", "large", "ordered"} {
		for _, combined := range []bool{false, true} {
			t.Run(fmt.Sprintf("%s/combined=%v", mode, combined), func(t *testing.T) {
				t.Parallel()
				dir := t.TempDir()
				t.Cleanup(func() { stopProcessTree(t, dir) })
				limit := 5 * time.Second
				if mode == "deadline" || mode == "post-exit-deadline" {
					limit = time.Second
				}
				start := time.Now()
				got, err := (launch.ExecMachine{}).Run(process.Command{
					Path: path, Args: []string{path, dir, mode}, Combined: combined, Deadline: start.Add(limit),
				})
				switch mode {
				case "closed", "large", "ordered":
					if time.Since(start) >= time.Second {
						t.Errorf("%s returned after %s, want under 1 s", mode, time.Since(start))
					}
				}
				if mode == "deadline" || mode == "post-exit-deadline" {
					if !errors.Is(err, context.DeadlineExceeded) || time.Since(start) > limit+300*time.Millisecond {
						t.Errorf("deadline took %s: %v", time.Since(start), err)
					}
				} else if mode == "held" {
					if !errors.Is(err, exec.ErrWaitDelay) || len(got.Stdout) != 0 || len(got.Stderr) != 0 {
						t.Errorf("held pipe: result %+v, error %v; want WaitDelay and no output", got, err)
					}
				} else if err != nil || got.Exit != 0 || got.Signaled {
					t.Errorf("Run = exit %d, signaled %v, error %v", got.Exit, got.Signaled, err)
				}
				switch mode {
				case "large":
					wantOut, wantErr := 1<<20, 1<<20
					if combined {
						wantOut, wantErr = 2<<20, 0
					}
					if len(got.Stdout) != wantOut || len(got.Stderr) != wantErr {
						t.Errorf("output lengths %d, %d; want %d, %d", len(got.Stdout), len(got.Stderr), wantOut, wantErr)
					}
				case "ordered":
					wantOut, wantErr := "AC", "B"
					if combined {
						wantOut, wantErr = "ABC", ""
					}
					if string(got.Stdout) != wantOut || string(got.Stderr) != wantErr {
						t.Errorf("output %q, %q; want %q, %q", got.Stdout, got.Stderr, wantOut, wantErr)
					}
				case "late":
					if string(got.Stdout) != "rtk-late-output" {
						t.Errorf("late output = %q", got.Stdout)
					}
				}
				assertProcessTreeStopped(t, dir)
			})
		}
	}
}

func assertProcessTreeStopped(t *testing.T, dir string) {
	t.Helper()
	for _, pid := range recordedPIDs(t, dir) {
		until := time.Now().Add(time.Second)
		for syscall.Kill(pid, 0) == nil && time.Now().Before(until) {
			time.Sleep(10 * time.Millisecond)
		}
		if err := syscall.Kill(pid, 0); !errors.Is(err, syscall.ESRCH) {
			t.Errorf("process %d remains after Run: %v", pid, err)
		}
	}
	before, err := os.Stat(filepath.Join(dir, "heartbeat"))
	if err != nil {
		t.Fatal(err)
	}
	time.Sleep(time.Second)
	after, err := os.Stat(filepath.Join(dir, "heartbeat"))
	if err != nil || before.Size() != after.Size() || !before.ModTime().Equal(after.ModTime()) {
		t.Errorf("descendant kept touching the file: %v", err)
	}
}
