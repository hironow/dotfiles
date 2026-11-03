package fileguard_test

import (
	"fmt"
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/applypatch"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/fileguard"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/guardcorpus"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
)

func TestCheckAgreesWithTheShellGuardOnTheCorpus(t *testing.T) {
	for _, entry := range guardcorpus.FilesGuardEntries(t) {
		t.Run(fmt.Sprintf("line-%d", entry.Line), func(t *testing.T) {
			// given an input of the corpus, as Claude Code or Codex hands it over
			var paths []string
			if entry.FilePath != nil {
				paths = []string{*entry.FilePath}
			} else {
				paths = applypatch.FilePaths(*entry.Patch)
			}
			// when the guard checks its paths with BSD's and with GNU's basename
			for _, c := range []struct {
				name     string
				basename fileguard.Basename
				shell    guardcorpus.ShellGuardResult
			}{
				{"BSD", fileguard.BSDBasename, entry.BSD},
				{"GNU", fileguard.GNUBasename, entry.GNU},
			} {
				outcome := fileguard.Check(paths, c.basename)
				// then it blocks, with the same reason, exactly when the shell guard exited 2
				if c.shell.Exit != 2 {
					if outcome.Action != ir.Pass {
						t.Fatalf("%s: Check(%q) blocked (%s); the shell guard exited %d",
							c.name, paths, outcome.Reason, c.shell.Exit)
					}
					continue
				}
				if outcome.Action != ir.Block || outcome.Reason != *c.shell.Reason {
					t.Fatalf("%s: Check(%q) = %v %q; the shell guard blocked: %q",
						c.name, paths, outcome.Action, outcome.Reason, *c.shell.Reason)
				}
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
		outcome := fileguard.Check([]string{c.path}, fileguard.BSDBasename)
		if outcome.Action != ir.Block || outcome.Rule != c.rule {
			t.Errorf("Check(%q) = %v rule %q; want block by %q", c.path, outcome.Action, outcome.Rule, c.rule)
		}
	}
}

// The shell guard's quirks, spelled out.
func TestCheckKeepsTheShellGuardsQuirks(t *testing.T) {
	cases := []struct {
		name     string
		paths    []string
		basename fileguard.Basename
		blocked  bool
	}{
		{"each line of a path is a path", []string{"a.yaml\nb.yml"}, fileguard.BSDBasename, true},
		{"a leading - makes basename fail, which stops the guard", []string{"-x.yml", "a.yml"}, fileguard.BSDBasename, false},
		{"a lone - is a name to basename", []string{"-", "a.yml"}, fileguard.BSDBasename, true},
		{"BSD basename fails on --help too", []string{"--help", "a.yml"}, fileguard.BSDBasename, false},
		{"GNU basename prints its help, and the guard reads on", []string{"--help", "a.yml"}, fileguard.GNUBasename, true},
		{"GNU basename takes a prefix of --version", []string{"--vers", "a.yml"}, fileguard.GNUBasename, true},
		{"GNU basename fails on other options", []string{"--hx", "a.yml"}, fileguard.GNUBasename, false},
		{"the instruction files may name examples", []string{"/repo/docs/agents/x.yml"}, fileguard.BSDBasename, false},
		{"only a docs/agents/ under a directory is exempt", []string{"docs/agents/x.yml"}, fileguard.BSDBasename, true},
		{"trailing slashes are not part of the name", []string{"a.yml/"}, fileguard.BSDBasename, true},
		{"bash drops NUL bytes", []string{"x\x00.yml"}, fileguard.BSDBasename, true},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := fileguard.Check(c.paths, c.basename).Action == ir.Block; got != c.blocked {
				t.Fatalf("Check(%q) blocked = %v; want %v", c.paths, got, c.blocked)
			}
		})
	}
}
