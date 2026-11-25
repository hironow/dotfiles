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
		"bunx @anthropic-ai/claude-code@2.1.226 \\\n  plugin validate --strict .\n",
		"echo 'checking'\nbunx @anthropic-ai/claude-code@2.1.226 plugin validate --strict . # the official one\n",
		"echo \"it's the official one\"\nbunx @anthropic-ai/claude-code@2.1.226 plugin validate --strict .\n",
		"true # it's the official one\nbunx @anthropic-ai/claude-code@2.1.226 plugin validate --strict .\n",
		"echo a\\#'b'\nbunx @anthropic-ai/claude-code@2.1.226 plugin validate --strict .\n",
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
		{"only in a multi-line echo", replace("echo '\nbunx @anthropic-ai/claude-code@2.1.226 plugin validate --strict .\n'\n"), "plugin validate"},
		{"only in a multi-line double-quoted string", replace("msg=\"\n  bunx @anthropic-ai/claude-code@2.1.226 plugin validate --strict .\n\"\necho \"$msg\"\n"), "plugin validate"},
		{"a comment ending in a backslash, then a multi-line echo", replace("# note \\\necho '\nbunx @anthropic-ai/claude-code@2.1.226 plugin validate --strict .\n'\n"), "plugin validate"},
		{"an escaped space before #, then a multi-line quote", replace("echo \\ #'\nbunx @anthropic-ai/claude-code@2.1.226 plugin validate --strict .\n'\n"), "plugin validate"},
		{"the step turned off", func(in Inputs) {
			steps := in[claudeLintWorkflow].(map[string]any)["jobs"].(map[string]any)["validate"].(map[string]any)["steps"].([]any)
			steps[len(steps)-1].(map[string]any)["if"] = "${{ false }}"
		}, "plugin validate"},
		{"the job turned off", func(in Inputs) {
			in[claudeLintWorkflow].(map[string]any)["jobs"].(map[string]any)["validate"].(map[string]any)["if"] = "false"
		}, "plugin validate"},
		{"validate only in a step name", func(in Inputs) {
			in[claudeLintWorkflow] = map[string]any{"jobs": map[string]any{"validate": map[string]any{"steps": []any{
				map[string]any{"name": "bunx @anthropic-ai/claude-code@2.1.226 plugin validate --strict", "run": "true\n"},
			}}}}
		}, "plugin validate"},
	})
}
