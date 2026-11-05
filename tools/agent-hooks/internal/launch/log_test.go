package launch_test

import (
	"bytes"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"errors"
	"slices"
	"strings"
	"testing"
	"time"

	json "github.com/goccy/go-json/v2"

	"github.com/hironow/dotfiles/tools/agent-hooks/harnesses"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/fake"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/launch"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/logline"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/logsink"
)

// logged runs the binary on a sink and returns its answer and the lines the
// sink kept, parsed.
func logged(t *testing.T, machine launch.Machine, sink *fake.LogSink, stdin string, args ...string) (result, []logline.Line) {
	t.Helper()
	var stdout, stderr bytes.Buffer
	exit := launch.Run(args, strings.NewReader(stdin), &stdout, &stderr, machine, sink)
	var lines []logline.Line
	for _, entry := range sink.Lines() {
		line, err := logline.Parse(entry.Line)
		if err != nil {
			t.Fatalf("the sink got a line Parse refuses: %q: %v", entry.Line, err)
		}
		lines = append(lines, line)
	}
	return result{exit, stdout.String(), stderr.String()}, lines
}

// oneLine is the one line a run logged.
func oneLine(t *testing.T, lines []logline.Line) logline.Line {
	t.Helper()
	if len(lines) != 1 {
		t.Fatalf("the run logged %d lines, want 1: %+v", len(lines), lines)
	}
	return lines[0]
}

func fixture(t *testing.T, name string) string {
	t.Helper()
	data, err := harnesses.FS.ReadFile(name)
	if err != nil {
		t.Fatal(err)
	}
	return string(data)
}

// claudeBash is Claude's pre-bash fixture with its payload changed.
func claudeBash(t *testing.T, change func(payload map[string]any)) string {
	t.Helper()
	var payload map[string]any
	if err := json.Unmarshal([]byte(fixture(t, "claude/fixtures/pre-bash.json")), &payload); err != nil {
		t.Fatal(err)
	}
	change(payload)
	data, err := json.Marshal(payload)
	if err != nil {
		t.Fatal(err)
	}
	return string(data)
}

func TestEachRunLogsOneLineOfWhatHappened(t *testing.T) {
	bashWith := func(command any) func(map[string]any) {
		return func(p map[string]any) { p["tool_input"] = map[string]any{"command": command} }
	}
	brokenShim := piRequest("pre", "bash", `{"command":"ls"}`)
	brokenShim = strings.Replace(brokenShim, `"v":1`, `"v":2`, 1)
	failedTool := piRequest("post", "write", `{"path":"a.md","content":"x"}`)
	failedTool = strings.Replace(failedTool, `"ok":true`, `"ok":false`, 1)
	cases := []struct {
		name  string
		stdin string
		args  []string
		want  logline.Line // the fields compared; the rest are checked apart
	}{
		{
			"a pass", fixture(t, "claude/fixtures/pre-bash.json"),
			[]string{"claude", "pre", "--hook", "command-guard"},
			logline.Line{
				Harness: "claude", Event: "pre", Tool: "Bash", Kind: "shell", Hook: "command-guard", Outcome: "pass",
				Program: "echo",
			},
		},
		{
			"a block", claudeBash(t, bashWith("npm ci")),
			[]string{"claude", "pre", "--hook", "command-guard"},
			logline.Line{
				Harness: "claude", Event: "pre", Tool: "Bash", Kind: "shell", Hook: "command-guard", Outcome: "block",
				Rule: "command.node", Program: "npm", Subcommand: "ci",
			},
		},
		{
			"input that is not one JSON value", `{"tool_name":`,
			[]string{"claude", "pre", "--hook", "files-guard"},
			logline.Line{
				Harness: "claude", Event: "pre", Tool: "other", Kind: "none", Hook: "files-guard", Outcome: "block",
				Rule: "input.unreadable", Error: logline.ErrInputUnreadable,
			},
		},
		{
			"a broken shim exchange", brokenShim,
			[]string{"pi", "pre", "--hook", "rtk"},
			logline.Line{
				Harness: "pi", Event: "pre", Tool: "other", Kind: "none", Hook: "rtk", Outcome: "block",
				Rule: "shim.broken", Error: logline.ErrShimBroken,
			},
		},
		{
			"a post call after a failed tool", failedTool,
			[]string{"pi", "post", "--hook", "formatter"},
			logline.Line{
				Harness: "pi", Event: "post", Tool: "write", Kind: "write", Hook: "formatter", Outcome: "pass",
				Extension: ".md", Error: logline.ErrToolFailed,
			},
		},
		{
			"an envelope mismatch", claudeBash(t, func(p map[string]any) { p["tool_name"] = 5 }),
			[]string{"claude", "pre", "--hook", "command-guard"},
			logline.Line{
				Harness: "claude", Event: "pre", Tool: "other", Kind: "none", Hook: "command-guard", Outcome: "pass",
				Mismatch: logline.MismatchEnvelope,
			},
		},
		{
			"an input mismatch", claudeBash(t, bashWith(1)),
			[]string{"claude", "pre", "--hook", "command-guard"},
			logline.Line{
				Harness: "claude", Event: "pre", Tool: "Bash", Kind: "shell", Hook: "command-guard", Outcome: "pass",
				Mismatch: logline.MismatchInput,
			},
		},
		{
			"a mapping mismatch", claudeBash(t, func(p map[string]any) {
				p["tool_name"] = "FutureTool"
				p["tool_input"] = map[string]any{"command": 123}
			}),
			[]string{"claude", "pre", "--hook", "command-guard"},
			logline.Line{
				Harness: "claude", Event: "pre", Tool: "other", Kind: "none", Hook: "command-guard", Outcome: "pass",
				Mismatch: logline.MismatchMapping,
			},
		},
		{
			// The validator cannot read it, but the IR shows the mapping
			// mismatch, which comes first.
			"an unchecked payload with a mapping mismatch", strings.Replace(claudeBash(t, func(p map[string]any) {
				p["tool_name"] = "FutureTool"
				p["tool_input"] = map[string]any{"command": 123}
			}), "{", `{"x": 1e400,`, 1),
			[]string{"claude", "pre", "--hook", "command-guard"},
			logline.Line{
				Harness: "claude", Event: "pre", Tool: "other", Kind: "none", Hook: "command-guard", Outcome: "pass",
				Mismatch: logline.MismatchMapping,
			},
		},
		{
			"an unchecked payload", strings.Replace(fixture(t, "claude/fixtures/pre-bash.json"), "{", `{"x": 1e400,`, 1),
			[]string{"claude", "pre", "--hook", "command-guard"},
			logline.Line{
				Harness: "claude", Event: "pre", Tool: "Bash", Kind: "shell", Hook: "command-guard", Outcome: "pass",
				Program: "echo", Mismatch: logline.MismatchUnchecked,
			},
		},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			// given a payload, when the binary runs a hook on it with a sink
			sink := &fake.LogSink{}
			_, lines := logged(t, &fake.Machine{}, sink, c.stdin, c.args...)
			// then it logs exactly one line, of what happened
			got := oneLine(t, lines)
			want := c.want
			want.Time, want.Release, want.DurationMs, want.TraceID, want.SpanID = got.Time, got.Release, got.DurationMs,
				got.TraceID, got.SpanID
			if got != want {
				t.Errorf("line\n got %+v\nwant %+v", got, want)
			}
			if got.Release != logline.Release || len(got.TraceID) != 32 || len(got.SpanID) != 16 || got.Project != "" {
				t.Errorf("release %q, trace %q, span %q, project %q: want the release, random ids, no project without salt",
					got.Release, got.TraceID, got.SpanID, got.Project)
			}
		})
	}
}

