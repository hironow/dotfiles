package rules

import "testing"

const officialValidate = "bunx @anthropic-ai/claude-code@2.1.226 plugin validate --strict .\n"

func claudeLintSteps(runs ...string) map[string]any {
	steps := []any{map[string]any{"name": "Install bun", "run": "curl -fsSL https://bun.sh/install | bash\n"}}
	for _, run := range runs {
		steps = append(steps, map[string]any{"run": run})
	}
	return map[string]any{"jobs": map[string]any{"validate": map[string]any{"steps": steps}}}
}

func claudeInputs() Inputs {
	return Inputs{claudeLintWorkflow: claudeLintSteps(officialValidate)}
}

func TestClaudeLintRunsThePinnedOfficialValidate(t *testing.T) {
	replace := func(runs ...string) func(Inputs) {
		return func(in Inputs) { in[claudeLintWorkflow] = claudeLintSteps(runs...) }
	}
	runCases(t, claudeLintRunsOfficialValidate(), claudeInputs, []ruleCase{
		{"no validate step", replace(), "plugin validate"},
		{"an unpinned CLI", replace("bunx @anthropic-ai/claude-code plugin validate --strict .\n"), "plugin validate"},
		{"a moving tag", replace("bunx @anthropic-ai/claude-code@latest plugin validate --strict .\n"), "plugin validate"},
		{"without --strict", replace("bunx @anthropic-ai/claude-code@2.1.226 plugin validate .\n"), "plugin validate"},
		{"validate only in a step name", func(in Inputs) {
			in[claudeLintWorkflow] = map[string]any{"jobs": map[string]any{"validate": map[string]any{"steps": []any{
				map[string]any{"name": "bunx @anthropic-ai/claude-code@2.1.226 plugin validate --strict", "run": "true\n"},
			}}}}
		}, "plugin validate"},
	})
}
