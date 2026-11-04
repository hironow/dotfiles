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
	"slices"

	json "github.com/goccy/go-json/v2"

	agenthooks "github.com/hironow/dotfiles/tools/agent-hooks"
	"github.com/hironow/dotfiles/tools/agent-hooks/harnesses"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/commandguard"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/definition"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/fileguard"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/process"
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
	// LookPath finds a program on PATH as the old scripts did (process.Search).
	LookPath(name string) (process.Program, bool)
	// IsExecutable is access(2) with X_OK, as Python's os.access.
	IsExecutable(path string) bool
	// IsRegularFile is bash's `[ -f path ]`: a regular file, through symlinks.
	IsRegularFile(path string) bool
	// Getwd is the physical working directory, as Python's os.getcwd.
	Getwd() string
	// IsWindows reports whether paths follow Windows' rules here (the
	// scripts' Path(...) did), as on Windows.
	IsWindows() bool
	// Run runs a command in this process's working directory and environment.
	// The error is a command that could not start or ran out of time.
	Run(command process.Command) (process.Result, error)
}

// hook decides on one call.
type hook func(call ir.Call, machine Machine) ir.Outcome

// hooks are the hooks the binary runs, by id; manifest.json says which event
// each runs on and how it fails.
var hooks = map[string]hook{
	"command-guard": commandGuard,
	"files-guard":   filesGuard,
	"secrets-guard": secretsGuard,
	"rtk":           rtkHook,
	"formatter":     formatterHook,
}

// hookSpec is one hook of manifest.json.
type hookSpec struct {
	ID      string `json:"id"`
	Event   string `json:"event"`
	Failure string `json:"failure"`
}

// The failure modes of manifest.json.
const (
	failClosed = "closed" // input the hook cannot read blocks the call
	failOpen   = "open"   // input the hook cannot read lets the call go on
)

// manifest reads manifest.json.
func manifest() ([]hookSpec, error) {
	var file struct {
		Hooks []hookSpec `json:"hooks"`
	}
	if err := json.Unmarshal(agenthooks.Manifest, &file, json.RejectUnknownMembers(true)); err != nil {
		return nil, fmt.Errorf("manifest.json: %w", err)
	}
	for _, spec := range file.Hooks {
		if spec.Failure != failClosed && spec.Failure != failOpen {
			return nil, fmt.Errorf("manifest.json: hook %s has failure mode %q", spec.ID, spec.Failure)
		}
	}
	return file.Hooks, nil
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
	event, spec, decide, err := parse(args, hooks)
	if err != nil {
		_, _ = fmt.Fprintf(stderr, "agent-hook: %v\n%s\n", err, usage)
		return exitUsage
	}
	// A guard blocks input it cannot read; rtk and the formatter let it go on
	// and run nothing, as their scripts failed open.
	outcome := ir.Outcome{}
	if spec.Failure == failClosed {
		outcome = unreadable
	}
	if payload, err := io.ReadAll(stdin); err == nil {
		if call, err := event.Decode(payload); err == nil {
			call.Native = payload
			var failure any
			if outcome, failure = decideSafely(decide, call, machine); failure != nil {
				_, _ = fmt.Fprintf(stderr, "agent-hook: the %s hook failed, so the call goes on: %v\n", spec.ID, failure)
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

// parse reads the arguments: the harness, the event, and --hook, which must
// name a hook of the manifest for that event.
func parse(args []string, hooks map[string]hook) (definition.Event, hookSpec, hook, error) {
	if len(args) < 2 {
		return definition.Event{}, hookSpec{}, nil, errors.New("a harness and an event are needed")
	}
	flags := flag.NewFlagSet("agent-hook", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	id := flags.String("hook", "", "the hook to run")
	if err := flags.Parse(args[2:]); err != nil {
		return definition.Event{}, hookSpec{}, nil, err
	}
	if flags.NArg() > 0 {
		return definition.Event{}, hookSpec{}, nil, fmt.Errorf("unexpected argument %q", flags.Arg(0))
	}
	specs, err := manifest()
	if err != nil {
		return definition.Event{}, hookSpec{}, nil, err
	}
	at := slices.IndexFunc(specs, func(s hookSpec) bool { return s.ID == *id })
	decide, ok := hooks[*id]
	if at < 0 || !ok {
		return definition.Event{}, hookSpec{}, nil, fmt.Errorf("no hook %q", *id)
	}
	spec := specs[at]
	if spec.Event != args[1] {
		return definition.Event{}, hookSpec{}, nil, fmt.Errorf("hook %s runs on %s, not %s", spec.ID, spec.Event, args[1])
	}
	def, err := definition.Load(harnesses.FS, args[0])
	if err != nil {
		return definition.Event{}, hookSpec{}, nil, fmt.Errorf("no harness %q: %w", args[0], err)
	}
	event, ok := def.Event(args[1])
	if !ok {
		return definition.Event{}, hookSpec{}, nil, fmt.Errorf("harness %s has no event %q", args[0], args[1])
	}
	return event, spec, decide, nil
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
