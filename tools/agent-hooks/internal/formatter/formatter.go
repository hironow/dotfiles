// Package formatter is the formatter hook, run after a file is written or
// edited: Python files through ruff (under uv), Go files through gofmt. It
// cannot undo the edit; it formats the file and reports what ruff still finds.
//
// It is a port of ROOT_AGENTS_hooks_format-after-edit.sh. This package is the
// pure part: which paths a call names, which commands format a path, and what
// to report. The shell checks the files, finds the programs, and runs them.
package formatter

import (
	"strings"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/applypatch"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/bashsubst"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
)

// cleanRuff is what `ruff check` prints when it finds nothing.
const cleanRuff = "All checks passed"

// Paths returns the paths the formatter considers in a call, each line of
// them a path. A file_path that is a string is read as $(jq -r ...) leaves
// it. When that is empty, the patch in the command field names the paths
// (applypatch.FormattedPaths). A file_path of another type prints as JSON
// text, no line of which ends in a suffix the formatter knows, so it names
// none.
//
// A file path that could not be resolved as the harness resolves it
// (ir.Call.PathUnresolved) names no file.
func Paths(call ir.Call) []string {
	if call.PathUnresolved {
		return nil
	}
	if value, ok := call.Fields[ir.FieldFilePath]; ok {
		if !value.IsString {
			return nil
		}
		// fixed-one-path: the script formatted each line of file_path, NULs
		// and trailing newlines dropped, and so could format a file the tool
		// never wrote. The whole string names one file.
		if value.Text != "" {
			return []string{value.Text}
		}
	}
	if value, ok := call.Fields[ir.FieldCommand]; ok && value.IsString {
		return applypatch.FormattedPaths(bashsubst.Output(value.Text))
	}
	return nil
}

// Formatting is how one file is formatted: the program that must be on PATH
// and the commands to run, in order, each starting with the program.
type Formatting struct {
	Program  string
	Commands [][]string
	// Reported is the index of the command whose output (stdout and stderr
	// together) Notice reports, or -1.
	Reported int
}

// For returns how a path is formatted, by its suffix: .py through ruff under
// uv (format, fix, then the check whose findings are reported), .go through
// gofmt. ok is false for any other path.
func For(path string) (Formatting, bool) {
	switch {
	case strings.HasSuffix(path, ".py"):
		// --frozen: never touch uv.lock; the lint group holds ruff.
		ruff := []string{"uv", "run", "--frozen", "--only-group", "lint", "ruff"}
		return Formatting{
			Program: "uv",
			Commands: [][]string{
				append(append([]string(nil), ruff...), "format", path),
				append(append([]string(nil), ruff...), "check", "--fix", path),
				append(append([]string(nil), ruff...), "check", path),
			},
			Reported: 2,
		}, true
	case strings.HasSuffix(path, ".go"):
		return Formatting{Program: "gofmt", Commands: [][]string{{"gofmt", "-w", path}}, Reported: -1}, true
	default:
		return Formatting{}, false
	}
}

// Notice is what the formatter reports for the reported command's output, as
// $(...) captured it (bashsubst.Output): nothing when the output is empty or
// says all checks passed, else the path and the output.
func Notice(path, output string) string {
	if output == "" || strings.Contains(output, cleanRuff) {
		return ""
	}
	return "ruff still reports issues in " + path + ":\n" + output + "\n"
}