func TestARunWithArgumentsItDoesNotKnowLogsAUsageLine(t *testing.T) {
	sink := &fake.LogSink{}
	// given arguments the binary does not know, when it runs
	got, _ := logged(t, &fake.Machine{}, sink, `{}`, "claude", "pre", "--hook", "no-such-hook")
	if got.exit != 64 {
		t.Fatalf("exit %d, want 64", got.exit)
	}
	// then the line has only the usage line's keys
	entries := sink.Lines()
	if len(entries) != 1 {
		t.Fatalf("%d lines, want 1", len(entries))
	}
	var members map[string]any
	if err := json.Unmarshal(entries[0].Line, &members); err != nil {
		t.Fatal(err)
	}
	keys := slices.Sorted(func(yield func(string) bool) {
		for key := range members {
			if !yield(key) {
				return
			}
		}
	})
	want := []string{"error", "harness", "release", "spanId", "time", "traceId"}
	if !slices.Equal(keys, want) || members["harness"] != "claude" || members["error"] != logline.ErrUsage {
		t.Errorf("usage line %s; want keys %v, harness claude, error usage", entries[0].Line, want)
	}
}

func TestTheLineTellsTheRunsDurationAndEndTime(t *testing.T) {
	start := time.Date(2026, 11, 5, 4, 0, 0, 0, time.UTC)
	m := &fake.Machine{Time: start, Step: 1500 * time.Microsecond}
	sink := &fake.LogSink{}
	_, lines := logged(t, m, sink, fixture(t, "claude/fixtures/pre-bash.json"), "claude", "pre", "--hook", "command-guard")
	got := oneLine(t, lines)
	if got.DurationMs != 1.5 || got.Time != "2026-11-05T04:00:00.001Z" {
		t.Errorf("durationMs %v, time %q; want 1.5 and the end of the run", got.DurationMs, got.Time)
	}
	if entries := sink.Lines(); !entries[0].Time.Equal(start.Add(1500 * time.Microsecond)) {
		t.Errorf("the sink got the time %v, want the end of the run", entries[0].Time)
	}
}

