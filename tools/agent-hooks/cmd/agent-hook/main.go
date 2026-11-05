// Command agent-hook runs one of the dotfiles agent hooks for one harness:
//
//	agent-hook <harness> <event> --hook <id>
//
// It reads the harness's hook payload from stdin and answers as that harness
// reads an answer (exit code, stdout, stderr). Each run then logs one line of
// fixed values to the file log under the state directory. The binary's own
// commands:
//
//	agent-hook log [--days N]   the recent log lines
//	agent-hook version          the release ID and the Go version
//	agent-hook selftest         the binary's own cases (internal/selftest)
package main

import (
	"os"
	"time"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/launch"
)

func main() {
	if len(os.Args) > 1 {
		switch os.Args[1] {
		case "log":
			os.Exit(printLog(os.Args[2:], os.Stdout, os.Stderr, os.LookupEnv, time.Now()))
		case "version":
			os.Exit(printVersion(os.Args[2:], os.Stdout, os.Stderr))
		case "selftest":
			os.Exit(runSelftest(os.Args[2:], os.Stdout, os.Stderr))
		}
	}
	os.Exit(launch.Run(os.Args[1:], os.Stdin, os.Stdout, os.Stderr, launch.ExecMachine{}, &fileLog{}))
}
