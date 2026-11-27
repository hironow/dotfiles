package rules

import (
	"fmt"
	"slices"
	"strings"
)

const (
	healthDockerIgnore = "emulator/healthcheck/.dockerignore"
	healthGitIgnore    = "emulator/healthcheck/.gitignore"
	rttmPyproject      = "tools/rttm/pyproject.toml"
)

func emulatorHealthContextFacts() Rule {
	return factRule("emulator-health-context-facts", "the health build context admits only production sources", []string{healthDockerIgnore, healthGitIgnore}, []scriptFact{
		fact("test_health_build_context_only_allows_production_sources",
			exactLines(healthDockerIgnore, []string{"*", "!Dockerfile", "!go.mod", "!main.go"}),
			exactLines(healthGitIgnore, []string{"/dist/"})),
	})
}

func exactLines(path string, want []string) factCheck {
	return func(files map[string]string) []string {
		if !slices.Equal(pySplitlines(files[path]), want) {
			return []string{fmt.Sprintf("%s must have exactly these lines: %q", path, want)}
		}
		return nil
	}
}

var retiredOperationalFiles = []struct {
	path    string
	needles []string
}{
	{".pre-commit-config.yaml", []string{"coder", "tofu/exe"}},
	{"pyproject.toml", []string{`"exe:`}},
	{".github/workflows/iac-test.yaml", []string{"Coder template", "tofu/exe/", "exe-platform", "exe-cluster"}},
	{"config/mise/config.toml", []string{"google/ax", "ko-build/ko"}},
	{".github/dependabot.yaml", []string{"exe-reaper"}},
	{".gitignore", []string{"exe-reaper"}},
	{"ROOT_AGENTS_hooks_block-prohibited-commands.py", []string{"cdr"}},
}

func retiredStackOperationalFacts() Rule {
	var paths []string
	var checks []factCheck
	for _, entry := range retiredOperationalFiles {
		// Keep raw text separate from the decoded input for the same file.
		path := "./" + entry.path
		paths = append(paths, path)
		checks = append(checks, lacks(path, entry.needles...))
	}
	rule := factRule("retired-stack-operational-facts", "named operational files contain no retired stack references", paths, []scriptFact{
		fact("test_the_named_operational_files_no_longer_mention_it", checks...),
	})
	for i := range rule.Inputs {
		rule.Inputs[i].Optional = true
	}
	return rule
}

func rttmToolingFacts() Rule {
	return Rule{
		ID:     "rttm-tooling-facts",
		Why:    "RTTM shares the root lint pins and cooldown, with its own type-check scope",
		Inputs: []Input{{Path: pyprojectPath, Format: TOML}, {Path: rttmPyproject, Format: TOML}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: "rttm-tooling-facts", path: rttmPyproject}
			root, rttm := in[pyprojectPath], in[rttmPyproject]
			lintValue, _ := at(rttm, "dependency-groups", "lint")
			lint, _ := lintValue.([]any)
			for _, tool := range []string{"ruff", "ty"} {
				pin := firstRTTMLintPin(root, tool)
				dependencies := strs(rttm, "project", "dependencies")
				badDependency := dependencies == nil
				for _, p := range dependencies {
					badDependency = badDependency || strings.HasPrefix(p, tool)
				}
				cooldown, _ := str(rttm, "tool", "uv", "exclude-newer")
				exempt, _ := at(rttm, "tool", "uv", "exclude-newer-package", tool)
				exemptBool, isBool := exempt.(bool)
				if pin == "" || !slices.Contains(lint, any(pin)) || badDependency || cooldown != "7 days" || !isBool || exemptBool {
					r.add("test_rttm_lint_pin_and_cooldown_match_root: %s needs the first root pin, no application dependency, and its cooldown exemption", tool)
				}
			}
			warnings, _ := at(rttm, "tool", "ty", "terminal", "error-on-warning")
			warningsBool, isBool := warnings.(bool)
			if !slices.Equal(strs(rttm, "tool", "ty", "src", "include"), []string{"to_eaf.py", "visualize.py", "tests"}) || !slices.Equal(strs(rttm, "tool", "ty", "environment", "extra-paths"), []string{"."}) || !isBool || !warningsBool {
				r.add("test_rttm_ty_has_its_own_scope_and_import_path: preserve the ordered include list, local import path, and warning failures")
			}
			return r.out
		},
	}
}

func firstRTTMLintPin(root any, tool string) string {
	value, _ := at(root, "dependency-groups", "lint")
	items, _ := value.([]any)
	for _, item := range items {
		pin, ok := item.(string)
		// Python's next stops at the first match; startswith fails on a table.
		if !ok {
			return ""
		}
		if strings.HasPrefix(pin, tool+"==") {
			return pin
		}
	}
	return ""
}
