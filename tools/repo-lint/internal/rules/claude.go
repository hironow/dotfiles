package rules

import (
	"maps"
	"regexp"
	"slices"
	"strings"
	"unicode"
)

const claudeLintWorkflow = ".github/workflows/claude-lint.yaml"

var (
	// pinnedValidate is a command line that runs the official validator from a
	// version-pinned bunx run, with any spaces or tabs between its words.
	pinnedValidate = regexp.MustCompile(`^[ \t]*bunx[ \t]+@anthropic-ai/claude-code@\d+\.\d+\.\d+[ \t]+plugin[ \t]+validate[ \t]+--strict\b`)
	// constantFalse is an `if:` condition that never holds.
	constantFalse = regexp.MustCompile(`^\s*(?:\$\{\{\s*false\s*\}\}|false)\s*$`)
)

// commandLines is each logical line of a shell script that the shell reads as
// the start of a command. Outside single quotes and comments, a backslash and
// a newline join two lines, and a backslash makes the next character part of
// the word. A line that starts inside a quoted string is text, not a command.
// A # starts a comment only at the start of a word, and the comment ends at
// the newline, even after a backslash. Heredocs and other syntax are not read.
func commandLines(script string) []string {
	var lines []string
	var line strings.Builder
	var quote rune
	startsQuoted, escaped, comment, wordStart := false, false, false, true
	for _, c := range script {
		switch {
		case escaped:
			escaped, wordStart = false, false
			if c != '\n' {
				line.WriteRune('\\')
				line.WriteRune(c)
			}
			continue
		case c == '\n':
			if !startsQuoted {
				lines = append(lines, line.String())
			}
			line.Reset()
			startsQuoted, comment, wordStart = quote != 0, false, true
			continue
		case comment:
		case c == '\\' && quote != '\'':
			escaped = true
			continue
		case quote != 0:
			if c == quote {
				quote = 0
			}
		case c == '\'' || c == '"':
			quote = c
		case c == '#' && wordStart:
			comment = true
		}
		line.WriteRune(c)
		wordStart = quote == 0 && !comment && unicode.IsSpace(c)
	}
	if !startsQuoted && line.Len() > 0 {
		lines = append(lines, line.String())
	}
	return lines
}

// turnedOff reports whether a job's or a step's `if:` is the constant false.
func turnedOff(v any) bool {
	cond, ok := at(v, "if")
	if !ok {
		return false
	}
	if b, isBool := cond.(bool); isBool {
		return !b
	}
	s, _ := cond.(string)
	return constantFalse.MatchString(s)
}

// claudeLintRunsOfficialValidate: before ADR-0041 the official half of the
// Claude config lint never ran in CI; only the retired third-party claudelint
// did (the Semgrep rule workflow-no-third-party-claudelint keeps it out). The
// workflow runs the official validator, pinned, so the result is the same on
// every run and nothing is installed globally on the runner.
func claudeLintRunsOfficialValidate() Rule {
	const id = "claude-lint-runs-pinned-official-validate"
	return Rule{
		ID:     id,
		Why:    "CI validates the Claude config with the official `claude plugin validate --strict`, from a version-pinned bunx run (ADR-0041)",
		Inputs: []Input{{Path: claudeLintWorkflow, Format: YAML}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: claudeLintWorkflow}
			jobs, _ := table(in[claudeLintWorkflow], "jobs")
			for _, name := range slices.Sorted(maps.Keys(jobs)) {
				if turnedOff(jobs[name]) {
					continue
				}
				for _, step := range tables(jobs[name], "steps") {
					if turnedOff(step) {
						continue
					}
					run, _ := str(step, "run")
					if slices.ContainsFunc(commandLines(run), pinnedValidate.MatchString) {
						return r.out
					}
				}
			}
			r.add("no step runs `bunx @anthropic-ai/claude-code@<x.y.z> plugin validate --strict` (a step or job with `if: false` does not count)")
			return r.out
		},
	}
}
