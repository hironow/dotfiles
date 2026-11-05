// Package launch is the binary's shell. It reads the arguments and the
// payload, decodes the payload with the harness's definition, runs one hook,
// writes the harness's answer, and then logs the run (one line, through the
// logsink.Sink port). The hooks themselves are pure; the machine is reached
// only through the Machine port.
package launch

import (
	"bytes"
	"errors"
	"flag"
	"fmt"
	"io"
	"maps"
	"slices"
	"time"

	json "github.com/goccy/go-json/v2"

	agenthooks "github.com/hironow/dotfiles/tools/agent-hooks"
	"github.com/hironow/dotfiles/tools/agent-hooks/harnesses"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/commandguard"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/definition"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/fileguard"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/logline"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/logsink"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/pipath"
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

// logDeadline bounds the logging after the answer: the salt, the random ids,
// the validation, the write, and the cleanup. It is far under every harness's
// hook timeout, so that a stuck sink never turns a run into a timeout.
const logDeadline = 250 * time.Millisecond

// Machine is what the hooks need from the machine they run on.
type Machine interface {
	// LookPath finds a program on PATH as the old scripts did (process.Search).
	LookPath(name string) (process.Program, bool)
	// IsExecutable is access(2) with X_OK, as Python's os.access.
	IsExecutable(path string) bool
	// IsRegularFile is bash's `[ -f path ]`: a regular file, through symlinks.
	IsRegularFile(path string) bool
	// Getwd is the physical working directory, as Python's os.getcwd.
	Getwd() string
	// LookupEnv is a variable of this process's environment, and whether it
	// is set.
	LookupEnv(name string) (string, bool)
	// HomeDir is the home directory as Node's os.homedir() finds it, which is
	// how Pi expands ~: $HOME when it is set, even to "", else the password
	// entry. ok is false when neither names one.
	HomeDir() (string, bool)
	// IsWindows reports whether paths follow Windows' rules here (the
	// scripts' Path(...) did), as on Windows.
	IsWindows() bool
	// RealPath is an absolute path with every symlink followed.
	RealPath(path string) (string, error)
	// Exists reports whether there is an entry at the path, not following a
	// final symlink; the error is a lookup that could not finish.
	Exists(path string) (bool, error)
	// Run runs a command in this process's environment, and in its working
	// directory unless the command names one. The error is a command that
	// could not start or ran out of time.
	Run(command process.Command) (process.Result, error)
	// Now is the time, for the log: when the run started and ended.
	Now() time.Time
	// Random fills p with OS randomness, returning an error on failure.
	Random(p []byte) error
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
	ID              string `json:"id"`
	Event           string `json:"event"`
	Failure         string `json:"failure"`
	DeadlineSeconds int    `json:"deadlineSeconds"`
}

// The failure modes of manifest.json.
const (
	failClosed = "closed" // input the hook cannot read blocks the call
	failOpen   = "open"   // input the hook cannot read lets the call go on
)

// manifest reads manifest.json.
func manifest() ([]hookSpec, error) {
	return decodeManifest(agenthooks.Manifest)
}

func decodeManifest(encoded []byte) ([]hookSpec, error) {
	var file struct {
		Hooks []hookSpec `json:"hooks"`
	}
	if err := json.Unmarshal(encoded, &file, json.RejectUnknownMembers(true)); err != nil {
		return nil, fmt.Errorf("manifest.json: %w", err)
	}
	for _, spec := range file.Hooks {
		if spec.DeadlineSeconds <= 0 || uint64(spec.DeadlineSeconds) > uint64((1<<63-1)/time.Second) {
			return nil, fmt.Errorf("manifest.json: hook %s needs a positive deadline in seconds that fits a duration", spec.ID)
		}
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
	Rule:   ir.RuleInputUnreadable,
	Reason: "agent-hook could not read the hook input as one JSON value, so no guard ran.",
}

// Run runs the binary with its arguments (without the program's name):
// agent-hook <harness> <event> --hook <id>. It reads the payload from stdin,
// writes the harness's answer to stdout and stderr, logs the run to the sink,
// and returns the exit code. Logging never changes the answer or the exit
// code.
func Run(args []string, stdin io.Reader, stdout, stderr io.Writer, machine Machine, sink logsink.Sink) int {
	return run(args, stdin, stdout, stderr, machine, sink, hooks)
}

func run(args []string, stdin io.Reader, stdout, stderr io.Writer, machine Machine, sink logsink.Sink,
	hooks map[string]hook,
	stageLimit ...time.Duration,
) int {
	started := time.Now()
	start := machine.Now()
	firing := logline.Firing{}
	if len(args) > 0 {
		firing.Harness = args[0]
	}
	event, spec, decide, err := parse(args, hooks)
	if err != nil {
		_, _ = fmt.Fprintf(stderr, "agent-hook: %v\n%s\n", err, usage)
		firing.Usage, firing.Error = true, logline.ErrUsage
		logRun(sink, firing, nil, machine.Now(), machine)
		return exitUsage
	}
	firing.Event, firing.Hook = args[1], spec.ID
	limit := time.Duration(spec.DeadlineSeconds) * time.Second
	if len(stageLimit) > 0 {
		limit = stageLimit[0]
	}
	deadline := started.Add(limit)
	worker := make(chan stageAnswer, 1)
	go func() {
		worker <- decideStage(event, spec, decide, stdin, stageMachine{Machine: machine, deadline: deadline})
	}()
	timer := time.NewTimer(time.Until(deadline))
	defer timer.Stop()
	var answered stageAnswer
	var checked *validation
	timedOut := false
	finished := false
	select {
	case answered = <-worker:
		finished = true
		timedOut = !time.Now().Before(deadline)
	case <-timer.C:
		timedOut = true
	}
	if timedOut {
		firing.Error = logline.ErrHookTimeout
		firing.Outcome = timeoutOutcome(spec)
		answered = stageAnswer{}
		answered.answer, answered.err = event.Answer(firing.Outcome)
	} else {
		firing.Call, firing.Error, firing.Outcome = answered.firing.Call, answered.firing.Error, answered.firing.Outcome
		checked = &validation{event: event, payload: answered.payload}
		_, _ = io.WriteString(stderr, answered.diagnostics)
	}
	exit, ok := writeAnswer(answered.answer, answered.err, stdout, stderr)
	if !ok {
		firing.Error = logline.ErrAnswerFailed
	}
	end := machine.Now()
	firing.Duration = end.Sub(start)
	if timedOut && !finished {
		cleanup := time.NewTimer(2500 * time.Millisecond)
		defer cleanup.Stop()
		select {
		case <-worker:
		case <-cleanup.C:
		}
	}
	logRun(sink, firing, checked, end, machine)
	return exit
}

// stageAnswer belongs to the worker until it sends it to the supervisor.
type stageAnswer struct {
	payload     []byte
	firing      logline.Firing
	diagnostics string
	answer      definition.Answer
	err         error
}

func decideStage(event definition.Event, spec hookSpec, decide hook, stdin io.Reader, machine Machine) stageAnswer {
	var diagnostics bytes.Buffer
	var result stageAnswer
	payload, readErr := io.ReadAll(stdin)
	result.payload = payload
	result.firing.Outcome = decideInput(event, spec, decide, payload, readErr, machine, &diagnostics, &result.firing)
	result.answer, result.err = event.Answer(result.firing.Outcome)
	result.diagnostics = diagnostics.String()
	return result
}

func timeoutOutcome(spec hookSpec) ir.Outcome {
	if spec.Failure != failClosed {
		return ir.Outcome{}
	}
	return ir.Outcome{
		Action: ir.Block,
		Rule:   ir.RuleHookTimeout,
		Reason: "agent-hook's " + spec.ID + " hook did not finish in time, so the call is blocked.",
	}
}

// stageMachine gives every child the stage's absolute deadline.
type stageMachine struct {
	Machine
	deadline time.Time
}

func (m stageMachine) Run(command process.Command) (process.Result, error) {
	command.Deadline = m.deadline
	return m.Machine.Run(command)
}

// writeAnswer writes the rendered answer as the harness reads it. On
// a failure it returns exitSoftware and false.
func writeAnswer(answer definition.Answer, err error, stdout, stderr io.Writer) (int, bool) {
	if err != nil {
		_, _ = fmt.Fprintf(stderr, "agent-hook: cannot render the answer: %v\n", err)
		return exitSoftware, false
	}
	if _, err := io.WriteString(stdout, answer.Stdout); err != nil {
		return exitSoftware, false
	}
	if _, err := io.WriteString(stderr, answer.Stderr); err != nil {
		return exitSoftware, false
	}
	return answer.Exit, true
}

// decideInput is the hook's outcome on the payload the harness sent. It
// records the decoded call and what went wrong (a logline.Err* code) in the
// firing, for the log.
func decideInput(event definition.Event, spec hookSpec, decide hook, payload []byte, readErr error,
	machine Machine, stderr io.Writer, firing *logline.Firing,
) ir.Outcome {
	if event.Transport() == ir.TransportShim {
		if err := shimRequestError(event, payload, readErr); err != nil {
			_, _ = fmt.Fprintf(stderr, "agent-hook: a broken shim exchange: %v\n", err)
			firing.Error = logline.ErrShimBroken
			return brokenExchange(spec)
		}
	}
	// A guard blocks input it cannot read; rtk and the formatter let it go on
	// and run nothing, as their scripts failed open.
	unread := ir.Outcome{}
	if spec.Failure == failClosed {
		unread = unreadable
	}
	if readErr != nil {
		firing.Error = logline.ErrInputUnreadable
		return unread
	}
	call, err := event.Decode(payload)
	if err != nil {
		firing.Error = logline.ErrInputUnreadable
		return unread
	}
	call.Native = payload
	if call.PathResolution == ir.PathsPi {
		call = resolvePiPath(call, machine)
	}
	firing.Call = &call
	if call.ToolFailed {
		// A post hook acts on what the tool call did; a call that failed did
		// nothing to act on.
		firing.Error = logline.ErrToolFailed
		return ir.Outcome{}
	}
	outcome, failure := decideSafely(decide, call, machine)
	if failure != nil {
		outcome = failedOutcome(spec)
		what := "so the call goes on"
		if outcome.Action == ir.Block {
			what = "so the call is blocked"
		}
		_, _ = fmt.Fprintf(stderr, "agent-hook: the %s hook failed, %s: %v\n", spec.ID, what, failure)
		firing.Error = logline.ErrHookFailed
	}
	if outcome.Action == ir.Rewrite {
		// The codec writes the new value where the definition maps the field
		// and checks the result; what it cannot write is no rewrite.
		if _, err := event.Rewrite(payload, outcome.Set); err != nil {
			_, _ = fmt.Fprintf(stderr, "agent-hook: the %s hook's rewrite was dropped, so the call goes on: %v\n", spec.ID, err)
			firing.Error = logline.ErrRewriteDropped
			return ir.Outcome{}
		}
	}
	return outcome
}

// validation is what the log checks a decoded payload against: the event's
// definition. Only the log reads the result.
type validation struct {
	event   definition.Event
	payload []byte
}

// mismatch is the log's validation result for a decoded call: the first of
// envelope, input, mapping, and unchecked that applies, or "".
func (v *validation) mismatch(call ir.Call) string {
	conformance := v.event.Conform(v.payload)
	switch conformance {
	case definition.EnvelopeMismatch:
		return logline.MismatchEnvelope
	case definition.InputMismatch:
		return logline.MismatchInput
	}
	if call.MappingMismatch() {
		return logline.MismatchMapping
	}
	if conformance == definition.Unchecked {
		return logline.MismatchUnchecked
	}
	return ""
}

// logRun writes the run's line to the sink, after the answer: the
// validation, the salt, the random ids, the write, and the sink's cleanup.
// It waits at most logDeadline, so the run ends on time whatever the sink
// does; a goroutine still stuck in a system call ends with the process. Every
// error and any panic is dropped, and nothing is printed: logging never
// changes the answer or the exit code.
func logRun(sink logsink.Sink, firing logline.Firing, checked *validation, now time.Time, machine Machine) {
	done := make(chan struct{})
	go func() {
		defer close(done)
		defer func() { _ = recover() }()
		if checked != nil && firing.Call != nil {
			firing.Mismatch = checked.mismatch(*firing.Call)
		}
		firing.Wd = machine.Getwd()
		salt, ok := sink.Salt()
		if !ok {
			salt = nil
		}
		var span [8]byte
		var trace [16]byte
		if err := machine.Random(span[:]); err != nil {
			return
		}
		if err := machine.Random(trace[:]); err != nil {
			return
		}
		line, err := logline.Build(firing, salt, now, span, trace).Marshal()
		if err != nil {
			return
		}
		_ = sink.Write(now, line)
	}()
	deadline := time.NewTimer(logDeadline)
	defer deadline.Stop()
	select {
	case <-done:
	case <-deadline.C:
	}
}

// resolvePiPath replaces the call's file path with the file Pi touches: Pi
// resolves a tool's path against the call's cwd before it writes or edits
// (internal/pipath), so the hooks judge that file. A path the port cannot
// resolve as Pi does is marked, so that the files guard blocks it and the
// formatter leaves it. A path that is not a string names no file, and stays.
func resolvePiPath(call ir.Call, machine Machine) ir.Call {
	value, ok := call.Fields[ir.FieldFilePath]
	if !ok || !value.IsString {
		return call
	}
	home, known := machine.HomeDir()
	// The shim protocol makes the cwd an absolute path; anything else does
	// not resolve.
	resolved, ok := pipath.Resolve(value.Text, call.Fields[ir.FieldCwd].Text, pipath.Home{Dir: home, Known: known})
	if !ok {
		call.PathUnresolved = true
		return call
	}
	call.Fields = maps.Clone(call.Fields)
	call.Fields[ir.FieldFilePath] = ir.Value{Text: resolved, IsString: true}
	return call
}

// shimRequestError is why a shim's request breaks the shim protocol, or nil.
func shimRequestError(event definition.Event, payload []byte, readErr error) error {
	if readErr != nil {
		return readErr
	}
	return event.CheckShimRequest(payload)
}

// brokenExchange is the outcome of a shim request that breaks the shim
// protocol: the shim and the binary are out of step, so no hook can trust
// what it reads. Before the tool, every hook blocks, open ones (rtk)
// included; after it, nothing runs.
func brokenExchange(spec hookSpec) ir.Outcome {
	if spec.Event != "pre" {
		return ir.Outcome{}
	}
	return ir.Outcome{
		Action: ir.Block,
		Rule:   ir.RuleShimBroken,
		Reason: "agent-hook could not read the shim's request, so no hook ran: the shim and the binary are out of step.",
	}
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

// failedOutcome is the outcome of a hook that failed (panicked).
//
// fixed-guard-failure: a guard blocks the call, as it blocks input it cannot
// read. The old Python guard's own exceptions exited 1, which Claude and Codex
// let through. rtk and the formatter let the call go on, as their scripts did.
func failedOutcome(spec hookSpec) ir.Outcome {
	if spec.Failure != failClosed {
		return ir.Outcome{}
	}
	return ir.Outcome{
		Action: ir.Block,
		Rule:   ir.RuleHookFailed,
		Reason: "agent-hook's " + spec.ID + " hook failed, so it could not check the call.",
	}
}

// decideSafely runs a hook. A hook that panics decides nothing; the panic is
// returned, for the caller to answer with failedOutcome and to tell.
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

func filesGuard(call ir.Call, _ Machine) ir.Outcome {
	return fileguard.CheckCall(call)
}

func secretsGuard(call ir.Call, _ Machine) ir.Outcome {
	return secretguard.Check(secretguard.Contents(call))
}
