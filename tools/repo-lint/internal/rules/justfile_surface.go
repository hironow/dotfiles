package rules

import (
	"regexp"
	"slices"
	"strings"
)

// justGroups are the purposes every public recipe of the root justfile is
// grouped by (AGENTS.md, "Task runner").
var justGroups = []string{
	"gate", "lint", "test", "setup", "doctor", "agents", "runner", "emulator",
	"telemetry", "tailnet", "cloud", "dns", "site", "debug", "meta",
}

// justRecipe is one recipe header, of any OS's variant, as `just --list`
// would show it: its attribute lines and its doc.
type justRecipe struct {
	name  string
	attrs []string
	doc   string
}

var (
	docAttribute   = regexp.MustCompile(`(?m)^\[doc\('([^']*)'\)\]$`)
	groupAttribute = regexp.MustCompile(`(?m)^\[group\('([^']*)'\)\]$`)
	defaultList    = regexp.MustCompile(`(?m)^set default-list$`)
	defaultRecipe  = regexp.MustCompile(`(?m)^default:`)
)

// parseRecipes is every recipe header of the justfile, every OS's variant:
// the contiguous attribute lines above it, and its doc (a [doc('...')]
// attribute, else the comment right above the attributes that is not a
// shebang).
func parseRecipes(text string) []justRecipe {
	lines := strings.Split(text, "\n")
	var out []justRecipe
	for i, line := range lines {
		if notRecipeHeader.MatchString(line) {
			continue
		}
		m := recipeName.FindStringSubmatch(line)
		if m == nil {
			continue
		}
		j := i - 1
		var attrs []string
		for j >= 0 && strings.HasPrefix(lines[j], "[") {
			attrs = append([]string{lines[j]}, attrs...)
			j--
		}
		r := justRecipe{name: m[1], attrs: attrs}
		if d := docAttribute.FindStringSubmatch(strings.Join(attrs, "\n")); d != nil {
			r.doc = d[1]
		} else if j >= 0 && strings.HasPrefix(lines[j], "#") && !strings.HasPrefix(lines[j], "#!") {
			r.doc = strings.TrimSpace(lines[j][1:])
		}
		out = append(out, r)
	}
	return out
}

// public reports whether `just --list` shows the recipe.
func (r justRecipe) public() bool {
	return !strings.HasPrefix(r.name, "_") && !slices.Contains(r.attrs, "[private]")
}

func (r justRecipe) groups() []string {
	var out []string
	for _, m := range groupAttribute.FindAllStringSubmatch(strings.Join(r.attrs, "\n"), -1) {
		out = append(out, m[1])
	}
	return out
}

// justfileListSurface: `just --list` groups every public recipe by purpose
// and shows a summary for each, and a bare `just` lists them. The rule reads
// every OS's variant, which `just --list` on one OS cannot show.
func justfileListSurface() Rule {
	const id = "justfile-list-surface"
	return Rule{
		ID:     id,
		Why:    "every public recipe is in exactly one known group and has a doc, and a bare just lists the recipes",
		Inputs: []Input{{Path: justfilePath, Format: Text}, {Path: templateJustfile, Format: Text}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: justfilePath}
			text, _ := in[justfilePath].(string)
			tpl, _ := in[templateJustfile].(string)
			used := map[string]bool{}
			for _, rec := range parseRecipes(text) {
				if !rec.public() {
					continue
				}
				groups := rec.groups()
				for _, g := range groups {
					used[g] = true
				}
				if len(groups) != 1 || !slices.Contains(justGroups, groups[0]) {
					r.add("recipe %s has groups %q; it needs exactly one of %v", rec.name, groups, justGroups)
				}
			}
			for _, g := range justGroups {
				if !used[g] {
					r.add("group %s holds no public recipe", g)
				}
			}
			for _, rec := range parseRecipes(tpl) {
				if rec.public() && len(rec.groups()) != 1 {
					r.addAt(templateJustfile, "recipe %s has groups %q; it needs exactly one", rec.name, rec.groups())
				}
			}
			for _, f := range []struct{ path, text string }{{justfilePath, text}, {templateJustfile, tpl}} {
				for _, rec := range parseRecipes(f.text) {
					if rec.public() && rec.doc == "" {
						r.addAt(f.path, "recipe %s has no doc: `just --list` shows no summary for it", rec.name)
					}
				}
				if !defaultList.MatchString(f.text) {
					r.addAt(f.path, "a bare just must list the recipes: add `set default-list`")
				}
				if defaultRecipe.MatchString(f.text) {
					r.addAt(f.path, "a default: recipe runs instead of the list; `set default-list` replaces it")
				}
			}
			return r.out
		},
	}
}

