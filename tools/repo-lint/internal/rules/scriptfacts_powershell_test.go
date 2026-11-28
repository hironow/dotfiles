package rules

import (
	"strings"
	"testing"
)

func powershellBase() Inputs {
	return Inputs{powershellGlob: map[string]any{"scripts/gc.ps1": "# ASCII\r\nWrite-Output ok\n"}}
}

func TestPowershellASCIIOnly(t *testing.T) {
	for _, tc := range []struct{ name, text string }{
		{"BOM", "\ufeff# ASCII\n"},
		{"non ASCII", "# caf\u00e9\n"},
		{"invalid UTF-8", "# \xff\n"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			in := powershellBase()
			in[powershellGlob].(map[string]any)["scripts/gc.ps1"] = tc.text
			got := findingsOf(t, powershellASCIIOnly(), in)
			if len(got) == 0 || !strings.Contains(got[0].Message, "test_windows_scripts_are_ascii_only") {
				t.Fatalf("findings = %v", got)
			}
		})
	}
}

func TestPowershellSplitlinesSeparatorsPass(t *testing.T) {
	for _, text := range []string{"", "# a\u0085# b\u2028# c\u2029", "# a\r# b\r\n# c\n"} {
		in := powershellBase()
		in[powershellGlob].(map[string]any)["scripts/gc.ps1"] = text
		if got := findingsOf(t, powershellASCIIOnly(), in); len(got) != 0 {
			t.Errorf("%q: %v", text, got)
		}
	}
}
