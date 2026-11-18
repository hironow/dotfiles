package main

import "testing"

// Without a program there is nothing to start: a usage error, on every OS.
func TestRunWithoutAProgramIsAUsageError(t *testing.T) {
	if got := run(nil); got != 2 {
		t.Fatalf("run(nil) = %d, want 2", got)
	}
}