// osGated are recipes that cannot run elsewhere, so just must not offer them
// on another OS.
var osGated = []struct{ recipe, os string }{
	{"add-scoop", "windows"},
	{"wsl-compact", "windows"},
	// both hardcode /Applications
	{"start-cdp", "macos"},
	{"debug-cdp", "macos"},
}

// runnerRecipes manage the Windows runner: [windows]-gated and in group
// runner, which `just status` reports.
var runnerRecipes = []string{"runner-mode-interactive", "runner-mode-service", "runner-svc-install", "runner-svc-restart"}

// recipeAttributes is the contiguous attribute lines directly above the first
// header of the recipe, or false when it has none.
func recipeAttributes(text, name string) ([]string, bool) {
	header := regexp.MustCompile(`^` + regexp.QuoteMeta(name) + `[^:\n]*:`)
	lines := strings.Split(text, "\n")
	for i, line := range lines {
		if !header.MatchString(line) {
			continue
		}
		var attrs []string
		for j := i - 1; j >= 0; j-- {
			prev := strings.TrimSpace(lines[j])
			if !strings.HasPrefix(prev, "[") || !strings.HasSuffix(prev, "]") {
				break
			}
			attrs = append(attrs, prev)
		}
		return attrs, true
	}
	return nil, false
}

// namedRecipes are recipes something outside the justfile names: the manual
// PR-body secret scan, and the plugin install the scripts tell the operator
// to run.
var namedRecipes = []struct{ text, why string }{
	{"\ncheck-pr-body ", "the PR-body secret scan stays callable"},
	{"claude-plugins-install *args:", "scripts/claude_plugins.py and scripts/deploy.sh tell the operator to run it"},
}

// justfileRecipeSurface: OS-only recipes are gated to their OS, the runner
// recipes are Windows-only in group runner, and the recipes other files name
// exist.
func justfileRecipeSurface() Rule {
	const id = "justfile-recipe-surface"
	return Rule{
		ID:     id,
		Why:    "an OS-only recipe is offered only on its OS, the runner recipes are [windows] in group runner, and named recipes exist",
		Inputs: []Input{{Path: justfilePath, Format: Text}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: justfilePath}
			text, _ := in[justfilePath].(string)
			for _, g := range osGated {
				attrs, ok := recipeAttributes(text, g.recipe)
				word := regexp.MustCompile(`\b` + g.os + `\b`)
				switch {
				case !ok:
					r.add("recipe %s must exist", g.recipe)
				case !slices.ContainsFunc(attrs, word.MatchString):
					r.add("recipe %s runs only on %s and must carry the [%s] attribute (found %q)", g.recipe, g.os, g.os, attrs)
				}
			}
			for _, name := range runnerRecipes {
				m := regexp.MustCompile(`(?m)((?:^\[[^\]]*\]\n)+)` + regexp.QuoteMeta(name) + `:`).FindStringSubmatch(text)
				if m == nil || !strings.Contains(m[1], "windows") || !strings.Contains(m[1], "[group('runner')]") {
					r.add("recipe %s must be [windows]-gated in [group('runner')]", name)
				}
			}
			for _, n := range namedRecipes {
				if !strings.Contains(text, n.text) {
					r.add("the justfile must keep %q: %s", strings.TrimSpace(n.text), n.why)
				}
			}
			return r.out
		},
	}
}
