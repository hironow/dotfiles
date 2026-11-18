//go:build !windows

package main

import (
	"fmt"
	"os"
)

// run refuses: only Windows opens a window for a console program, so there
// is nothing to hide anywhere else.
func run([]string) int {
	fmt.Fprintln(os.Stderr, "run-hidden: Windows only")
	return 2
}
