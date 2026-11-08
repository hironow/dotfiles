//go:build windows

package main

import "os"

// fileOwner has nothing to keep on Windows, where os-bundle does not run.
func fileOwner(os.FileInfo) (uid, gid int, ok bool) { return 0, 0, false }
