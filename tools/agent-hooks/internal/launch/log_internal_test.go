package launch

import (
	"bytes"
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/harnesses"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/fake"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/logline"
)

// loggedBy runs one hook of the binary, replaced by decide, and returns the
// line it logged.
func loggedBy(t *testing.T, decide hook, id string, payload []byte, args ...string) logline.Line {
	t.Helper()
	sink := &fake.LogSink{}
	var stdout, stderr bytes.Buffer
	run(args, bytes.NewReader(payload), &stdout, &stderr, &fake.Machine{}, sink, map[string]hook{id: decide})
	entries := sink.Lines()
	if len(entries) != 1 {
		t.Fatalf("%d lines, want 1", len(entries))
	}
	line, err := logline.Parse(entries[0].Line)
	if err != nil {
		t.Fatal(err)
	}
	return line
}

func TestTheLineTellsAForwardARewriteAndAHooksFailure(t *testing.T) {
	claudeBash, err := harnesses.FS.ReadFile("claude/fixtures/pre-bash.json")
	if err != nil {
		t.Fatal(err)
	}
	piBash := []byte(`{"v":1,"harness":"pi","event":"pre","tool":"bash","input":{"command":"ls"},"cwd":"/home/user/project"}`)
	cases := []struct {
		name          string
		decide        hook
		id            string
		payload       []byte
		args          []string
		outcome, code string
	}{
		{
			"a forward", func(ir.Call, Machine) ir.Outcome { return ir.Outcome{Action: ir.Forward, Native: "{}"} },
			"rtk", claudeBash,
			[]string{"claude", "pre", "--hook", "rtk"},
			"forward", "",
		},
		{
			"a rewrite", func(ir.Call, Machine) ir.Outcome {
				return ir.Outcome{Action: ir.Rewrite, Set: ir.Assignment{Field: ir.FieldCommand, Value: "rtk ls"}}
			},
			"rtk", piBash,
			[]string{"pi", "pre", "--hook", "rtk"},
			"rewrite", "",
		},
		{
			"a rewrite the codec drops", func(ir.Call, Machine) ir.Outcome {
				return ir.Outcome{Action: ir.Rewrite, Set: ir.Assignment{Field: "noSuchField", Value: "x"}}
			},
			"rtk", piBash,
			[]string{"pi", "pre", "--hook", "rtk"},
			"pass", logline.ErrRewriteDropped,
		},
		{
			"a guard that panics", func(ir.Call, Machine) ir.Outcome { panic("broken") },
			"command-guard", claudeBash,
			[]string{"claude", "pre", "--hook", "command-guard"},
			"block", logline.ErrHookFailed,
		},
		{
			"an open hook that panics", func(ir.Call, Machine) ir.Outcome { panic("broken") },
			"rtk", claudeBash,
			[]string{"claude", "pre", "--hook", "rtk"},
			"pass", logline.ErrHookFailed,
		},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			// given a hook that decides so, when the binary runs it
			line := loggedBy(t, c.decide, c.id, c.payload, c.args...)
			// then the line tells the final outcome and what went wrong
			if line.Outcome != c.outcome || line.Error != c.code || line.Hook != c.id {
				t.Errorf("outcome %q error %q hook %q, want %q %q %q", line.Outcome, line.Error, line.Hook, c.outcome, c.code, c.id)
			}
		})
	}
}
