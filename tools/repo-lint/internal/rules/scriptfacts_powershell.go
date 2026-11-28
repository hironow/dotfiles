package rules

import (
	"fmt"
	"slices"
	"strings"
	"unicode/utf8"
)

const powershellGlob = "scripts/*.ps1"

func powershellASCIIOnly() Rule {
	r := factRule("powershell-ascii-only", "PowerShell scripts stay readable in Windows PowerShell 5.1 logs",
		[]string{powershellGlob}, []scriptFact{
			fact("test_windows_scripts_are_ascii_only", powershellASCII),
		})
	check := r.Check
	r.Inputs[0].FilesystemGlob = true
	r.Check = func(in Inputs) []Finding {
		files, _ := in[powershellGlob].(map[string]any)
		paths := make([]string, 0, len(files))
		for path := range files {
			paths = append(paths, path)
		}
		slices.Sort(paths)
		var out []Finding
		for _, path := range paths {
			for _, f := range check(Inputs{powershellGlob: files[path]}) {
				f.Path = path
				out = append(out, f)
			}
		}
		return out
	}
	return r
}

func powershellASCII(files map[string]string) []string {
	text := files[powershellGlob]
	if strings.HasPrefix(text, "\ufeff") {
		return []string{"must not carry a UTF-8 BOM"}
	}
	if !utf8.ValidString(text) {
		return []string{"must decode as strict UTF-8"}
	}
	var out []string
	for n, line := range pySplitlines(text) {
		if strings.ContainsFunc(line, func(ch rune) bool { return ch > 127 }) {
			out = append(out, fmt.Sprintf("line %d must stay ASCII-only: %q", n+1, line))
		}
	}
	return out
}
