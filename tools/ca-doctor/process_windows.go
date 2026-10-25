package main

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"syscall"
	"time"
	"unsafe"
)

var procGetSystemDirectory = syscall.NewLazyDLL("kernel32.dll").NewProc("GetSystemDirectoryW")

func configureProcess(cmd *exec.Cmd) {
	cmd.Cancel = func() error {
		cleanupProcess(cmd)
		if cmd.Process == nil {
			return os.ErrProcessDone
		}
		return cmd.Process.Kill()
	}
}

// systemTaskkill is taskkill.exe in the system directory Windows reports, not
// in whatever folder an inherited SystemRoot names.
func systemTaskkill() (string, bool) {
	buf := make([]uint16, syscall.MAX_PATH)
	n, _, _ := procGetSystemDirectory.Call(uintptr(unsafe.Pointer(&buf[0])), uintptr(len(buf)))
	if n == 0 || n >= uintptr(len(buf)) {
		return "", false
	}
	return filepath.Join(syscall.UTF16ToString(buf[:n]), "taskkill.exe"), true
}

// Native probes do not spawn children. For native PATH shims, make a bounded
// best-effort tree cleanup too. WaitDelay is the hard pipe-drain bound even
// when System32/taskkill is unavailable or the parent already exited.
func cleanupProcess(cmd *exec.Cmd) {
	if cmd.Process == nil {
		return
	}
	taskkill, ok := systemTaskkill()
	if !ok {
		return
	}
	ctx, cancel := context.WithTimeout(context.Background(), 300*time.Millisecond)
	defer cancel()
	// Audited: the binary is the system directory's taskkill.exe from the
	// Windows API, not the environment, and the only varying argument is a
	// numeric pid.
	// nosemgrep: go.lang.security.audit.dangerous-exec-command.dangerous-exec-command
	kill := exec.CommandContext(ctx, taskkill, "/PID", strconv.Itoa(cmd.Process.Pid), "/T", "/F") //nolint:gosec // G204: audited above
	kill.WaitDelay = 100 * time.Millisecond
	_ = kill.Run()
}
