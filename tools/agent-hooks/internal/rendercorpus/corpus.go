// Package rendercorpus records public, deterministic arguments and answers for
// both the Go renderer and sync's registration ownership tests.
package rendercorpus

import (
	"bytes"
	"fmt"

	json "github.com/goccy/go-json/v2"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/registration"
)

// Entry is one command invocation, without the binary and render command names.
type Entry struct {
	Case   string   `json:"case"`
	Args   []string `json:"args"`
	Exit   int      `json:"exit"`
	Stdout string   `json:"stdout"`
	Stderr string   `json:"stderr"`
}

// Generate runs the same entry point as the binary. Cases pin the intended
// exit independently, so a refused path cannot silently become a success.
func Generate() ([]byte, error) {
	var corpus bytes.Buffer
	for _, scenario := range scenarios() {
		var stdout, stderr bytes.Buffer
		exit := registration.Main(scenario.args, &stdout, &stderr)
		if exit != scenario.exit {
			return nil, fmt.Errorf("%s: exit %d, want %d: %s", scenario.name, exit, scenario.exit, &stderr)
		}
		entry := Entry{Case: scenario.name, Args: scenario.args, Exit: exit, Stdout: stdout.String(), Stderr: stderr.String()}
		line, err := json.Marshal(entry)
		if err != nil {
			return nil, err
		}
		corpus.Write(line)
		corpus.WriteByte('\n')
	}
	return corpus.Bytes(), nil
}
