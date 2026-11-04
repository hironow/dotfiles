package formatter_test

import (
	"slices"
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/formatter"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
)

func str(text string) ir.Value { return ir.Value{Text: text, IsString: true} }

const patchFormatting = "*** Begin Patch\n*** Update File: a.py\n@@\n-x\n+y\n*** Add File: b.go\n+package b\n" +
	"*** Delete File: gone.py\n*** End Patch\n"

func TestPathsReadsTheCallAsTheFormatterScriptDoes(t *testing.T) {
	cases := []struct {
		name   string
		fields map[string]ir.Value
		want   []string
	}{
		{"a file path", map[string]ir.Value{ir.FieldFilePath: str("/p/a.py")}, []string{"/p/a.py"}},
		{"each line is a path", map[string]ir.Value{ir.FieldFilePath: str("a.py\nb.go")}, []string{"a.py", "b.go"}},
		{"NULs go, then trailing newlines", map[string]ir.Value{ir.FieldFilePath: str("a.\x00py\n\n")}, []string{"a.py"}},
		{
			"a file path wins over a patch",
			map[string]ir.Value{ir.FieldFilePath: str("a.go"), ir.FieldCommand: str(patchFormatting)},
			[]string{"a.go"},
		},
		{
			"an empty file path falls back to the patch",
			map[string]ir.Value{ir.FieldFilePath: str("\n"), ir.FieldCommand: str(patchFormatting)},
			[]string{"a.py", "b.go"},
		},
		{"no file path: the patch", map[string]ir.Value{ir.FieldCommand: str(patchFormatting)}, []string{"a.py", "b.go"}},
		{
			"a move names the old and the new path",
			map[string]ir.Value{ir.FieldCommand: str("*** Begin Patch\n*** Update File: a.py\n*** Move to: b.py\n")},
			[]string{"a.py", "b.py"},
		},
		{"a command that is not a patch", map[string]ir.Value{ir.FieldCommand: str("ls a.py")}, nil},
		{
			// jq prints it as JSON text, and no line of that ends in .py or .go
			"a file path that is not a string",
			map[string]ir.Value{ir.FieldFilePath: {Text: `["a.py"]`}, ir.FieldCommand: str(patchFormatting)},
			nil,
		},
		{"a patch that is not a string", map[string]ir.Value{ir.FieldCommand: {Text: `["*** Begin Patch"]`}}, nil},
		{"nothing", map[string]ir.Value{}, nil},
	}
	for _, c := range cases {
		if got := formatter.Paths(ir.Call{Fields: c.fields}); !slices.EqualFunc(got, c.want, func(a, b string) bool { return a == b }) {
			t.Errorf("%s: Paths = %q, want %q", c.name, got, c.want)
		}
	}
}

func TestForNamesTheCommandsOfEachSuffix(t *testing.T) {
	uv := func(args ...string) []string {
		return append([]string{"uv", "run", "--frozen", "--only-group", "lint", "ruff"}, args...)
	}
	cases := []struct {
		path string
		want formatter.Formatting
		ok   bool
	}{
		{"a.py", formatter.Formatting{
			Program: "uv",
			Commands: [][]string{
				uv("format", "a.py"),
				uv("check", "--fix", "a.py"),
				uv("check", "a.py"),
			},
			Reported: 2,
		}, true},
		{"/x y/m.go", formatter.Formatting{Program: "gofmt", Commands: [][]string{{"gofmt", "-w", "/x y/m.go"}}, Reported: -1}, true},
		{".py", formatter.Formatting{
			Program:  "uv",
			Commands: [][]string{uv("format", ".py"), uv("check", "--fix", ".py"), uv("check", ".py")},
			Reported: 2,
		}, true},
		{"-x.go", formatter.Formatting{Program: "gofmt", Commands: [][]string{{"gofmt", "-w", "-x.go"}}, Reported: -1}, true},
		{"a.ts", formatter.Formatting{}, false},
		{"a.PY", formatter.Formatting{}, false},
		{"a.py.txt", formatter.Formatting{}, false},
		{"a.go\r", formatter.Formatting{}, false},
		{"", formatter.Formatting{}, false},
	}
	for _, c := range cases {
		got, ok := formatter.For(c.path)
		if ok != c.ok || got.Program != c.want.Program || got.Reported != c.want.Reported ||
			!slices.EqualFunc(got.Commands, c.want.Commands, slices.Equal) {
			t.Errorf("For(%q) = %+v, %v; want %+v, %v", c.path, got, ok, c.want, c.ok)
		}
	}
}

func TestNoticeReportsWhatRuffStillFinds(t *testing.T) {
	cases := []struct {
		output, want string
	}{
		{"", ""},
		{"All checks passed!", ""},
		{"warning: x\nAll checks passed!", ""},
		{"a.py:1:1: F401 unused\nFound 1 error.", "ruff still reports issues in a.py:\na.py:1:1: F401 unused\nFound 1 error.\n"},
		{"All checks passed", ""},
		{"all checks passed!", "ruff still reports issues in a.py:\nall checks passed!\n"},
		{"error: Failed to spawn: `ruff`", "ruff still reports issues in a.py:\nerror: Failed to spawn: `ruff`\n"},
	}
	for _, c := range cases {
		if got := formatter.Notice("a.py", c.output); got != c.want {
			t.Errorf("Notice(%q) = %q, want %q", c.output, got, c.want)
		}
	}
}
