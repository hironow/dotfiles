package registration_test

import (
	"bytes"
	"errors"
	"testing"

	json "github.com/goccy/go-json/v2"

	agenthooks "github.com/hironow/dotfiles/tools/agent-hooks"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/registration"
)

type failingWriter struct{}

func (failingWriter) Write([]byte) (int, error) { return 0, errors.New("disk full") }

// exitSoftware is the binary's exit when an answer cannot be written.
const exitSoftware = 70

func TestMainFailsWhenItCannotWrite(t *testing.T) {
	// Codex on Windows has a loss line; Claude on Linux has none.
	codex := []string{"--harness", "codex", "--os", "windows", "--shell", "cmd", "--binary", `C:\s\dotfiles\agent-hooks\current\codex\agent-hook.exe`}
	claude := []string{"--harness", "claude", "--os", "linux", "--binary", "/s/dotfiles/agent-hooks/current/claude/agent-hook"}
	t.Run("loss report", func(t *testing.T) {
		// A fragment without its loss report would hide a gap from sync.
		var stdout bytes.Buffer
		if exit := registration.Main(codex, &stdout, failingWriter{}); exit != exitSoftware || stdout.Len() != 0 {
			t.Fatalf("exit %d, stdout %q; want %d and no fragment", exit, &stdout, exitSoftware)
		}
	})
	for name, args := range map[string][]string{"fragment with losses": codex, "fragment": claude} {
		t.Run(name, func(t *testing.T) {
			var stderr bytes.Buffer
			if exit := registration.Main(args, failingWriter{}, &stderr); exit != exitSoftware {
				t.Fatalf("exit %d, want %d: %s", exit, exitSoftware, &stderr)
			}
		})
	}
}

func TestEveryClosedHookRunsBeforeTheTool(t *testing.T) {
	// The launchers' fallbacks block the call (Codex's deny names PreToolUse),
	// which means nothing after the tool has run.
	var manifest struct {
		Hooks []registration.Hook `json:"hooks"`
	}
	if err := json.Unmarshal(agenthooks.Manifest, &manifest); err != nil {
		t.Fatal(err)
	}
	for _, hook := range manifest.Hooks {
		if hook.Failure == "closed" && hook.Event != "pre" {
			t.Errorf("%s fails closed on %s", hook.ID, hook.Event)
		}
	}
}
