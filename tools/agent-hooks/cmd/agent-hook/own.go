package main

import (
	"fmt"
	"io"
	"runtime"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/logline"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/selftest"
)

// printVersion is `agent-hook version`: the release ID the build was given
// (logline.Release, "dev" for a plain build) and the Go version it was built
// with. The release build (hookrelease) checks it.
func printVersion(args []string, stdout, stderr io.Writer) int {
	if len(args) > 0 {
		_, _ = fmt.Fprintln(stderr, "usage: agent-hook version")
		return exitUsage
	}
	_, _ = fmt.Fprintf(stdout, "agent-hook %s %s\n", logline.Release, runtime.Version())
	return 0
}

// runSelftest is `agent-hook selftest`: the binary answers its own cases
// (internal/selftest), with no program run and nothing logged. A release
// passes it before any registration names it.
func runSelftest(args []string, stdout, stderr io.Writer) int {
	if len(args) > 0 {
		_, _ = fmt.Fprintln(stderr, "usage: agent-hook selftest")
		return exitUsage
	}
	n, err := selftest.Run()
	if err != nil {
		_, _ = fmt.Fprintf(stderr, "agent-hook selftest: %v\n", err)
		return 1
	}
	_, _ = fmt.Fprintf(stdout, "agent-hook selftest: %d cases pass\n", n)
	return 0
}
