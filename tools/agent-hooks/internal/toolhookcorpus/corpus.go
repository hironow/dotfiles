// Package toolhookcorpus holds the corpora of the hooks that run other
// programs: rtk.jsonl (the rtk hook) and formatter.jsonl (the formatter).
// scripts/tool_hooks_corpus.py writes them by running the old scripts
// (ROOT_AGENTS_hooks_rtk-hook-{claude,codex}.*, format-after-edit.sh) in a
// temporary root built from scratch, with fake programs, and
// tests/unit/test_tool_hooks_corpus.py checks that they are fresh. The Go
// tests check the binary against every run: in-process with a fake machine
// that answers from World and replays the recorded invocations, and as a real
// process, with faketool standing in for each fake program.
//
// "@ROOT@" in any value is the temporary root; a test puts its own in.
package toolhookcorpus

import (
	_ "embed"
	"strings"
	"testing"

	"github.com/goccy/go-json/jsontext"
	json "github.com/goccy/go-json/v2"
)

//go:embed rtk.jsonl
var rtkCorpus string

//go:embed formatter.jsonl
var formatterCorpus string

// Root is what stands for the temporary root in the corpora.
const Root = "@ROOT@"

// The difference IDs: how a run's expected behavior follows from its legacy run.
const (
	DifferenceNone                = ""
	DifferenceUnreadable          = "unreadable"            // not one JSON value: the binary passes silently
	DifferenceReferenceLimit      = "reference-limit"       // past a reference's limit: answered as its base
	DifferencePathRelative        = "path-relative"         // a program found through a relative PATH entry: not run
	DifferenceRTKAnswerUnreadable = "rtk-answer-unreadable" // rtk's answer is not one JSON value: the binary passes
	DifferenceNULWarning          = "nul-warning"           // bash warned of a NUL: the binary writes only the notices
	DifferencePassDiagnostic      = "pass-diagnostic"       // the formatter printed jq's errors only: the binary is silent
)

// Scenario is one environment and payload, run through a hook's script as
// each harness runs it.
type Scenario struct {
	Line        int         `json:"-"`       // its line in its corpus
	Name        string      `json:"name"`    // what the scenario tests
	Mirrors     []string    `json:"mirrors"` // the Python tests it mirrors
	Stdin       []byte      `json:"stdin"`   // the payload
	Base        string      `json:"base"`    // the scenario this one adds an unused member to, if any
	Environment Environment `json:"environment"`
	World       World       `json:"world"`
	Runs        []Run       `json:"runs"`
}

// Environment is the temporary root a scenario runs in, paths relative to it.
type Environment struct {
	Path  []string          `json:"path"`  // PATH, before @ROOT@/sys-bin
	Fakes map[string]Rule   `json:"fakes"` // each fake program, by where it is
	Files map[string]string `json:"files"` // regular files and their content
	Dirs  []string          `json:"dirs"`
	Links map[string]string `json:"links"` // symlinks and their targets
	Cwd   string            `json:"cwd"`   // the working directory
}

// Rule is how a fake program answers: one answer, or for uv one per `ruff
// check <path>` (Checks, else Clean) and Default for everything else.
type Rule struct {
	Stdout  []byte            `json:"stdout"`
	Stderr  []byte            `json:"stderr"`
	Exit    int               `json:"exit"`
	Default *Answer           `json:"default"`
	Clean   *Answer           `json:"clean"`
	Checks  map[string]Answer `json:"checks"`
}

// Answer is what a program writes, stdout then stderr, and its exit code.
type Answer struct {
	Stdout []byte `json:"stdout"`
	Stderr []byte `json:"stderr"`
	Exit   int    `json:"exit"`
}

// World is what the machine answers in a scenario, worked out by the
// generator on the real root: the in-process fake machine answers from it.
type World struct {
	Cwd          string             `json:"cwd"`          // the physical working directory
	Lookups      map[string]*Lookup `json:"lookups"`      // what PATH finds, by name; nil: nothing
	Executable   map[string]bool    `json:"executable"`   // access(X_OK), by path
	RegularFiles map[string]bool    `json:"regularFiles"` // [ -f ], by path
	// Unstartable lists paths a script tried to run that are no executable
	// file: running one fails, and no fake logs it.
	Unstartable []string `json:"unstartable"`
}

