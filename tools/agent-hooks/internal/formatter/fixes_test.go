package formatter_test

// The old formatter script's bug that the port fixes, kept apart from the
// faithful port (formatter_test.go). The fix is defined by an edit to the
// script (scripts/old_script_fixes.py), and the corpus marks every scenario
// it changes with its ID.

import (
	"slices"
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/formatter"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
)

func TestFixedOnePathAFilePathNamesOneFile(t *testing.T) {
	// fixed-one-path: the old script formatted each line of file_path, NULs
	// and trailing newlines dropped, so it could format a file the tool never
	// wrote. A string file_path names one file, exactly as given; only a
	// patch names several.
	cases := []struct {
		name   string
		fields map[string]ir.Value
		want   []string
	}{
		{"a newline inside", map[string]ir.Value{ir.FieldFilePath: str("/w/dir\n/tmp/victim.go")}, []string{"/w/dir\n/tmp/victim.go"}},
		{"a newline at the end", map[string]ir.Value{ir.FieldFilePath: str("b.go\n")}, []string{"b.go\n"}},
		{"a newline in a Go file's name", map[string]ir.Value{ir.FieldFilePath: str("a\nb.go")}, []string{"a\nb.go"}},
		{"a NUL stays, and names no file", map[string]ir.Value{ir.FieldFilePath: str("b.\x00go")}, []string{"b.\x00go"}},
		{"a plain path", map[string]ir.Value{ir.FieldFilePath: str("/w/a.py")}, []string{"/w/a.py"}},
		// A newline alone is a name too, of no file: no fallback to the patch.
		{
			"a newline alone, with a patch",
			map[string]ir.Value{ir.FieldFilePath: str("\n"), ir.FieldCommand: str(patchFormatting)},
			[]string{"\n"},
		},
		// As before: an empty file_path falls back to the patch.
		{
			"an empty file path, then the patch",
			map[string]ir.Value{ir.FieldFilePath: str(""), ir.FieldCommand: str(patchFormatting)},
			[]string{"a.py", "b.go"},
		},
	}
	for _, c := range cases {
		if got := formatter.Paths(ir.Call{Fields: c.fields}); !slices.Equal(got, c.want) {
			t.Errorf("%s: Paths = %q, want %q", c.name, got, c.want)
		}
	}
}
