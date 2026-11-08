package launch

import (
	"bytes"
	"strings"
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/harnesses"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/definition"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/fake"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/logline"
)

type panickingInput struct{}

func (panickingInput) Read([]byte) (int, error) { panic("stdin read failed") }

func TestStageRecoversAPanicWhileReadingStdin(t *testing.T) {
	for _, id := range []string{"command-guard", "rtk", "formatter"} {
		t.Run(id, func(t *testing.T) {
			event := "pre"
			outcome := ir.Outcome{}
			switch id {
			case "command-guard":
				outcome = ir.Outcome{Action: ir.Block, Rule: "hook.failed", Reason: "agent-hook's command-guard hook failed, so it could not check the call."}
			case "formatter":
				event = "post"
			}
			want := answerTo(t, "claude", event, outcome)
			var stdout, stderr bytes.Buffer
			sink := &fake.LogSink{}
			exit := run([]string{"claude", event, "--hook", id}, panickingInput{}, &stdout, &stderr,
				&fake.Machine{}, sink, hooks)
			if exit != want.Exit || stdout.String() != want.Stdout || !strings.Contains(stderr.String(), "stdin read failed") || !strings.HasSuffix(stderr.String(), want.Stderr) {
				t.Errorf("exit %d, stdout %q, stderr %q; want %+v and panic diagnostics", exit, stdout.String(), stderr.String(), want)
			}
			entries := sink.Lines()
			if len(entries) != 1 {
				t.Fatalf("%d log lines, want one", len(entries))
			}
			line, err := logline.Parse(entries[0].Line)
			wantOutcome := "pass"
			if id == "command-guard" {
				wantOutcome = "block"
			}
			if err != nil || line.Error != "hook.failed" || line.Rule != outcome.Rule || line.Outcome != wantOutcome {
				t.Errorf("line %+v, %v; want hook.failed and %s", line, err, wantOutcome)
			}
		})
	}
}

// runPanicking runs hook id, which panics, on a harness's fixture.
func runPanicking(t *testing.T, harness, event, id, fixture string) (int, string, string) {
	t.Helper()
	payload, err := harnesses.FS.ReadFile(harness + "/fixtures/" + fixture)
	if err != nil {
		t.Fatal(err)
	}
	panicking := map[string]hook{id: func(ir.Call, Machine) ir.Outcome { panic("broken") }}
	var stdout, stderr bytes.Buffer
	exit := run([]string{harness, event, "--hook", id}, bytes.NewReader(payload), &stdout, &stderr,
		&fake.Machine{}, &fake.LogSink{}, panicking)
	return exit, stdout.String(), stderr.String()
}

// answerTo is the harness's answer to an outcome.
func answerTo(t *testing.T, harness, event string, outcome ir.Outcome) definition.Answer {
	t.Helper()
	def, err := definition.Load(harnesses.FS, harness)
	if err != nil {
		t.Fatal(err)
	}
	e, ok := def.Event(event)
	if !ok {
		t.Fatalf("%s has no event %s", harness, event)
	}
	answer, err := e.Answer(outcome)
	if err != nil {
		t.Fatal(err)
	}
	return answer
}

func TestFixedGuardFailureBlocks(t *testing.T) {
	// fixed-guard-failure: a guard that panics blocks the call, as a guard
	// blocks input it cannot read. The old Python guard's own exceptions
	// exited 1, which Claude and Codex let through. The panic is told on
	// stderr, before the harness's answer.
	fixtures := map[string]string{
		"claude": "pre-bash.json",
		"codex":  "pre-bash.json",
		"agy":    "pre-run-command.json",
		"pi":     "pre-bash.json",
	}
	for _, id := range []string{"command-guard", "files-guard", "secrets-guard"} {
		failed := ir.Outcome{
			Action: ir.Block,
			Rule:   "hook.failed",
			Reason: "agent-hook's " + id + " hook failed, so it could not check the call.",
		}
		for harness, fixture := range fixtures {
			exit, stdout, stderr := runPanicking(t, harness, "pre", id, fixture)
			want := answerTo(t, harness, "pre", failed)
			if exit != want.Exit || stdout != want.Stdout ||
				!strings.Contains(stderr, "broken") || !strings.HasSuffix(stderr, want.Stderr) {
				t.Errorf("%s %s: exit %d, stdout %q, stderr %q; want exit %d, stdout %q, the panic, then stderr %q",
					harness, id, exit, stdout, stderr, want.Exit, want.Stdout, want.Stderr)
			}
		}
	}
}

func TestAnOpenHookThatPanicsPasses(t *testing.T) {
	// rtk and the formatter fail open, as their scripts did: the panic is
	// told on stderr, and the call goes on.
	cases := []struct{ harness, event, id, fixture string }{
		{"claude", "pre", "rtk", "pre-bash.json"},
		{"codex", "pre", "rtk", "pre-bash.json"},
		{"claude", "post", "formatter", "post-write.json"},
		{"codex", "post", "formatter", "post-apply-patch.json"},
		{"agy", "post", "formatter", "post-write-file.json"},
	}
	for _, c := range cases {
		exit, stdout, stderr := runPanicking(t, c.harness, c.event, c.id, c.fixture)
		want := answerTo(t, c.harness, c.event, ir.Outcome{})
		if exit != want.Exit || stdout != want.Stdout || !strings.Contains(stderr, "broken") {
			t.Errorf("%s %s: exit %d, stdout %q, stderr %q; want exit %d, stdout %q, the panic on stderr",
				c.harness, c.id, exit, stdout, stderr, want.Exit, want.Stdout)
		}
	}
}

func TestFailedOutcomeBlocksOnlyForAClosedHook(t *testing.T) {
	// fixed-guard-failure: the answers above do not show the rule, so the
	// outcome itself is pinned here.
	closed := failedOutcome(hookSpec{ID: "files-guard", Failure: failClosed})
	want := ir.Outcome{
		Action: ir.Block,
		Rule:   "hook.failed",
		Reason: "agent-hook's files-guard hook failed, so it could not check the call.",
	}
	if closed != want {
		t.Errorf("closed hook: %+v, want %+v", closed, want)
	}
	if open := failedOutcome(hookSpec{ID: "rtk", Failure: failOpen}); open != (ir.Outcome{}) {
		t.Errorf("open hook: %+v, want a pass", open)
	}
}
