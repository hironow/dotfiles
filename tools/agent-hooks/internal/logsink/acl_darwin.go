//go:build darwin

package logsink

import (
	"encoding/binary"
	"errors"
	"fmt"
	"os"
	"syscall"
	"unsafe"
)

// macOS checks a file's ACL before its mode bits: an entry that allows
// another user reaches past 0600 and 0700, and a directory's inheritable
// entries pass to everything made in it. So the sink removes any ACL from the
// directories and files it checks, through their open handles, and then reads
// that none is left. The standard library has no call for ACLs, so these are
// the raw fstat64_extended and fchmod_extended system calls, which Go makes
// through libc's deprecated syscall(2). Should a later macOS drop that, every
// call fails, the sink logs nothing, and the macOS CI job shows it.
//
// The mode and the ACL change in one fchmod_extended call: a deny entry may
// be all that guards a loose mode, and removing it before the mode narrowed
// would open the file in between.

const (
	// kauthNone is KAUTH_UID_NONE (and KAUTH_GID_NONE): fchmod_extended
	// leaves the owner and the group as they are.
	kauthNone = 1<<32 - 1 - 100
	// removeACL is _FILESEC_REMOVE_ACL.
	removeACL = 1
	// filesecHeader is the size of a kauth_filesec with no ACL entry: the
	// magic, the owner's and the group's GUIDs, the entry count, the flags.
	filesecHeader = 44
	// filesecMagic is KAUTH_FILESEC_MAGIC, and noACL KAUTH_FILESEC_NOACL,
	// the entry count of a file with no ACL.
	filesecMagic = 0x012cc16d
	noACL        = 0xffffffff
)

var (
	errACLStays     = errors.New("an ACL stays on the file after it was removed")
	errFilesecShape = errors.New("the file's security is not in the form expected")
)

// restrict leaves the open file to its owner: when group or others have any
// permission (mode is its mode now), its mode becomes private; and any ACL
// goes. Both happen in one call, and then the sink reads that no ACL is left.
// A file that needs neither is left as it is.
func restrict(file *os.File, mode, private os.FileMode) error {
	has, err := hasACL(file)
	if err != nil {
		return err
	}
	target := mode.Perm()
	if target&0o077 != 0 {
		target = private
	}
	if !has && target == mode.Perm() {
		return nil
	}
	err = control(file, func(fd uintptr) syscall.Errno {
		_, _, errno := syscall.Syscall6(syscall.SYS_FCHMOD_EXTENDED, fd, kauthNone, kauthNone, uintptr(target), removeACL, 0)
		return errno
	})
	if err != nil {
		return fmt.Errorf("narrow the mode and remove the ACL: %w", err)
	}
	if has, err = hasACL(file); err != nil || has {
		return errors.Join(errACLStays, err)
	}
	return nil
}

// hasACL reads the open file's security with fstat64_extended (whose stat is
// syscall.Stat_t's layout), and reports whether it holds an ACL entry.
func hasACL(file *os.File) (bool, error) {
	var stat syscall.Stat_t
	var filesec [filesecHeader]byte
	size := uintptr(len(filesec))
	err := control(file, func(fd uintptr) syscall.Errno {
		// Audited: the pointers are to this function's own variables, which
		// stay alive through the call, and the kernel writes at most size
		// bytes of the filesec.
		_, _, errno := syscall.Syscall6(syscall.SYS_FSTAT64_EXTENDED, fd,
			uintptr(unsafe.Pointer(&stat)),       //nolint:gosec // G103: audited above
			uintptr(unsafe.Pointer(&filesec[0])), //nolint:gosec // G103: audited above
			uintptr(unsafe.Pointer(&size)),       //nolint:gosec // G103: audited above
			0, 0)
		return errno
	})
	if err != nil {
		return false, fmt.Errorf("read the ACL: %w", err)
	}
	switch {
	case size == 0: // no extended security at all
		return false, nil
	case size > filesecHeader: // entries, which the kernel did not copy for want of room
		return true, nil
	case size < filesecHeader:
		return false, errFilesecShape
	}
	magic := binary.NativeEndian.Uint32(filesec[0:4])
	count := binary.NativeEndian.Uint32(filesec[36:40])
	if magic != filesecMagic || (count != noACL && count != 0) {
		return false, errFilesecShape
	}
	return false, nil
}

// control runs a raw system call on the open file's descriptor.
func control(file *os.File, call func(fd uintptr) syscall.Errno) error {
	raw, err := file.SyscallConn()
	if err != nil {
		return err
	}
	var errno syscall.Errno
	if err := raw.Control(func(fd uintptr) { errno = call(fd) }); err != nil {
		return err
	}
	if errno != 0 {
		return errno
	}
	return nil
}
