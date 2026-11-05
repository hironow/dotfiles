package fileguard_test

import (
	"fmt"
	"slices"
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/applypatch"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/fileguard"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/guardcorpus"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
)

func TestCheckAgreesWithTheShellGuardOnTheCorpus(t *testing.T) {
	for _, entry := range guardcorpus.FilesGuardEntries(t) {
		t.Run(fmt.Sprintf("%s/line-%d", entry.Frame(), entry.Line), func(t *testing.T) {
			// given an input of the corpus, as Claude Code or Codex hands it over
			var paths []string
			if entry.FilePath != nil {
				paths = []string{*entry.FilePath}
			} else {
				paths = applypatch.FilePaths(*entry.Patch)
			}
			// when the guard checks its paths, with no basename(1) to ask
			outcome := fileguard.Check(paths)
			// then it blocks, with the same reason, exactly when the shell
			// guard (with its bugs fixed, where the entry says) exited 2
			want := entry.Expected(t)
			if want.Exit != 2 {
				if outcome.Action != ir.Pass {
					t.Fatalf("Check(%q) blocked (%s); the shell guard exited %d", paths, outcome.Reason, want.Exit)
				}
				return
			}
			if outcome.Action != ir.Block || outcome.Reason != *want.Reason {
				t.Fatalf("Check(%q) = %v %q; the shell guard blocked: %q",
					paths, outcome.Action, outcome.Reason, *want.Reason)
			}
			// and the block names a rule the guard lists, for the log
			if !slices.Contains(fileguard.Rules(), outcome.Rule) {
				t.Fatalf("Check(%q) blocked by rule %q, which Rules() does not list", paths, outcome.Rule)
			}
		})
	}
}

func TestEveryBlockNamesItsRule(t *testing.T) {
	cases := []struct {
		path string
		rule string
	}{
		{"x/docker-compose.yaml", fileguard.RuleComposeV1},
		{"docker-compose.yml", fileguard.RuleComposeV1},
		{".github/workflows/ci.yml", fileguard.RuleYMLExtension},
	}
	for _, c := range cases {
		outcome := fileguard.Check([]string{c.path})
		if outcome.Action != ir.Block || outcome.Rule != c.rule {
			t.Errorf("Check(%q) = %v rule %q; want block by %q", c.path, outcome.Action, outcome.Rule, c.rule)
		}
	}
}

// The shell guard's quirks, spelled out.
func TestCheckKeepsTheShellGuardsQuirks(t *testing.T) {
	// The guard's quirks the port keeps; its bugs, which it fixes, are in
	// fixes_test.go.
	cases := []struct {
		name    string
		paths   []string
		blocked bool
	}{
		{"each line of a path is a path", []string{"a.yaml\nb.yml"}, true},
		{"a lone - is a name", []string{"-", "a.yml"}, true},
		{"the instruction files may name examples", []string{"/repo/docs/agents/x.yml"}, false},
		{"trailing slashes are not part of the name", []string{"a.yml/"}, true},
		{"bash drops NUL bytes", []string{"x\x00.yml"}, true},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := fileguard.Check(c.paths).Action == ir.Block; got != c.blocked {
				t.Fatalf("Check(%q) blocked = %v; want %v", c.paths, got, c.blocked)
			}
		})
	}
}
