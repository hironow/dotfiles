package launch_test

import (
	"bytes"
	"maps"
	"strings"
	"testing"
	"time"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/fake"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/guardcorpus"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/launch"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/process"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/toolhookcorpus"
)

// fakeRoot stands for the corpus's temporary root in-process.
const fakeRoot = "/fake-root"

func inRoot(text string) string { return strings.ReplaceAll(text, toolhookcorpus.Root, fakeRoot) }

// machineFor is the fake machine of a scenario: it answers from the world the
// generator worked out, and replays the invocations the binary must make.
func machineFor(scenario toolhookcorpus.Scenario, expected toolhookcorpus.Expected) *fake.Machine {
	m := &fake.Machine{
		Programs:    map[string]process.Program{},
		Executable:  map[string]bool{},
		Files:       map[string]bool{},
		Unstartable: map[string]bool{},
		Cwd:         inRoot(scenario.World.Cwd),
	}
	for _, path := range scenario.World.Unstartable {
		m.Unstartable[inRoot(path)] = true
	}
	for name, lookup := range scenario.World.Lookups {
		if lookup != nil {
			m.Programs[name] = process.Program{Path: inRoot(lookup.Path), Relative: lookup.Relative}
		}
	}
	for path, ok := range scenario.World.Executable {
		m.Executable[inRoot(path)] = ok
	}
	for path, ok := range maps.All(scenario.World.RegularFiles) {
		m.Files[inRoot(path)] = ok
	}
	for _, invocation := range expected.Invocations {
		args := make([]string, 0, len(invocation.Args)+1)
		args = append(args, "argv0")
		for _, arg := range invocation.Args {
			args = append(args, inRoot(arg))
		}
		var stdin []byte
		if invocation.Stdin != nil {
			stdin = []byte(inRoot(string(invocation.Stdin)))
		}
		result := process.Result{
			Stdout: []byte(inRoot(string(invocation.Answer.Stdout))),
			Stderr: invocation.Answer.Stderr,
			Exit:   invocation.Answer.Exit,
		}
		if invocation.Combined {
			result = process.Result{Stdout: append(result.Stdout, result.Stderr...), Exit: result.Exit}
		}
		m.Replay = append(m.Replay, fake.Invocation{
			Command: process.Command{
				Path:     inRoot(invocation.Path),
				Args:     args,
				Stdin:    stdin,
				Timeout:  time.Duration(invocation.TimeoutSeconds) * time.Second,
				Combined: invocation.Combined,
			},
			Result:   result,
			AnyArgv0: true,
		})
	}
	return m
}

func TestRunDoesWhatTheToolHooksCorpusExpects(t *testing.T) {
	for hook, scenarios := range map[string][]toolhookcorpus.Scenario{
		"rtk":       toolhookcorpus.RTK(t),
		"formatter": toolhookcorpus.Formatter(t),
	} {
		if len(scenarios) < 30 {
			t.Fatalf("%s: %d scenarios; expected the whole corpus", hook, len(scenarios))
		}
		event := map[string]string{"rtk": "pre", "formatter": "post"}[hook]
		for _, scenario := range scenarios {
			for _, run := range scenario.Runs {
				// The frame says whether the binary runs what the script ran
				// ("parity") or differs on purpose, and why.
				name := guardcorpus.Frame(run.Difference) + "/" + hook + "/" + scenario.Name + "/" + run.Harness
				t.Run(name, func(t *testing.T) {
					m := machineFor(scenario, run.ExpectedGo)
					var stdout, stderr bytes.Buffer
					exit := launch.Run([]string{run.Harness, event, "--hook", hook},
						bytes.NewReader([]byte(inRoot(string(scenario.Stdin)))), &stdout, &stderr, m, &fake.LogSink{})
					where := hook + ".jsonl:" + scenario.Name + " " + run.Harness + " (difference " + run.Difference + ")"
					run.ExpectedGo.Check(t, where, exit, stdout.String(), stderr.String(), inRoot)
					for _, problem := range m.Done() {
						t.Errorf("%s: %s", where, problem)
					}
				})
			}
		}
	}
}
