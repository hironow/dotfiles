//go:build unix && !darwin

package logsink

import "os"

// clearACL does nothing here. On Linux, a POSIX ACL's named entries are
// bounded by its mask, which is the mode's group bits, so the 0600 and 0700
// the sink keeps leave them nothing. The sink runs on no other Unix.
func clearACL(*os.File) error { return nil }
