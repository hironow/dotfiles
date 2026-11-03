// Package launch is the binary's shell. It reads the arguments and the
// payload, decodes the payload with the harness's definition, runs one hook,
// and writes the harness's answer. The hooks themselves are pure; the machine
// is reached only through the Machine port.
package launch

import (
	"errors"
	"flag"
	"fmt"
	"io"

	"github.com/hironow/dotfiles/tools/agent-hooks/harnesses"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/commandguard"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/definition"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/fileguard"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/secretguard"
)

// The exit codes of the binary's own failures (sysexits.h). The harness's
// answer sets every other exit code.
const (
	exitUsage    = 64 // an argument the binary does not know
	exitSoftware = 70 // the answer could not be rendered or written
)

const usage = "usage: agent-hook <harness> <event> --hook <id>"

// Machine is what the hooks need from the machine they run on.
type Machine interface {
	// Basename is the flavor of basename(1) the shell guard would run here.
	Basename() fileguard.Basename
}

// hook decides on one call.
type hook func(call ir.Call, machine Machine) ir.Outcome

// hooks are the hooks the binary runs, by id.
var hooks = map[string]hook{
	"command-guard": commandGuard,
	"files-guard":   filesGuard,
	"secrets-guard": secretsGuard,
}

// unreadable is the outcome for a payload that is not one JSON value: no
// guard can read it, so none runs, and the call is blocked.
var unreadable = ir.Outcome{
	Action: ir.Block,
	Rule:   "input.unreadable",
	Reason: "agent-hook could not read the hook input as one JSON value, so no guard ran.",
}

// Run runs the binary with its arguments (without the program's name):
// agent-hook <harness> <event> --hook <id>. It reads the payload from stdin,
// writes the harness's answer to stdout and stderr, and returns the exit code.
func Run(args []string, stdin io.Reader, stdout, stderr io.Writer, machine Machine) int {
	return run(args, stdin, stdout, stderr, machine, hooks)
}

func run(args []string, stdin io.Reader, stdout, stderr io.Writer, machine Machine, hooks map[string]hook) int {
	event, id, decide, err := parse(args, hooks)
	if err != nil {
		_, _ = fmt.Fprintf(stderr, "agent-hook: %v\n%s\n", err, usage)
		return exitUsage
	}
	outcome := unreadable
	if payload, err := io.ReadAll(stdin); err == nil {
		if call, err := event.Decode(payload); err == nil {
			var failure any
			if outcome, failure = decideSafely(decide, call, machine); failure != nil {
				_, _ = fmt.Fprintf(stderr, "agent-hook: the %s hook failed, so the call goes on: %v\n", id, failure)
			}
		}
	}
	answer, err := event.Answer(outcome)
	if err != nil {
		_, _ = fmt.Fprintf(stderr, "agent-hook: cannot render the answer: %v\n", err)
		return exitSoftware
	}
	if _, err := io.WriteString(stdout, answer.Stdout); err != nil {
		return exitSoftware
	}
	if _, err := io.WriteString(stderr, answer.Stderr); err != nil {
		return exitSoftware
	}
	return answer.Exit
}

// parse reads the arguments: the harness, the event, and --hook.
func parse(args []string, hooks map[string]hook) (definition.Event, string, hook, error) {
	if len(args) < 2 {
		return definition.Event{}, "", nil, errors.New("a harness and an event are needed")
	}
	flags := flag.NewFlagSet("agent-hook", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	id := flags.String("hook", "", "the hook to run")
	if err := flags.Parse(args[2:]); err != nil {
		return definition.Event{}, "", nil, err
	}
	if flags.NArg() > 0 {
		return definition.Event{}, "", nil, fmt.Errorf("unexpected argument %q", flags.Arg(0))
	}
	decide, ok := hooks[*id]
	if !ok {
		return definition.Event{}, "", nil, fmt.Errorf("no hook %q", *id)
	}
	def, err := definition.Load(harnesses.FS, args[0])
	if err != nil {
		return definition.Event{}, "", nil, fmt.Errorf("no harness %q: %w", args[0], err)
	}
	event, ok := def.Event(args[1])
	if !ok {
		return definition.Event{}, "", nil, fmt.Errorf("harness %s has no event %q", args[0], args[1])
	}
	return event, *id, decide, nil
}

// decideSafely runs a hook. A hook that panics passes the call, as the old
// guards' internal exceptions did; the panic is returned to be told.
func decideSafely(decide hook, call ir.Call, machine Machine) (outcome ir.Outcome, failure any) {
	defer func() {
		if failure = recover(); failure != nil {
			outcome = ir.Outcome{}
		}
	}()
	return decide(call, machine), nil
}

func commandGuard(call ir.Call, _ Machine) ir.Outcome {
	command, ok := commandguard.CommandOf(call)
	if !ok {
		return ir.Outcome{}
	}
	return commandguard.Check(command)
}

func filesGuard(call ir.Call, machine Machine) ir.Outcome {
	paths := fileguard.Paths(call)
	flavor := fileguard.BSDBasename // the flavors read these paths alike
	if fileguard.NeedsBasename(paths) {
		flavor = machine.Basename()
	}
	return fileguard.Check(paths, flavor)
}

func secretsGuard(call ir.Call, _ Machine) ir.Outcome {
	return secretguard.Check(secretguard.Contents(call))
}