// Lookup is a program PATH finds.
type Lookup struct {
	Path     string `json:"path"`
	Relative bool   `json:"relative"`
}

// Run is one script run on a scenario, as one harness runs it.
type Run struct {
	Harness    string         `json:"harness"`
	Difference string         `json:"difference"` // the difference IDs that apply, joined by "+"; "" for none
	Fixed      jsontext.Value `json:"fixed"`      // the run of the script with its bugs fixed, where that differs
	Legacy     jsontext.Value `json:"legacy"`     // what the script did; the Python test reads it
	ExpectedGo Expected       `json:"expectedGo"`
}

// Expected is what the binary must do: its answer and the programs it runs.
type Expected struct {
	Exit   int    `json:"exit"`
	Stdout string `json:"stdout"`
	// StdoutJSON marks a forwarded answer: it is compared as JSON (SameJSON).
	StdoutJSON  bool         `json:"stdoutJSON"`
	Stderr      string       `json:"stderr"`
	Invocations []Invocation `json:"invocations"`
}

// Invocation is one program the binary must run, and what it answers.
type Invocation struct {
	Tool           string             `json:"tool"` // which fake, by where it is
	Path           string             `json:"path"` // the path given to execve
	Args           []string           `json:"args"` // the arguments after argv[0]
	Stdin          []byte             `json:"stdin"`
	TimeoutSeconds int                `json:"timeoutSeconds"`
	Combined       bool               `json:"combined"` // stdout and stderr on one pipe
	Cwd            string             `json:"cwd"`
	Env            map[string]*string `json:"env"` // PATH, HOME, AGENT_HOOK_PROBE as the program saw them
	Answer         Answer             `json:"answer"`
}

// RTK returns every scenario of rtk.jsonl.
func RTK(tb testing.TB) []Scenario {
	tb.Helper()
	return decode(tb, "rtk.jsonl", rtkCorpus)
}

// Formatter returns every scenario of formatter.jsonl.
func Formatter(tb testing.TB) []Scenario {
	tb.Helper()
	return decode(tb, "formatter.jsonl", formatterCorpus)
}

func decode(tb testing.TB, name, text string) []Scenario {
	tb.Helper()
	lines := strings.Split(strings.TrimSuffix(text, "\n"), "\n")
	scenarios := make([]Scenario, 0, len(lines))
	for i, line := range lines {
		var scenario Scenario
		if err := json.Unmarshal([]byte(line), &scenario, json.RejectUnknownMembers(true)); err != nil {
			tb.Fatalf("%s:%d: %v", name, i+1, err)
		}
		scenario.Line = i + 1
		scenarios = append(scenarios, scenario)
	}
	return scenarios
}

// Check fails tb unless an answer is the expected one, with sub putting a
// root in for @ROOT@: a forwarded answer is compared as JSON (SameJSON) and
// must be one line; anything else byte for byte.
func (e Expected) Check(tb testing.TB, where string, exit int, stdout, stderr string, sub func(string) string) {
	tb.Helper()
	if exit != e.Exit || stderr != sub(e.Stderr) {
		tb.Errorf("%s: exit %d, stderr %q; want exit %d, stderr %q", where, exit, stderr, e.Exit, sub(e.Stderr))
	}
	want := sub(e.Stdout)
	if !e.StdoutJSON {
		if stdout != want {
			tb.Errorf("%s: stdout %q, want %q", where, stdout, want)
		}
		return
	}
	if !strings.HasSuffix(stdout, "\n") || strings.Count(stdout, "\n") != 1 {
		tb.Errorf("%s: stdout %q is not one line", where, stdout)
	}
	if same, err := SameJSON([]byte(stdout), []byte(want)); err != nil || !same {
		tb.Errorf("%s: stdout %s, want %s (%v)", where, stdout, want, err)
	}
}
