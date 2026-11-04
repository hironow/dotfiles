package secretguard_test

import (
	"slices"
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/secretguard"
)

func TestContentsReadsTheCallAsTheShellGuardDoes(t *testing.T) {
	str := func(text string) ir.Value { return ir.Value{Text: text, IsString: true} }
	patch := "*** Begin Patch\n*** Add File: a.txt\n+one\n-gone\n+two\n*** End Patch"
	cases := []struct {
		name   string
		fields map[string]ir.Value
		want   []string
	}{
		{"content", map[string]ir.Value{ir.FieldContent: str("text")}, []string{"text"}},
		{"NULs go, then trailing newlines", map[string]ir.Value{ir.FieldContent: str("a\x00b\n\n")}, []string{"ab"}},
		{
			"content wins over a patch",
			map[string]ir.Value{ir.FieldContent: str("text"), ir.FieldCommand: str(patch)},
			[]string{"text"},
		},
		{
			"content that prints empty falls back to the patch's added lines",
			map[string]ir.Value{ir.FieldContent: str("\n"), ir.FieldCommand: str(patch)},
			[]string{"one\ntwo"},
		},
		{
			"empty content falls back too",
			map[string]ir.Value{ir.FieldContent: str(""), ir.FieldCommand: str(patch)},
			[]string{"one\ntwo"},
		},
		{
			"non-string content is checked as its JSON text, with no fallback",
			map[string]ir.Value{ir.FieldContent: {Text: `["a\u0000b"]`}, ir.FieldCommand: str(patch)},
			[]string{`["a\u0000b"]`},
		},
		{"no content: the patch", map[string]ir.Value{ir.FieldCommand: str(patch)}, []string{"one\ntwo"}},
		{"no content: a command that is not a patch", map[string]ir.Value{ir.FieldCommand: str("echo +x")}, nil},
		{"no content: a patch that is not a string", map[string]ir.Value{ir.FieldCommand: {Text: "1"}}, nil},
		{"nothing", map[string]ir.Value{}, nil},
	}
	for _, c := range cases {
		// The script reads the contents whatever the tool is.
		for _, tool := range tools {
			if got := secretguard.Contents(ir.Call{Tool: tool.name, Kind: tool.kind, Fields: c.fields}); !slices.Equal(got, c.want) {
				t.Errorf("%s, tool %q: Contents = %q, want %q", c.name, tool.name, got, c.want)
			}
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

func TestContentsReadsEveryReplacementOfAnEdit(t *testing.T) {
	// Pi's edit makes one or more replacements, each newText an element of
	// the contents list. Each is read as a content field is, beside one.
	str := func(text string) ir.Value { return ir.Value{Text: text, IsString: true} }
	list := func(values ...ir.Value) map[string][]ir.Value { return map[string][]ir.Value{ir.ListContents: values} }
	cases := []struct {
		name string
		call ir.Call
		want []string
	}{
		{"each element", ir.Call{Lists: list(str("one"), str("two"))}, []string{"one", "two"}},
		{"NULs go, then trailing newlines", ir.Call{Lists: list(str("a\x00b\n\n"))}, []string{"ab"}},
		{"an element that prints empty adds nothing", ir.Call{Lists: list(str("\n"), str("x"))}, []string{"x"}},
		{"a non-string element is read as its JSON text", ir.Call{Lists: list(ir.Value{Text: `{"a":1}`})}, []string{`{"a":1}`}},
		{
			"beside a content field",
			ir.Call{Fields: map[string]ir.Value{ir.FieldContent: str("c")}, Lists: list(str("e"))},
			[]string{"c", "e"},
		},
		{"an empty list", ir.Call{Lists: list()}, nil},
	}
	for _, c := range cases {
		if got := secretguard.Contents(c.call); !slices.Equal(got, c.want) {
			t.Errorf("%s: Contents = %q, want %q", c.name, got, c.want)
		}
	}
}
