//go:build !windows

package main

import "testing"

// Only Windows opens a window for a console program, so elsewhere the
// launcher refuses instead of pretending to hide anything.
func TestRunRefusesOffWindows(t *testing.T) {
	if got := run([]string{"true"}); got != 2 {
		t.Fatalf("run(true) = %d, want 2", got)
	}
}
