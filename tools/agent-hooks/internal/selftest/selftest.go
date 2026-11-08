// Package selftest holds the binary's own cases: payloads it must answer
// exactly as recorded, run through launch.Run on the in-memory machine
// (internal/fake), whose programs are replayed and never run. A release runs
// them before any registration names it (`agent-hook selftest`), so that a
// release whose definitions, answer templates, or hooks answer otherwise
// never reaches a harness. A selftest runs no program and writes no log.
package selftest

import (
	"bytes"
	"fmt"
	"strings"
	"time"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/launch"
)

// Run answers every case and returns how many it checked, or an error naming
// the first case that answered otherwise.
func Run() (int, error) {
	for i, c := range Cases() {
		if err := check(c, answers[c.Name]); err != nil {
			return i, err
		}
	}
	return len(Cases()), nil
}

// check runs one case on a fresh machine and compares its answer.
func check(c Case, want answer) error {
	machine := c.Machine()
	var stdout, stderr bytes.Buffer
	exit := launch.Run(c.Args, strings.NewReader(c.Payload), &stdout, &stderr, machine, discard{})
	got := answer{exit: exit, stdout: stdout.String(), stderr: stderr.String()}
	if got != want {
		return fmt.Errorf("%s: answered exit %d, stdout %q, stderr %q; recorded exit %d, stdout %q, stderr %q",
			c.Name, got.exit, got.stdout, got.stderr, want.exit, want.stdout, want.stderr)
	}
	// A hook that did not ask its programs what the case records answered
	// from something else, even when the answer matches.
	if problems := machine.Done(); len(problems) > 0 {
		return fmt.Errorf("%s: %s", c.Name, strings.Join(problems, "; "))
	}
	return nil
}

// discard is a log sink that keeps nothing: a selftest writes no log.
type discard struct{}

func (discard) Salt() ([]byte, bool)          { return nil, false }
func (discard) Write(time.Time, []byte) error { return nil }
