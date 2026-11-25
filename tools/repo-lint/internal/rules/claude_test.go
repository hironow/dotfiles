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

func TestClaudeLintAcceptsTheValidateCommandAsTheShellRunsIt(t *testing.T) {
	for _, run := range []string{
		"bunx  @anthropic-ai/claude-code@2.1.226\tplugin validate  --strict .\n",
		"for m in plugins/*/.claude-plugin/plugin.json; do\n  bunx @anthropic-ai/claude-code@2.1.226 plugin validate --strict \"$m\"\ndone\n",
	} {
		in := Inputs{claudeLintWorkflow: claudeLintSteps(run)}
		if got := findingsOf(t, claudeLintRunsOfficialValidate(), in); len(got) != 0 {
			t.Errorf("%q: %v", run, got)
		}
	}
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
		{"only echoed", replace("echo 'bunx @anthropic-ai/claude-code@2.1.226 plugin validate --strict .'\n"), "plugin validate"},
		{"only in a comment", replace("# bunx @anthropic-ai/claude-code@2.1.226 plugin validate --strict .\ntrue\n"), "plugin validate"},
		{"validate only in a step name", func(in Inputs) {
			in[claudeLintWorkflow] = map[string]any{"jobs": map[string]any{"validate": map[string]any{"steps": []any{
				map[string]any{"name": "bunx @anthropic-ai/claude-code@2.1.226 plugin validate --strict", "run": "true\n"},
			}}}}
		}, "plugin validate"},
	})
}
