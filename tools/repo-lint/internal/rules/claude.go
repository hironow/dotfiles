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

// commandLines is each line of a shell script that the shell reads as the
// start of a command. A backslash and a newline join two lines; a line that
// starts inside a quoted string is text, not a command; a # comment ends at
// the end of its line. Heredocs and other shell syntax are not read.
func commandLines(script string) []string {
	script = strings.ReplaceAll(script, "\\\n", "")
	var lines []string
	var quote, prev rune
	lineStart, startsQuoted, escaped, comment := 0, false, false, false
	for i, c := range script {
		if c == '\n' {
			if !startsQuoted {
				lines = append(lines, script[lineStart:i])
			}
			lineStart, startsQuoted, escaped, comment, prev = i+1, quote != 0, false, false, c
			continue
		}
		switch {
		case comment:
		case escaped:
			escaped = false
		case c == '\\' && quote != '\'':
			escaped = true
		case quote != 0:
			if c == quote {
				quote = 0
			}
		case c == '\'' || c == '"':
			quote = c
		case c == '#' && (i == lineStart || unicode.IsSpace(prev)):
			comment = true
		}
		prev = c
	}
	if !startsQuoted && lineStart < len(script) {
		lines = append(lines, script[lineStart:])
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
