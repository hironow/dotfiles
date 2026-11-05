//go:build unix && !darwin

package logsink

import "os"

// restrict leaves the open file to its owner: when group or others have any
// permission (mode is its mode now), its mode becomes private. On Linux, a
// POSIX ACL's named entries are bounded by its mask, which is the mode's
// group bits, so that leaves them nothing. The sink runs on no other Unix.
func restrict(file *os.File, mode, private os.FileMode) error {
	if mode.Perm()&0o077 == 0 {
		return nil
	}
	return file.Chmod(private)
}
