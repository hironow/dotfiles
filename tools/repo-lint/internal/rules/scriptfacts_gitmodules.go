package rules

import (
	"fmt"
	"slices"
)

const gitmodulesPath = ".gitmodules"

func gitmodulesSkipAll() Rule {
	return factRule(
		"gitmodules-skip-all",
		"Dependabot's recursive clone must skip every submodule",
		[]string{gitmodulesPath},
		[]scriptFact{
			// tests/unit/test_dependabot_submodule_clone.py
			fact("test_every_submodule_is_skipped_by_default", submodulesSkipUpdates),
		},
	)
}

var (
	gitmodulesSection = pyCompile(`(?m)^\[submodule "([^"]+)"\]\n((?:[ \t].*\n?)*)`).re
	gitmodulesUpdate  = pyCompile(`(?m)^\s*update\s*=\s*(\S+)\s*$`).re
)

func submodulesSkipUpdates(files map[string]string) []string {
	// dict(re.findall(...)): the last section with a name wins.
	sections := map[string]string{}
	for _, match := range gitmodulesSection.FindAllStringSubmatch(files[gitmodulesPath], -1) {
		sections[match[1]] = match[2]
	}
	if len(sections) == 0 {
		return []string{".gitmodules lists no submodule"}
	}
	var out []string
	for name, body := range sections {
		// re.search takes the first matching update, even with duplicates.
		value := gitmodulesUpdate.FindStringSubmatch(body)
		if value == nil || value[1] != "none" {
			out = append(out, fmt.Sprintf("submodule %q must set update = none", name))
		}
	}
	slices.Sort(out)
	return out
}
