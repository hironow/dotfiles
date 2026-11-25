package rules

import "testing"

func sharedSettings() map[string]any {
	return map[string]any{
		"env": map[string]any{
			"RTK_TELEMETRY_DISABLED":  "1",
			"HEADROOM_BEACON":         "off",
			"DO_NOT_TRACK":            "1",
			"VERCEL_PLUGIN_TELEMETRY": "off",
		},
		"settings": map[string]any{"skillOverrides": map[string]any{}},
	}
}

// settingsInputs is the Claude settings, as the shell decodes them, that every
// settings rule accepts.
func settingsInputs() Inputs {
	in := Inputs{
		claudeShared: sharedSettings(),
		settingsShared: map[string]any{
			claudeShared:                         sharedSettings(),
			".claude/settings.shared.macos.json": map[string]any{"env": map[string]any{"A": "1"}},
		},
		settingsProfiles: map[string]any{
			".claude/settings.profiles/claude.json": map[string]any{"settings": map[string]any{"model": "opus"}},
		},
		pluginsDecl: pluginDeclaration(),
		skillLock:   skillLockFile("ui-sdk", "provable-glossary"),
		claudeProject: map[string]any{
			"claudeMdExcludes": []any{"**/payments/**", "**/protocols/**"},
		},
		gitmodules: "[submodule \"payments/UCP\"]\n\tpath = payments/UCP\n\turl = https://example.invalid/ucp.git\n" +
			"[submodule \"protocols/A2A\"]\n\tpath = protocols/A2A\n\turl = https://example.invalid/a2a.git\n",
	}
	for _, glob := range instructionGlobs {
		in[glob] = map[string]any{}
	}
	in[instructionGlobs[0]] = map[string]any{"CLAUDE.md": "@AGENTS.md\n"}
	in[instructionGlobs[2]] = map[string]any{"AGENTS.md": "x\n", "emulator/AGENTS.md": "x\n"}
	return in
}

func TestClaudeSessionsKeepTheTelemetryOff(t *testing.T) {
	env := func(in Inputs) map[string]any { e, _ := table(in[claudeShared], "env"); return e }
	runCases(t, claudeTelemetryOff(), settingsInputs, []ruleCase{
		{"rtk telemetry on", func(in Inputs) { delete(env(in), "RTK_TELEMETRY_DISABLED") }, "RTK_TELEMETRY_DISABLED"},
		{"headroom beacon on", func(in Inputs) { env(in)["HEADROOM_BEACON"] = "on" }, "HEADROOM_BEACON"},
		{"do not track dropped", func(in Inputs) { delete(env(in), "DO_NOT_TRACK") }, "DO_NOT_TRACK"},
		{"vercel plugin telemetry on", func(in Inputs) { delete(env(in), "VERCEL_PLUGIN_TELEMETRY") }, "VERCEL_PLUGIN_TELEMETRY"},
		{"the vercel plugin no longer declared", func(in Inputs) {
			in[pluginsDecl].(map[string]any)["plugins"] = []any{"codex@openai-codex"}
		}, "vercel@claude-plugins-official"},
	})
}

func TestClaudeMdExcludesHideOnlyThirdPartyInstructions(t *testing.T) {
	runCases(t, claudeMdExcludes(), settingsInputs, []ruleCase{
		{"a submodule not excluded", func(in Inputs) {
			in[gitmodules] = in[gitmodules].(string) + "[submodule \"vendor/x\"]\n\tpath = vendor/x\n"
		}, "vendor/x"},
		{"no submodule", func(in Inputs) { in[gitmodules] = "" }, "no submodule"},
		{"no excludes", func(in Inputs) { delete(in[claudeProject].(map[string]any), "claudeMdExcludes") }, "payments/UCP"},
		{"a tracked instruction file hidden", func(in Inputs) {
			in[claudeProject] = map[string]any{"claudeMdExcludes": []any{"**/payments/**", "**/protocols/**", "**/emulator/**"}}
		}, "emulator/AGENTS.md"},
		{"the repository's own CLAUDE.md gone", func(in Inputs) { in[instructionGlobs[0]] = map[string]any{} }, "CLAUDE.md"},
		{"a rule file hidden", func(in Inputs) {
			in[instructionGlobs[4]].(map[string]any)["protocols/.claude/rules/x.md"] = "x\n"
		}, "protocols/.claude/rules/x.md"},
	})
}

func TestClaudeMdGlobMatchesAsClaudeDoes(t *testing.T) {
	for _, c := range []struct {
		pattern, path string
		want          bool
	}{
		{"**/payments/**", "/checkout/dotfiles/payments/UCP/CLAUDE.md", true},
		{"**/payments/**", "/checkout/dotfiles/paymentsx/CLAUDE.md", false},
		{"**/tools/tmux/plugins/**", "/checkout/dotfiles/tools/tmux/plugins/tpm/CLAUDE.md", true},
		{"/checkout/*/CLAUDE.md", "/checkout/dotfiles/CLAUDE.md", true},
		{"/checkout/*/CLAUDE.md", "/checkout/dotfiles/x/CLAUDE.md", false},
		{"**/a.b/**", "/checkout/dotfiles/aXb/CLAUDE.md", false},
	} {
		if got := claudeGlob(c.pattern).MatchString(c.path); got != c.want {
			t.Errorf("%q on %q = %v, want %v", c.pattern, c.path, got, c.want)
		}
	}
}

func TestSettingsFragmentsLeaveThePluginKeysToTheCLI(t *testing.T) {
	runCases(t, settingsLeavePluginKeys(), settingsInputs, []ruleCase{
		{"enabledPlugins at the top", func(in Inputs) {
			in[settingsShared].(map[string]any)[".claude/settings.shared.macos.json"] = map[string]any{"enabledPlugins": map[string]any{}}
		}, "enabledPlugins"},
		{"marketplaces in a profile's settings", func(in Inputs) {
			in[settingsProfiles].(map[string]any)[".claude/settings.profiles/claude.json"] = map[string]any{
				"settings": map[string]any{"extraKnownMarketplaces": map[string]any{}},
			}
		}, "extraKnownMarketplaces"},
	})
}

func TestSkillOverridesStayClearedAndDeclared(t *testing.T) {
	shared := func(in Inputs) map[string]any {
		return in[settingsShared].(map[string]any)[claudeShared].(map[string]any)
	}
	runCases(t, skillOverrides(), settingsInputs, []ruleCase{
		{"the shared layer drops its empty map", func(in Inputs) { delete(shared(in)["settings"].(map[string]any), "skillOverrides") }, "skillOverrides"},
		{"the shared layer turns a skill off", func(in Inputs) {
			set(shared(in), map[string]any{"ui-sdk": "off"}, "settings", "skillOverrides")
		}, "skillOverrides"},
		{"a profile adds an override", func(in Inputs) {
			in[settingsProfiles].(map[string]any)[".claude/settings.profiles/claude.json"] = map[string]any{
				"settings": map[string]any{"skillOverrides": map[string]any{"plugin:x": "off"}},
			}
		}, "settings.profiles/claude.json"},
		{"an override names an undeclared skill", func(in Inputs) {
			set(shared(in), map[string]any{"no-such-skill": "off"}, "settings", "skillOverrides")
		}, "no-such-skill"},
	})
}
