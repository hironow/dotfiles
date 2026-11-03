package fileguard_test

import (
	"slices"
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/fileguard"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
)

const patchAddingYML = "*** Begin Patch\n*** Add File: a.yml\n+x\n*** End Patch"

func TestPathsReadsTheCallAsTheShellGuardDoes(t *testing.T) {
	str := func(text string) ir.Value { return ir.Value{Text: text, IsString: true} }
	cases := []struct {
		name   string
		fields map[string]ir.Value
		want   []string
	}{
		{"a file path", map[string]ir.Value{ir.FieldFilePath: str("a.yml")}, []string{"a.yml"}},
		{
			"a file path wins over a patch",
			map[string]ir.Value{ir.FieldFilePath: str("a.yaml"), ir.FieldCommand: str(patchAddingYML)},
			[]string{"a.yaml"},
		},
		{"NULs go, then trailing newlines", map[string]ir.Value{ir.FieldFilePath: str("a.\x00yml\n\n")}, []string{"a.yml"}},
		{"an inner newline stays", map[string]ir.Value{ir.FieldFilePath: str("a\nb.yml")}, []string{"a\nb.yml"}},
		{
			"a path that prints empty falls back to the patch",
			map[string]ir.Value{ir.FieldFilePath: str("\n\x00\n"), ir.FieldCommand: str(patchAddingYML)},
			[]string{"a.yml"},
		},
		{
			"an empty path falls back to the patch",
			map[string]ir.Value{ir.FieldFilePath: str(""), ir.FieldCommand: str(patchAddingYML)},
			[]string{"a.yml"},
		},
		{
			"a non-string path names no file and does not fall back",
			map[string]ir.Value{ir.FieldFilePath: {Text: "0"}, ir.FieldCommand: str(patchAddingYML)},
			nil,
		},
		{"no path: the patch", map[string]ir.Value{ir.FieldCommand: str(patchAddingYML)}, []string{"a.yml"}},
		{"no path: a command that is not a patch", map[string]ir.Value{ir.FieldCommand: str("ls a.yml")}, nil},
		{
			"no path: a patch that is not a string",
			map[string]ir.Value{ir.FieldCommand: {Text: `["` + "*** Begin Patch\\n*** Add File: a.yml" + `"]`}},
			nil,
		},
		{"nothing", map[string]ir.Value{}, nil},
	}
	for _, c := range cases {
		// The script reads the paths whatever the tool is.
		for _, tool := range tools {
			if got := fileguard.Paths(ir.Call{Tool: tool.name, Kind: tool.kind, Fields: c.fields}); !slices.Equal(got, c.want) {
				t.Errorf("%s, tool %q: Paths = %q, want %q", c.name, tool.name, got, c.want)
			}
		}
	}
}

func TestNeedsBasenameOnlyForAPathTheFlavorsReadApart(t *testing.T) {
	// BSD's and GNU's basename part ways only on --help, --version, and
	// their prefixes: GNU's succeeds on them, and the guard reads on.
	cases := []struct {
		paths []string
		want  bool
	}{
		{[]string{"a.yml"}, false},
		{[]string{"-"}, false},
		{[]string{"-x\na.yml"}, false},
		{[]string{"--"}, false},
		{[]string{"--help\na.yml"}, true},
		{[]string{"--h"}, true},
		{[]string{"a.yaml", "b\n--vers"}, true},
		{[]string{"--\x00help"}, true},
		{[]string{"--helpx"}, false},
		{nil, false},
	}
	for _, c := range cases {
		if got := fileguard.NeedsBasename(c.paths); got != c.want {
			t.Errorf("NeedsBasename(%q) = %v, want %v", c.paths, got, c.want)
		}
	}
}

// tools are calls' tools that must not change the reading: none, one no
// definition maps, and known tools of other kinds.
var tools = []struct{ name, kind string }{
	{"", ""},
	{"future_tool", ""},
	{"Bash", ir.KindShell},
	{"Write", ir.KindWrite},
	{"apply_patch", ir.KindPatch},
}
