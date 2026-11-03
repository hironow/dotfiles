package commandguard

import (
	"strings"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
)

// CommandOf returns the command the Python guard's main() analyzes in a call:
// the command field, when it is a string that Python's str.strip() does not
// leave empty. A call without one passes unanalyzed.
func CommandOf(call ir.Call) (string, bool) {
	value, ok := call.Fields[ir.FieldCommand]
	if !ok || !value.IsString || strings.TrimFunc(value.Text, isPythonSpace) == "" {
		return "", false
	}
	return value.Text, true
}
