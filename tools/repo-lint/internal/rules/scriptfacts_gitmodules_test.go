package rules

import "testing"

const gitmodulesFixture = `[submodule "public"]
	path = public
	update = none
[submodule "private"]
	update = none
`

func TestGitmodulesSkipAll(t *testing.T) {
	const test = "test_every_submodule_is_skipped_by_default"
	runCases(t, gitmodulesSkipAll(), func() Inputs { return Inputs{gitmodulesPath: gitmodulesFixture} }, []ruleCase{
		{"no sections", edit(gitmodulesPath, gitmodulesFixture, ""), test},
		{"checkout enabled", edit(gitmodulesPath, "update = none", "update = checkout"), test},
		{"no update setting", edit(gitmodulesPath, "\tupdate = none\n", ""), test},
	})
}

func TestGitmodulesSkipAllReadsLikePython(t *testing.T) {
	for _, c := range []struct {
		name, text string
		fails      bool
	}{
		{"Unicode spaces", "[submodule \"x\"]\n \u0085update\u00a0=\u2003none\u001c\n", false},
		{"Unicode in value", "[submodule \"x\"]\n update = noné\n", true},
		{"CRLF", "[submodule \"x\"]\r\n\tupdate = none\r\n", false},
		{"lone CR", "[submodule \"x\"]\r\tupdate = none\r", false},
		{"last duplicate section wins", "[submodule \"x\"]\n update = checkout\n[submodule \"x\"]\n update = none\n", false},
		{"last duplicate section fails", "[submodule \"x\"]\n update = none\n[submodule \"x\"]\n update = checkout\n", true},
		{"first duplicate setting wins", "[submodule \"x\"]\n update = none\n update = checkout\n", false},
		{"first duplicate setting fails", "[submodule \"x\"]\n update = checkout\n update = none\n", true},
		{"value may follow newline", "[submodule \"x\"]\n update =\n none\n", false},
		{"no final newline", "[submodule \"x\"]\n update = none", false},
		{"undiscovered sections ignored", "[submodule \"x\"]\n update = none\n[submodule 'y']\n update = checkout\n", false},
		{"single quotes not discovered", "[submodule 'x']\n update = none\n", true},
		{"header without newline", "[submodule \"x\"]", true},
		{"blank line ends body", "[submodule \"x\"]\n\n update = none\n", true},
		{"Unicode indentation not discovered", "[submodule \"x\"]\n\u00a0update = none\n", true},
		{"inline comment not accepted", "[submodule \"x\"]\n update = none # skip\n", true},
		{"case preserved", "[submodule \"x\"]\n update = NONE\n", true},
	} {
		t.Run(c.name, func(t *testing.T) {
			got := findingsOf(t, gitmodulesSkipAll(), Inputs{gitmodulesPath: c.text})
			if (len(got) > 0) != c.fails {
				t.Errorf("findings = %v, want failure %t", got, c.fails)
			}
		})
	}
}
