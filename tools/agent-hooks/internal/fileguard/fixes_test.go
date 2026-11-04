package fileguard_test

// The old shell guard's bugs that the port fixes, kept apart from the
// faithful port (guard_test.go, call_test.go). Each fix is defined by an edit
// to the shell guard (scripts/old_script_fixes.py), and the corpus marks every
// input it changes with its ID.

import (
	"slices"
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/fileguard"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
)

func TestFixedDashLineEveryLineIsChecked(t *testing.T) {
	// fixed-dash-line: the old guard ran basename(1) on each line. A line that
	// starts with "-" made it fail (or, on GNU, print a message), the guard
	// exited 1, which no harness blocks on, and no later line was checked.
	tests := []struct {
		paths []string
		rule  string // "" for a pass
	}{
		{[]string{"ok\n--bogus\nbad.yml"}, fileguard.RuleYMLExtension},
		{[]string{"--x.yml"}, fileguard.RuleYMLExtension},
		{[]string{"--help\na.yml"}, fileguard.RuleYMLExtension},
		{[]string{"--\ndocker-compose.yaml"}, fileguard.RuleComposeV1},
		{[]string{"--bogus", "bad.yml"}, fileguard.RuleYMLExtension},
		// A "-" line itself is a path like any other.
		{[]string{"--help"}, ""},
		{[]string{"-"}, ""},
		{[]string{"-x/docs/agents/a.yml"}, ""},
	}
	for _, test := range tests {
		got := fileguard.Check(test.paths)
		if got.Rule != test.rule || (got.Action == ir.Block) != (test.rule != "") {
			t.Errorf("Check(%q) = %+v, want rule %q", test.paths, got, test.rule)
		}
	}
}

func TestFixedNotebookPathIsCheckedBesideTheFilePath(t *testing.T) {
	// fixed-notebook-path: the old guard read file_path only, so NotebookEdit's
	// notebook_path was never checked. It is now read on its own, after what
	// the old guard read, so an empty or safe file_path cannot hide it, and a
	// blocked file_path still blocks.
	str := func(text string) ir.Value { return ir.Value{Text: text, IsString: true} }
	tests := []struct {
		name   string
		fields map[string]ir.Value
		paths  []string
		blocks bool
	}{
		{"notebook_path alone", map[string]ir.Value{ir.FieldNotebookPath: str("bad.yml")}, []string{"bad.yml"}, true},
		{
			"an empty file_path",
			map[string]ir.Value{ir.FieldFilePath: str(""), ir.FieldNotebookPath: str("bad.yml")},
			[]string{"bad.yml"},
			true,
		},
		{
			"a safe file_path",
			map[string]ir.Value{ir.FieldFilePath: str("safe.md"), ir.FieldNotebookPath: str("bad.yml")},
			[]string{"safe.md", "bad.yml"},
			true,
		},
		{
			"a blocked file_path still blocks",
			map[string]ir.Value{ir.FieldFilePath: str("bad.yml"), ir.FieldNotebookPath: str("safe.ipynb")},
			[]string{"bad.yml", "safe.ipynb"},
			true,
		},
		{
			"a file_path that is not a string",
			map[string]ir.Value{ir.FieldFilePath: {Text: "1"}, ir.FieldNotebookPath: str("bad.yml")},
			[]string{"bad.yml"},
			true,
		},
		{
			"after a patch",
			map[string]ir.Value{
				ir.FieldCommand:      str("*** Begin Patch\n*** Add File: a.yaml\n+x\n*** End Patch\n"),
				ir.FieldNotebookPath: str("bad.yml"),
			},
			[]string{"a.yaml", "bad.yml"},
			true,
		},
		{"a notebook_path that is not a string", map[string]ir.Value{ir.FieldNotebookPath: {Text: `["bad.yml"]`}}, nil, false},
		{"an empty notebook_path", map[string]ir.Value{ir.FieldNotebookPath: str("\n")}, nil, false},
		{"with fixed-dash-line", map[string]ir.Value{ir.FieldNotebookPath: str("--x.yml")}, []string{"--x.yml"}, true},
	}
	for _, test := range tests {
		paths := fileguard.Paths(ir.Call{Fields: test.fields})
		if !slices.Equal(paths, test.paths) {
			t.Errorf("%s: Paths = %q, want %q", test.name, paths, test.paths)
		}
		if got := fileguard.Check(paths); (got.Action == ir.Block) != test.blocks {
			t.Errorf("%s: Check(%q) = %+v, want blocked %v", test.name, paths, got, test.blocks)
		}
	}
}

func TestFixedDocsAgentsRelativeIsExempt(t *testing.T) {
	// fixed-docs-agents-relative: the old guard's exemption */docs/agents/*
	// needs a "/" before docs, so a relative path under docs/agents/ (Codex's
	// patch names its files relative to the session) was blocked, though a
	// bare AGENTS.md or CLAUDE.md is exempt.
	tests := []struct {
		path string
		rule string // "" for a pass
	}{
		{"docs/agents/x.yml", ""},
		{"docs/agents/docker-compose.yml", ""},
		{"docs/agents/sub/x.yml", ""},
		// what is not under docs/agents/ is checked as before
		{"docs/agentsx/x.yml", fileguard.RuleYMLExtension},
		{"xdocs/agents/x.yml", fileguard.RuleYMLExtension},
		{"docs/agents.yml", fileguard.RuleYMLExtension},
		{"docs/x.yml", fileguard.RuleYMLExtension},
		{"docs/agents", ""},
	}
	for _, test := range tests {
		got := fileguard.Check([]string{test.path})
		if got.Rule != test.rule || (got.Action == ir.Block) != (test.rule != "") {
			t.Errorf("Check(%q) = %+v, want rule %q", test.path, got, test.rule)
		}
	}
}

func TestFixedDocsAgentsRelativeHoldsOnlyWhereAPathStarts(t *testing.T) {
	// fixed-docs-agents-relative exempts a relative path under docs/agents/,
	// so it holds only for a line where a path starts: the first line of each
	// path Check is given (a file_path, each file of a patch, a
	// notebook_path). A later line is part of the same path: /w/x, a
	// newline, and docs/agents/y.yml names a file under no docs/agents/
	// directory, and the old guard blocked it. The old exemptions still hold
	// on every line.
	tests := []struct {
		paths []string
		rule  string // "" for a pass
	}{
		{[]string{"/w/x\ndocs/agents/y.yml"}, fileguard.RuleYMLExtension},
		{[]string{"\ndocs/agents/y.yml"}, fileguard.RuleYMLExtension},
		{[]string{"docs/agents/a\ndocs/agents/y.yml"}, fileguard.RuleYMLExtension},
		{[]string{"docs/agents/y.yml\nz.yml"}, fileguard.RuleYMLExtension},
		{[]string{"/w/x\ndocs/agents/docker-compose.yml"}, fileguard.RuleComposeV1},
		// each path starts at its own first line
		{[]string{"/w/a.md", "docs/agents/y.yml"}, ""},
		{[]string{"docs/agents/y.yml\n/w/a.md"}, ""},
		// the old exemptions hold on every line
		{[]string{"x\n/docs/agents/y.yml"}, ""},
		{[]string{"x\nCLAUDE.md"}, ""},
	}
	for _, test := range tests {
		got := fileguard.Check(test.paths)
		if got.Rule != test.rule || (got.Action == ir.Block) != (test.rule != "") {
			t.Errorf("Check(%q) = %+v, want rule %q", test.paths, got, test.rule)
		}
	}
}
