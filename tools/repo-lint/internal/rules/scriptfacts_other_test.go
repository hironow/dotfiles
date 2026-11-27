package rules

import "testing"

func TestEmulatorHealthContextFacts(t *testing.T) {
	runCases(t, emulatorHealthContextFacts(), func() Inputs {
		return Inputs{healthDockerIgnore: "*\n!Dockerfile\n!go.mod\n!main.go\n", healthGitIgnore: "/dist/\n"}
	}, []ruleCase{
		{"open context", edit(healthDockerIgnore, "*\n", ""), "test_health_build_context_only_allows_production_sources"},
		{"extra blank line", edit(healthDockerIgnore, "!main.go\n", "!main.go\n\n"), "test_health_build_context_only_allows_production_sources"},
		{"reordered sources", edit(healthDockerIgnore, "!go.mod\n!main.go", "!main.go\n!go.mod"), "test_health_build_context_only_allows_production_sources"},
		{"dist tracked", edit(healthGitIgnore, "/dist/", "dist"), "test_health_build_context_only_allows_production_sources"},
	})
}

func TestRetiredStackOperationalFacts(t *testing.T) {
	var cases []ruleCase
	for _, entry := range retiredOperationalFiles {
		for _, needle := range entry.needles {
			cases = append(cases, ruleCase{entry.path + needle, func(in Inputs) { in["./"+entry.path] = "# " + needle }, "test_the_named_operational_files_no_longer_mention_it"})
		}
	}
	runCases(t, retiredStackOperationalFacts(), func() Inputs {
		in := Inputs{}
		for _, entry := range retiredOperationalFiles {
			in["./"+entry.path] = nil
		}
		return in
	}, cases)
}

func rttmFixture() Inputs {
	return Inputs{
		pyprojectPath: map[string]any{"dependency-groups": map[string]any{"lint": []any{"ruff==1", "ruff==later", "ty==2"}}},
		rttmPyproject: map[string]any{
			"dependency-groups": map[string]any{"lint": []any{"ruff==1", "ty==2"}},
			"project":           map[string]any{"dependencies": []any{"other"}},
			"tool": map[string]any{
				"uv": map[string]any{"exclude-newer": "7 days", "exclude-newer-package": map[string]any{"ruff": false, "ty": false}},
				"ty": map[string]any{"src": map[string]any{"include": []any{"to_eaf.py", "visualize.py", "tests"}}, "environment": map[string]any{"extra-paths": []any{"."}}, "terminal": map[string]any{"error-on-warning": true}},
			},
		},
	}
}

func TestRTTMToolingFacts(t *testing.T) {
	runCases(t, rttmToolingFacts(), rttmFixture, []ruleCase{
		{"root include before a pin", func(in Inputs) {
			groups, _ := table(in[pyprojectPath], "dependency-groups")
			groups["lint"] = []any{"ruff==1", map[string]any{"include-group": "dev"}, "ty==2"}
		}, "test_rttm_lint_pin_and_cooldown_match_root: ty"},
		{"missing pin with a group include", func(in Inputs) {
			groups, _ := table(in[rttmPyproject], "dependency-groups")
			groups["lint"] = []any{map[string]any{"include-group": "dev"}, "ruff==later", "ty==2"}
		}, "test_rttm_lint_pin_and_cooldown_match_root: ruff"},
		{"missing dependency list", func(in Inputs) {
			project, _ := table(in[rttmPyproject], "project")
			delete(project, "dependencies")
		}, "test_rttm_lint_pin_and_cooldown_match_root"},
		{"second pin only", func(in Inputs) {
			in[rttmPyproject].(map[string]any)["dependency-groups"] = map[string]any{"lint": []any{"ruff==later", "ty==2"}}
		}, "test_rttm_lint_pin_and_cooldown_match_root"},
		{"broad dependency prefix", func(in Inputs) {
			in[rttmPyproject].(map[string]any)["project"] = map[string]any{"dependencies": []any{"ruff-extra"}}
		}, "test_rttm_lint_pin_and_cooldown_match_root"},
		{"cooldown", func(in Inputs) { uv, _ := table(in[rttmPyproject], "tool", "uv"); uv["exclude-newer"] = "6 days" }, "test_rttm_lint_pin_and_cooldown_match_root"},
		{"false string", func(in Inputs) {
			exemptions, _ := table(in[rttmPyproject], "tool", "uv", "exclude-newer-package")
			exemptions["ty"] = "false"
		}, "test_rttm_lint_pin_and_cooldown_match_root"},
		{"include order", func(in Inputs) {
			src, _ := table(in[rttmPyproject], "tool", "ty", "src")
			src["include"] = []any{"tests", "to_eaf.py", "visualize.py"}
		}, "test_rttm_ty_has_its_own_scope_and_import_path"},
		{"import path", func(in Inputs) {
			env, _ := table(in[rttmPyproject], "tool", "ty", "environment")
			env["extra-paths"] = []any{".."}
		}, "test_rttm_ty_has_its_own_scope_and_import_path"},
		{"true number", func(in Inputs) {
			terminal, _ := table(in[rttmPyproject], "tool", "ty", "terminal")
			terminal["error-on-warning"] = float64(1)
		}, "test_rttm_ty_has_its_own_scope_and_import_path"},
	})
}

func TestRTTMToolingAllowsEmptyDependencyList(t *testing.T) {
	in := rttmFixture()
	project, _ := table(in[rttmPyproject], "project")
	project["dependencies"] = []any{}
	if got := rttmToolingFacts().Check(in); len(got) != 0 {
		t.Fatalf("empty dependency list: %v", got)
	}
}

func TestRTTMToolingMixedLintGroups(t *testing.T) {
	for _, path := range []string{pyprojectPath, rttmPyproject} {
		t.Run(path, func(t *testing.T) {
			in := rttmFixture()
			groups, _ := table(in[path], "dependency-groups")
			groups["lint"] = []any{"ruff==1", "ty==2", map[string]any{"include-group": "dev"}}
			if got := rttmToolingFacts().Check(in); len(got) != 0 {
				t.Fatalf("pins before a group include must pass: %v", got)
			}
		})
	}
	t.Run("RTTM include before pins", func(t *testing.T) {
		in := rttmFixture()
		groups, _ := table(in[rttmPyproject], "dependency-groups")
		groups["lint"] = []any{map[string]any{"include-group": "dev"}, "ruff==1", "ty==2"}
		if got := rttmToolingFacts().Check(in); len(got) != 0 {
			t.Fatalf("membership must allow a group include before pins: %v", got)
		}
	})
}
