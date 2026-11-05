// Command agent-hook runs one of the dotfiles agent hooks for one harness:
//
//	agent-hook <harness> <event> --hook <id>
//
// It reads the harness's hook payload from stdin and answers as that harness
// reads an answer (exit code, stdout, stderr). Each run then logs one line of
// fixed values to the file log under the state directory. `agent-hook log`
// prints the recent lines:
//
//	agent-hook log [--days N]
package main

import (
	"os"
	"time"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/launch"
)

func main() {
	if len(os.Args) > 1 && os.Args[1] == "log" {
		os.Exit(printLog(os.Args[2:], os.Stdout, os.Stderr, os.LookupEnv, time.Now()))
	}
	os.Exit(launch.Run(os.Args[1:], os.Stdin, os.Stdout, os.Stderr, launch.ExecMachine{}, &fileLog{}))
}
