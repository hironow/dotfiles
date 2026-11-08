package commandguard_test

import (
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/commandguard"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
)

func TestCommandOfReadsTheCallAsThePythonGuardDoes(t *testing.T) {
	// main(): the command is analyzed when it is a string that is not blank
	// by Python's str.strip(); anything else passes.
	str := func(text string) map[string]ir.Value {
		return map[string]ir.Value{ir.FieldCommand: {Text: text, IsString: true}}
	}
	cases := []struct {
		name   string
		fields map[string]ir.Value
		want   string
		ok     bool
	}{
		{"a command", str("npm ci"), "npm ci", true},
		{"kept as it is, spaces and all", str("  ls \n"), "  ls \n", true},
		{"no command", map[string]ir.Value{}, "", false},
		{"an empty command", str(""), "", false},
		{"ASCII white space only", str(" \t\n\r\v\f"), "", false},
		{"Python white space only", str("\u3000 \x1c\x1f \u0085"), "", false},
		{"a zero-width space is not white space", str("\u200b"), "\u200b", true},
		{"a number", map[string]ir.Value{ir.FieldCommand: {Text: "1"}}, "", false},
		{"an array", map[string]ir.Value{ir.FieldCommand: {Text: `["npm ci"]`}}, "", false},
		{"another field", map[string]ir.Value{ir.FieldContent: {Text: "npm ci", IsString: true}}, "", false},
	}
	for _, c := range cases {
		// The script reads the command whatever the tool is.
		for _, tool := range tools {
			got, ok := commandguard.CommandOf(ir.Call{Tool: tool.name, Kind: tool.kind, Fields: c.fields})
			if got != c.want || ok != c.ok {
				t.Errorf("%s, tool %q: CommandOf = %q, %v; want %q, %v", c.name, tool.name, got, ok, c.want, c.ok)
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
