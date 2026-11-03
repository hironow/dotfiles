// Command agent-hook runs one of the dotfiles agent hooks for one harness:
//
//	agent-hook <harness> <event> --hook <id>
//
// It reads the harness's hook payload from stdin and answers as that harness
// reads an answer (exit code, stdout, stderr).
package main

import (
	"os"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/launch"
)

func main() {
	os.Exit(launch.Run(os.Args[1:], os.Stdin, os.Stdout, os.Stderr, launch.ExecMachine{}))
}
