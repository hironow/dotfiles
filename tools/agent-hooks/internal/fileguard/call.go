package fileguard

import (
	"strings"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/applypatch"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/bashsubst"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
)

// Paths returns the paths the shell guard checks in a call.
//
// A file_path that is a string is read as $(jq -r ...) leaves it. When that
// is empty, the guard reads the files of the apply_patch patch in the command
// field instead. A file_path of any other type prints as JSON text: never
// empty, so no fallback, and every line of it ends in a quote, a comma, a
// bracket, or a literal, so it names no file the rules block.
func Paths(call ir.Call) []string {
	if value, ok := call.Fields[ir.FieldFilePath]; ok {
		if !value.IsString {
			return nil
		}
		if path := bashsubst.Output(value.Text); path != "" {
			return []string{path}
		}
	}
	if value, ok := call.Fields[ir.FieldCommand]; ok && value.IsString {
		return applypatch.FilePaths(value.Text)
	}
	return nil
}

// NeedsBasename reports whether the paths hold a line that BSD's and GNU's
// basename(1) read apart (--help, --version, or a prefix of one), so that
// Check needs the flavor this machine has.
func NeedsBasename(paths []string) bool {
	for _, path := range paths {
		for line := range strings.SplitSeq(strings.ReplaceAll(path, "\x00", ""), "\n") {
			if isGNUInfoOption(line) {
				return true
			}
		}
	}
	return false
}
