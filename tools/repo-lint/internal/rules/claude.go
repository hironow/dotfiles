package rules

import (
	"maps"
	"regexp"
	"slices"
)

const claudeLintWorkflow = ".github/workflows/claude-lint.yaml"

// pinnedValidate runs the official validator from a version-pinned bunx run.
var pinnedValidate = regexp.MustCompile(`\bbunx @anthropic-ai/claude-code@\d+\.\d+\.\d+ plugin validate --strict\b`)

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
				for _, step := range tables(jobs[name], "steps") {
					if run, _ := str(step, "run"); pinnedValidate.MatchString(run) {
						return r.out
					}
				}
			}
			r.add("no step runs `bunx @anthropic-ai/claude-code@<x.y.z> plugin validate --strict`")
			return r.out
		},
	}
}
