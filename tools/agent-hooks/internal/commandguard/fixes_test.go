package commandguard_test

// The old Python guard's bugs that the port fixes, kept apart from the
// faithful port (guard_test.go). Each fix is defined by an edit to the Python
// guard (scripts/old_script_fixes.py), the corpus marks every input it changes
// with its ID, and tests/unit/test_command_guard_bash_oracle.py checks these
// inputs, and more, against what bash itself runs.

import (
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/commandguard"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
)

type fixCase struct {
	command string
	rule    string // "" for a pass
}

func checkFixCases(t *testing.T, cases []fixCase) {
	t.Helper()
	for _, c := range cases {
		got := commandguard.Check(c.command)
		if got.Rule != c.rule || (got.Action == ir.Block) != (c.rule != "") {
			t.Errorf("Check(%q) = %v %q, want rule %q", c.command, got.Action, got.Rule, c.rule)
		}
	}
}

func TestFixedCommandSplitReadsTheTextAsBashDoes(t *testing.T) {
	// fixed-command-split: the old guard split a command with Python's shlex,
	// so a newline, operators written together, a # inside a word, a
	// redirection before the name, substitutions, and the lines after a << in
	// a comment or quotes hid a command bash runs.
	node, yml := commandguard.RuleNodePackages, commandguard.RuleYMLFile
	checkFixCases(t, []fixCase{
		{"cd .\nnpm i", node},
		{"echo x#y; npm i", node},
		{"(cd .);npm i", node},
		{"echo |& npm i", node},
		{"< /dev/null npm i", node},
		{"2>/dev/null npm i", node},
		{"echo `npm i`", node},
		{`echo "$(npm i)"`, node},
		{"cat <(npm i)", node},
		{"$'n\\x70m' i", node},
		{"cat <<< EOF\nnpm i", node},
		{"cat <<EOF\n$(npm i)\nEOF", node},
		{"# <<EOF\n\"npm\" i\nEOF", node},
		{"cat <<EOF\nEO\\\nF\n\"npm\" i", node},
		{"\"npm\" i\necho 'unterminated", node},
		{"cat < /dev/null > x.yml", yml},
		// what bash does not run passes, where the old guard blocked it
		{"echo ';' npm i", ""},
		{"arr=(npm yarn)", ""},
		{"npm#x", ""},
		{"cat <<'EOF'\n$(npm i)\nEOF", ""},
		{"cat <<'EOF'\n  EOF\nnpm i\nEOF", ""},
		{`printf '%s\n' "<(npm i)"`, ""},
		{"cat <<$(npm i)\nbody\n$(npm i)", ""},
		// a compound command with a syntax error: bash runs none of it, the
		// guard blocks on purpose
		{"if true; then\n  \"npm\" i\n  echo 'unterminated\nfi", node},
	})
}

func TestFixedCommandStartFindsTheCommandAfterReservedWords(t *testing.T) {
	// fixed-command-start: after do, then, {, !, if ..., after exec, and after
	// coproc's NAME, the old guard took that word as the command's name.
	node := commandguard.RuleNodePackages
	checkFixCases(t, []fixCase{
		{"for d in a; do npm i; done", node},
		{"{ npm i; }", node},
		{"if true; then npm i; fi", node},
		{"! npm i", node},
		{"function f { npm i; }; f", node},
		{"exec npm i", node},
		{"coproc worker { npm i; }; wait", node},
		{"coproc npm i; wait", node},
		{"while false; do echo; done", ""},
	})
}

func TestFixedShellStringReadsWhatAShellRuns(t *testing.T) {
	// fixed-shell-string: the string a shell runs with -c, and the words of
	// eval, were never read as commands.
	node := commandguard.RuleNodePackages
	checkFixCases(t, []fixCase{
		{`bash -c "npm i"`, node},
		{"sh -ec 'npm i'", node},
		{"bash -lc 'npm i'", node},
		{`bash -o pipefail -c "npm i"`, node},
		{"bash -c -- 'npm i'", node},
		{"zsh -oSH_WORD_SPLIT -c 'npm i'", node},
		{`eval "npm i"`, node},
		{`eval -- "npm i"`, node},
		{"bash ./script.sh 'npm i'", ""},
		{"bash -c 'echo npm i'", ""},
	})
}
