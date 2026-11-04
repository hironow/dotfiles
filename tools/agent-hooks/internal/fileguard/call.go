package fileguard

import (
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
//
// fixed-notebook-path: NotebookEdit's notebook_path, which the shell guard
// never read, comes after those, read the same way, so neither an empty nor
// a safe file_path hides it.
func Paths(call ir.Call) []string {
	paths := filePaths(call)
	if value, ok := call.Fields[ir.FieldNotebookPath]; ok && value.IsString {
		if path := bashsubst.Output(value.Text); path != "" {
			paths = append(paths, path)
		}
	}
	return paths
}

// filePaths is what the shell guard read: file_path, else a patch's files.
func filePaths(call ir.Call) []string {
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
