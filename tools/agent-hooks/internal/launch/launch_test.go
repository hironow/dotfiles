package launch_test

import (
	"bytes"
	"errors"
	"strings"
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/fake"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/launch"
)

type result struct {
	exit           int
	stdout, stderr string
}

func run(t *testing.T, machine launch.Machine, stdin string, args ...string) result {
	t.Helper()
	var stdout, stderr bytes.Buffer
	exit := launch.Run(args, strings.NewReader(stdin), &stdout, &stderr, machine, &fake.LogSink{})
	return result{exit, stdout.String(), stderr.String()}
}

func deny(reason string) string {
	return `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny",` +
		`"permissionDecisionReason":"` + reason + `"}}` + "\n"
}

const (
	ymlReason    = "BLOCKED: 'a.yml' uses '.yml'. This project uses '.yaml' exclusively. Rename to 'a.yaml'."
	secretReason = "BLOCKED: content looks like a live secret (API key / token / private key). " +
		"Do not commit secrets; use a secret manager and reference via env var."
	nodeReason = "BLOCKED: Node package management is 'bun' only. " +
		"Do not use npm/yarn/pnpm (including 'corepack pnpm')."
	unreadableReason = "BLOCKED: agent-hook could not read the hook input as one JSON value, so no guard ran."
)

func TestRunAnswersAsEachHarnessReads(t *testing.T) {
	// A synthetic AWS-style key, built from pieces.
	key := "AKIA" + strings.Repeat("Z", 16)
	cases := []struct {
		hook, payload, reason string
	}{
		{"command-guard", `{"tool_input":{"command":"npm ci"}}`, nodeReason},
		{"files-guard", `{"tool_input":{"file_path":"a.yml"}}`, ymlReason},
		{"secrets-guard", `{"tool_input":{"content":"` + key + `"}}`, secretReason},
		{"command-guard", `{"tool_input":{"command":"bun install"}}`, ""},
		{"files-guard", `{"tool_input":{"file_path":"a.yaml"}}`, ""},
		{"secrets-guard", `{"tool_input":{"content":"plain"}}`, ""},
	}
	for _, c := range cases {
		claude := run(t, &fake.Machine{}, c.payload, "claude", "pre", "--hook", c.hook)
		codex := run(t, &fake.Machine{}, c.payload, "codex", "pre", "--hook", c.hook)
		wantClaude, wantCodex := result{}, result{}
		if c.reason != "" {
			wantClaude = result{exit: 2, stderr: c.reason + "\n"}
			wantCodex = result{stdout: deny(c.reason)}
		}
		if claude != wantClaude {
			t.Errorf("claude %s %s = %+v, want %+v", c.hook, c.payload, claude, wantClaude)
		}
		if codex != wantCodex {
			t.Errorf("codex %s %s = %+v, want %+v", c.hook, c.payload, codex, wantCodex)
		}
	}
}

func TestRunBlocksAPayloadThatIsNotOneJSONValue(t *testing.T) {
	for _, hook := range []string{"command-guard", "files-guard", "secrets-guard"} {
		for _, payload := range []string{"", "{", `{"tool_input":{"command":"ls"}} x`, `{"a":NaN}`} {
			if got, want := run(t, &fake.Machine{}, payload, "claude", "pre", "--hook", hook),
				(result{exit: 2, stderr: unreadableReason + "\n"}); got != want {
				t.Errorf("claude %s %q = %+v, want %+v", hook, payload, got, want)
			}
			if got, want := run(t, &fake.Machine{}, payload, "codex", "pre", "--hook", hook),
				(result{stdout: deny(unreadableReason)}); got != want {
				t.Errorf("codex %s %q = %+v, want %+v", hook, payload, got, want)
			}
		}
	}
}

type failingReader struct{}

func (failingReader) Read([]byte) (int, error) { return 0, errors.New("read failed") }

func TestRunBlocksWhenStdinCannotBeRead(t *testing.T) {
	var stdout, stderr bytes.Buffer
	exit := launch.Run([]string{"claude", "pre", "--hook", "files-guard"}, failingReader{}, &stdout, &stderr, &fake.Machine{}, &fake.LogSink{})
	if got, want := (result{exit, stdout.String(), stderr.String()}), (result{exit: 2, stderr: unreadableReason + "\n"}); got != want {
		t.Errorf("Run = %+v, want %+v", got, want)
	}
}

func TestTheFilesGuardRunsNoProgram(t *testing.T) {
	// fixed-dash-line: the old guard ran basename(1), whose flavor changed its
	// answer; the port takes base names itself, so a "-" line needs no program
	// and blocks the same everywhere. The fake machine fails any Run.
	for _, path := range []string{"a.yml", "-x\\na.yml", "--help\\na.yml", "--version.yml"} {
		machine := &fake.Machine{}
		got := run(t, machine, `{"tool_input":{"file_path":"`+path+`"}}`, "claude", "pre", "--hook", "files-guard")
		if got.exit != 2 {
			t.Errorf("%q: %+v, want a block", path, got)
		}
		checkReplay(t, machine)
	}
}

func TestRunRejectsArgumentsItDoesNotKnow(t *testing.T) {
	for _, args := range [][]string{
		{},
		{"claude"},
		{"claude", "pre"},
		{"claude", "pre", "--hook"},
		{"nope", "pre", "--hook", "files-guard"},
		{"claude", "post", "--hook", "files-guard"},
		{"claude", "pre", "--hook", "nope"},
		{"claude", "pre", "--hook", "files-guard", "extra"},
		{"claude", "pre", "--bogus", "files-guard"},
		{"claude", "pre", "files-guard"},
	} {
		got := run(t, &fake.Machine{}, `{"tool_input":{"file_path":"a.yml"}}`, args...)
		if got.exit != 64 || got.stdout != "" || !strings.Contains(got.stderr, "agent-hook") {
			t.Errorf("Run(%q) = %+v, want exit 64 with a message", args, got)
		}
	}
}
