//go:build darwin || linux

package launch

import (
	"syscall"
	"unsafe"
)

// waitExit reserves the leader's PID until the owner reaps it.
func waitExit(pid int) error {
	var siginfo [16]uint64
	for {
		// Audited: siginfo is a zeroed, aligned 128-byte buffer owned here.
		// It stays alive while waitid writes it. WNOWAIT leaves the PID reserved.
		_, _, errno := syscall.Syscall6(syscall.SYS_WAITID, 1, uintptr(pid),
			uintptr(unsafe.Pointer(&siginfo[0])), //nolint:gosec // G103: audited above
			4|waitNoReap, 0, 0)
		if errno == syscall.EINTR {
			continue
		}
		if errno != 0 {
			return errno
		}
		return nil
	}
}
