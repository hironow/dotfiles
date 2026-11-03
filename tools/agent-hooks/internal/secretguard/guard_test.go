package secretguard_test

import (
	"fmt"
	"strings"
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/applypatch"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/guardcorpus"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/secretguard"
)

func TestCheckAgreesWithTheShellGuardOnTheCorpus(t *testing.T) {
	for _, entry := range guardcorpus.SecretsGuardEntries(t) {
		t.Run(fmt.Sprintf("line-%d", entry.Line), func(t *testing.T) {
			// given an input of the corpus, as Claude Code or Codex hands it over
			var content string
			if entry.Content != nil {
				content = *entry.Content
			} else {
				content = applypatch.AddedLines(*entry.Patch)
			}
			// when the guard checks its content
			outcome := secretguard.Check([]string{content})
			// then it blocks, with the same reason, exactly when the shell guard exited 2
			if entry.Exit != 2 {
				if outcome.Action != ir.Pass {
					t.Fatalf("Check(%q) blocked; the shell guard exited %d", content, entry.Exit)
				}
				return
			}
			if outcome.Action != ir.Block || outcome.Reason != *entry.Reason || outcome.Rule != secretguard.RuleCredential {
				t.Fatalf("Check(%q) = %v %s %q; the shell guard blocked: %q",
					content, outcome.Action, outcome.Rule, outcome.Reason, *entry.Reason)
			}
		})
	}
}

// The shell guard's reading, spelled out. Tokens are built here, so that this
// file holds none.
func TestCheckKeepsTheShellGuardsReading(t *testing.T) {
	key := "AKIA" + strings.Repeat("A", 16)
	cases := []struct {
		name     string
		contents []string
		blocked  bool
	}{
		{"a token anywhere in a content", []string{"x = '" + key + "'"}, true},
		{"any of several contents", []string{"plain", key}, true},
		{"a token split across lines is not one", []string{key[:10] + "\n" + key[10:]}, false},
		{"bash drops NUL bytes, joining the token", []string{"AK\x00IA" + strings.Repeat("A", 16)}, true},
		{"one character short", []string{"AKIA" + strings.Repeat("A", 15)}, false},
		{"Slack tokens start with a digit", []string{"xoxb-" + "your-token-here"}, false},
		{"hyphenated prose is not a key", []string{"risk-assessment-framework-for-the-team"}, false},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := secretguard.Check(c.contents).Action == ir.Block; got != c.blocked {
				t.Fatalf("Check(%q) blocked = %v; want %v", c.contents, got, c.blocked)
			}
		})
	}
}
