//go:build !windows

package main

import (
	"os"
	"syscall"
)

// fileOwner is the uid and gid of a file, so a replaced bundle keeps them.
func fileOwner(info os.FileInfo) (uid, gid int, ok bool) {
	stat, ok := info.Sys().(*syscall.Stat_t)
	if !ok {
		return 0, 0, false
	}
	return int(stat.Uid), int(stat.Gid), true
}
