package secretguard

import (
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/applypatch"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/bashsubst"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
)

// Contents returns the texts the shell guard checks in a call.
//
// A content field that is a string is read as $(jq -r ...) leaves it. When
// that is empty, the guard reads the lines the apply_patch patch in the
// command field adds instead. A content of any other type is checked as the
// JSON text jq prints for it, with no fallback: its strings stay escaped, so
// a NUL inside one stays \u0000 and joins no token.
func Contents(call ir.Call) []string {
	if value, ok := call.Fields[ir.FieldContent]; ok {
		if !value.IsString {
			return []string{value.Text}
		}
		if text := bashsubst.Output(value.Text); text != "" {
			return []string{text}
		}
	}
	if value, ok := call.Fields[ir.FieldCommand]; ok && value.IsString {
		if added := applypatch.AddedLines(value.Text); added != "" {
			return []string{added}
		}
	}
	return nil
}
