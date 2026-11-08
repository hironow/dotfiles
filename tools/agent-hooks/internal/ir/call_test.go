package ir_test

import (
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
)

func str(text string) ir.Value  { return ir.Value{Text: text, IsString: true} }
func json(text string) ir.Value { return ir.Value{Text: text} }

func TestMappingMismatch(t *testing.T) {
	cases := []struct {
		name string
		call ir.Call
		want bool
	}{
		{"a shell with its command", ir.Call{Kind: ir.KindShell, Fields: map[string]ir.Value{"command": str("ls")}}, false},
		{"a shell with an empty command", ir.Call{Kind: ir.KindShell, Fields: map[string]ir.Value{"command": str("")}}, false},
		{"a shell without a command", ir.Call{Kind: ir.KindShell, Fields: map[string]ir.Value{}}, true},
		{"a shell with a number for a command", ir.Call{Kind: ir.KindShell, Fields: map[string]ir.Value{"command": json("1")}}, true},
		{"a write with its path and content", ir.Call{Kind: ir.KindWrite, Fields: map[string]ir.Value{
			"filePath": str("a.go"), "content": str("x"),
		}}, false},
		{"a write without content", ir.Call{Kind: ir.KindWrite, Fields: map[string]ir.Value{"filePath": str("a.go")}}, true},
		{"a write without a path", ir.Call{Kind: ir.KindWrite, Fields: map[string]ir.Value{"content": str("x")}}, true},
		{"a write with an object for a path", ir.Call{Kind: ir.KindWrite, Fields: map[string]ir.Value{
			"filePath": json(`{"a":1}`), "content": str("x"),
		}}, true},
		{"an edit with its content", ir.Call{Kind: ir.KindEdit, Fields: map[string]ir.Value{
			"filePath": str("a.go"), "content": str("x"),
		}}, false},
		{"an edit with its contents", ir.Call{
			Kind: ir.KindEdit, Fields: map[string]ir.Value{"filePath": str("a.go")},
			Lists: map[string][]ir.Value{"contents": {str("x"), str("y")}},
		}, false},
		{"an edit with neither", ir.Call{Kind: ir.KindEdit, Fields: map[string]ir.Value{"filePath": str("a.go")}}, true},
		{"an edit with a number among its contents", ir.Call{
			Kind: ir.KindEdit, Fields: map[string]ir.Value{"filePath": str("a.go")},
			Lists: map[string][]ir.Value{"contents": {str("x"), json("2")}},
		}, true},
		{"a notebook edit with its path, no source (a delete)", ir.Call{Kind: ir.KindNotebook, Fields: map[string]ir.Value{
			"notebookPath": str("a.ipynb"),
		}}, false},
		{"a notebook edit without its path", ir.Call{Kind: ir.KindNotebook, Fields: map[string]ir.Value{"content": str("x")}}, true},
		{"a patch with its text", ir.Call{Kind: ir.KindPatch, Fields: map[string]ir.Value{"command": str("*** Begin Patch")}}, false},
		{"a patch without its text", ir.Call{Kind: ir.KindPatch, Fields: map[string]ir.Value{}}, true},
		{"a call of no kind promises nothing", ir.Call{Fields: map[string]ir.Value{}}, false},
		// Codex's example: an unmapped tool whose command is a number, which
		// passes both schemas and which the command guard cannot read.
		{"a call of no kind with a number for a command", ir.Call{Fields: map[string]ir.Value{"command": json("123")}}, true},
		{"a number for a cwd", ir.Call{Kind: ir.KindShell, Fields: map[string]ir.Value{
			"command": str("ls"), "cwd": json("1"),
		}}, true},
		{"a number among the workspaces", ir.Call{
			Kind: ir.KindShell, Fields: map[string]ir.Value{"command": str("ls")},
			Lists: map[string][]ir.Value{"workspaces": {str("/w"), json("3")}},
		}, true},
		{"ids of any type, only hashed", ir.Call{Kind: ir.KindShell, Fields: map[string]ir.Value{
			"command": str("ls"), "sessionId": json("7"), "callId": json(`{"a":1}`),
		}}, false},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			// given a decoded call, when the log asks whether its IR holds what
			// its kind promises, with each field's type
			got := c.call.MappingMismatch()
			// then only a missing or mistyped field is a mismatch
			if got != c.want {
				t.Fatalf("MappingMismatch() = %v, want %v", got, c.want)
			}
		})
	}
}