// hashed is HMAC-SHA256 over the log's unambiguous message: each field's
// length (4 bytes, big-endian), then its bytes.
func hashed(salt []byte, fields ...string) string {
	mac := hmac.New(sha256.New, salt)
	for _, field := range fields {
		mac.Write(binary.BigEndian.AppendUint32(nil, uint32(len(field))))
		mac.Write([]byte(field))
	}
	return hex.EncodeToString(mac.Sum(nil))
}

func TestWithASaltTheProjectIsHashedAndACallsPreAndPostShareATrace(t *testing.T) {
	salt := bytes.Repeat([]byte{7}, logsink.SaltSize)
	sink := &fake.LogSink{SaltBytes: salt}
	// given one Claude edit's pre and post payloads (the same session and call)
	_, pre := logged(t, &fake.Machine{}, sink, fixture(t, "claude/fixtures/pre-edit.json"), "claude", "pre", "--hook", "files-guard")
	post := &fake.LogSink{SaltBytes: salt}
	_, after := logged(t, &fake.Machine{}, post, fixture(t, "claude/fixtures/post-edit.json"), "claude", "post", "--hook", "formatter")
	// then both lines carry the same trace, hashed from the ids, and the project
	trace := hashed(salt, "trace", "claude", "s00000000-0000-4000-8000-000000000001", "stoolu_01FIXTUREEDIT")[:32]
	project := hashed(salt, "project", "/home/user/project")[:16]
	for _, line := range []logline.Line{oneLine(t, pre), oneLine(t, after)} {
		if line.TraceID != trace || line.Project != project {
			t.Errorf("%s line: trace %q project %q, want %q and %q", line.Event, line.TraceID, line.Project, trace, project)
		}
	}
}

// failingSink fails every write.
type failingSink struct{}

func (failingSink) Salt() ([]byte, bool)          { return nil, false }
func (failingSink) Write(time.Time, []byte) error { return errors.New("disk full") }

// panickingSink panics.
type panickingSink struct{}

func (panickingSink) Salt() ([]byte, bool)          { panic("a broken sink") }
func (panickingSink) Write(time.Time, []byte) error { panic("a broken sink") }

// stuckSink never returns until the test ends.
type stuckSink struct{ release chan struct{} }

func (s stuckSink) Salt() ([]byte, bool)          { <-s.release; return nil, false }
func (s stuckSink) Write(time.Time, []byte) error { <-s.release; return nil }

func TestASinkThatFailsPanicsOrHangsChangesNoAnswer(t *testing.T) {
	stuck := stuckSink{release: make(chan struct{})}
	t.Cleanup(func() { close(stuck.release) })
	payload := claudeBash(t, func(p map[string]any) {
		p["tool_input"] = map[string]any{"command": "npm ci"}
	})
	args := []string{"claude", "pre", "--hook", "command-guard"}
	var stdout, stderr bytes.Buffer
	exit := launch.Run(args, strings.NewReader(payload), &stdout, &stderr, &fake.Machine{}, &fake.LogSink{})
	want := result{exit, stdout.String(), stderr.String()}
	for name, sink := range map[string]logsink.Sink{"failing": failingSink{}, "panicking": panickingSink{}, "stuck": stuck} {
		t.Run(name, func(t *testing.T) {
			// given a sink that fails, panics, or never returns
			var stdout, stderr bytes.Buffer
			began := time.Now()
			// when the binary runs and logs to it
			exit := launch.Run(args, strings.NewReader(payload), &stdout, &stderr, &fake.Machine{}, sink)
			took := time.Since(began)
			// then the answer, the exit code, and stderr are as with a working
			// sink, and the run ends within the logging deadline
			if got := (result{exit, stdout.String(), stderr.String()}); got != want {
				t.Errorf("got %+v, want %+v", got, want)
			}
			if took > 2*time.Second {
				t.Errorf("the run took %v; the logging deadline is 250ms", took)
			}
		})
	}
}

// failingWriter fails every write, as a closed stdout would.
type failingWriter struct{}

func (failingWriter) Write([]byte) (int, error) { return 0, errors.New("closed") }

func TestAnAnswerThatCannotBeWrittenIsLogged(t *testing.T) {
	sink := &fake.LogSink{}
	var stderr bytes.Buffer
	exit := launch.Run([]string{"claude", "pre", "--hook", "command-guard"},
		strings.NewReader(fixture(t, "claude/fixtures/pre-bash.json")), failingWriter{}, &stderr, &fake.Machine{}, sink)
	if exit != 70 {
		t.Fatalf("exit %d, want 70", exit)
	}
	entries := sink.Lines()
	if len(entries) != 1 {
		t.Fatalf("%d lines, want 1", len(entries))
	}
	line, err := logline.Parse(entries[0].Line)
	if err != nil || line.Error != logline.ErrAnswerFailed {
		t.Errorf("line %+v (%v), want the error %q", line, err, logline.ErrAnswerFailed)
	}
}
