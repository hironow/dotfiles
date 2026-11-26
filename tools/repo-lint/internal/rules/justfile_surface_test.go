package rules

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"slices"
	"strings"
	"testing"

	json "github.com/goccy/go-json"
)

// surfaceJustfile groups every public recipe once and uses every group.
func surfaceJustfile() string {
	var text strings.Builder
	text.WriteString("set default-list\n\n# List the recipes.\n[group('meta')]\nhelp:\n    @just --list\n")
	for _, g := range justGroups {
		if g == "meta" {
			continue
		}
		fmt.Fprintf(&text, "\n# A %[1]s recipe.\n[group('%[1]s')]\n%[1]s-thing:\n    echo %[1]s\n", g)
	}
	return text.String() + `
# Under a block
# of explanation.
[group('setup')]
[doc('Install the thing.')]
install-thing *args:
    echo install

[private]
helper:
    echo helper

_hidden:
    echo hidden
`
}

const surfaceTemplate = `set default-list

# List the recipes.
[group('meta')]
help:
    @just --list

# Run the checks.
[group('gate')]
check:
    echo check
`

func TestJustfileListSurface(t *testing.T) {
	base := func() Inputs {
		return Inputs{justfilePath: surfaceJustfile(), templateJustfile: surfaceTemplate}
	}
	j, tpl := justfilePath, templateJustfile
	runCases(t, justfileListSurface(), base, []ruleCase{
		{"a recipe without a group", edit(j, "[group('dns')]\ndns-thing:", "dns-thing:"), "dns-thing"},
		{"a recipe in two groups", edit(j, "[group('dns')]\ndns-thing:", "[group('dns')]\n[group('site')]\ndns-thing:"), "dns-thing"},
		{"a recipe in an unknown group", edit(j, "[group('dns')]\ndns-thing:", "[group('net')]\ndns-thing:"), "net"},
		{"a group holds no recipe", edit(j, "[group('dns')]\ndns-thing:", "[group('site')]\ndns-thing:"), "dns"},
		{"a recipe without a doc", edit(j, "# A cloud recipe.\n", ""), "cloud-thing"},
		{"a shebang is not a doc", edit(j, "# A cloud recipe.\n", "#!/usr/bin/env bash\n"), "cloud-thing"},
		{"a template recipe without a doc", edit(tpl, "# Run the checks.\n", ""), "check"},
		{"a template recipe without a group", edit(tpl, "[group('gate')]\ncheck:", "check:"), "check"},
		{"no default-list", edit(j, "set default-list\n", ""), "set default-list"},
		{"the template lists nothing by default", edit(tpl, "set default-list\n", ""), "set default-list"},
		{"a default recipe", edit(j, "help:\n", "default:\n    @just --list\n\nhelp:\n"), "default:"},
		{"a default recipe in the template", edit(tpl, "help:\n", "default:\n    @just --list\n\nhelp:\n"), "default:"},
	})
}

const recipeSurfaceJustfile = `[group('setup')]
[windows]
add-scoop:
    scoop import x

[windows, group('runner')]
wsl-compact:
    echo compact

[macos]
[group('debug')]
start-cdp port='9222':
    open -a chrome

[group('debug')]
[macos]
debug-cdp:
    echo debug

[windows]
[group('runner')]
runner-mode-interactive: run-hidden-build
    echo interactive

[windows]
[group('runner')]
runner-mode-service:
    echo service

[group('runner')]
[windows]
runner-svc-install:
    echo install

[windows]
[group('runner')]
runner-svc-restart:
    echo restart

[group('agents')]
claude-plugins-install *args:
    echo plugins

[group('lint')]
check-pr-body file:
    echo scan
`

func TestJustfileRecipeSurface(t *testing.T) {
	base := func() Inputs { return Inputs{justfilePath: recipeSurfaceJustfile} }
	j := justfilePath
	runCases(t, justfileRecipeSurface(), base, []ruleCase{
		{"add-scoop runs everywhere", edit(j, "[group('setup')]\n[windows]\nadd-scoop:", "[group('setup')]\nadd-scoop:"), "add-scoop"},
		{"wsl-compact runs everywhere", edit(j, "[windows, group('runner')]\nwsl-compact:", "[group('runner')]\nwsl-compact:"), "wsl-compact"},
		{"start-cdp runs everywhere", edit(j, "[macos]\n[group('debug')]\nstart-cdp", "[group('debug')]\nstart-cdp"), "start-cdp"},
		{"debug-cdp is gone", edit(j, "debug-cdp:\n", "cdp-debug:\n"), "debug-cdp"},
		{"a runner mode leaves Windows", edit(j, "[windows]\n[group('runner')]\nrunner-mode-service:", "[group('runner')]\nrunner-mode-service:"), "runner-mode-service"},
		{"a runner mode leaves its group", edit(j, "[windows]\n[group('runner')]\nrunner-mode-interactive:", "[windows]\n[group('setup')]\nrunner-mode-interactive:"), "runner-mode-interactive"},
		{"a service recipe leaves Windows", edit(j, "[group('runner')]\n[windows]\nrunner-svc-install:", "[group('runner')]\nrunner-svc-install:"), "runner-svc-install"},
		{"a service recipe has no attributes", edit(j, "[windows]\n[group('runner')]\nrunner-svc-restart:", "runner-svc-restart:"), "runner-svc-restart"},
		{"the PR-body scan is gone", edit(j, "check-pr-body file:", "scan-pr-body file:"), "check-pr-body"},
		{"the plugin install takes no arguments", edit(j, "claude-plugins-install *args:", "claude-plugins-install:"), "claude-plugins-install"},
	})
}

// The parser sees every recipe just sees in the real justfile, so no recipe
// escapes the surface rules by a header the parser skips.
func TestTheParserSeesEveryRecipeJustSees(t *testing.T) {
	just, err := exec.LookPath("just")
	if err != nil {
		t.Skip("needs just")
	}
	path := filepath.Join("..", "..", "..", "..", justfilePath)
	out, err := exec.Command(just, "--justfile", path, "--dump", "--dump-format", "json").Output()
	if err != nil {
		t.Fatalf("just --dump: %v", err)
	}
	var dumped struct {
		Recipes map[string]json.RawMessage `json:"recipes"`
	}
	if err := json.Unmarshal(out, &dumped); err != nil {
		t.Fatal(err)
	}
	text, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var parsed []string
	for _, r := range parseRecipes(string(text)) {
		parsed = append(parsed, r.name)
	}
	if len(dumped.Recipes) == 0 {
		t.Fatal("just dumped no recipe")
	}
	for name := range dumped.Recipes {
		if !slices.Contains(parsed, name) {
			t.Errorf("just sees recipe %s; the parser does not", name)
		}
	}
}
