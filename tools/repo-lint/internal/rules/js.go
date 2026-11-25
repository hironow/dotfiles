package rules

import (
	"fmt"
	"maps"
	"regexp"
	"slices"
	"strconv"
	"strings"

	"github.com/hironow/dotfiles/tools/repo-lint/internal/jsonc"
)

const (
	packageJSON    = "package.json"
	bunfigPath     = "bunfig.toml"
	tsconfigPath   = "tsconfig.json"
	siteCopy       = "site/copy.js"
	oxlintPath     = ".oxlintrc.json"
	piExtensions   = "config/pi/extensions/*.ts"
	piRtkExtension = "config/pi/extensions/rtk.ts"
	bunLock        = "bun.lock"
	// sevenDays is the bun install cooldown in seconds: Dependabot's bun
	// rejects "7d".
	sevenDays = 604800
)

var (
	bunCheckLine     = regexp.MustCompile(`(?:\bbun|BUN \}\}) check\b`)
	importStatement  = regexp.MustCompile(`(?ms)^import\b[^;]*?from\s+["']([^"']+)["']`)
	sentinelConstant = regexp.MustCompile(`(?m)^VENDORED_SENTINEL = ("(?:[^"\\]|\\.)*")$`)
	// ruleKey is the line that opens a rule's entry: its key.
	ruleKey = regexp.MustCompile(`^\s*"([^"]+)"\s*:`)
)

// oxlintCategories must each be error; oxlintDefaultPlugins stay listed.
var (
	oxlintCategories     = []string{"correctness", "suspicious", "pedantic", "perf", "style", "restriction", "nursery"}
	oxlintDefaultPlugins = []string{"eslint", "typescript", "unicorn", "oxc"}
	// oxlintVendored are the only files oxlint may skip: bytes from elsewhere
	// that this repository must not edit.
	oxlintVendored = []string{"site/vendor/**", "config/pi/extensions/rtk.ts"}
	// gateDevDependencies are the dev dependencies the JS gate runs: the
	// linter and its type-aware half, and the types the type check reads.
	gateDevDependencies = []string{"oxlint", "oxlint-tsgolint", "@types/bun", "@earendil-works/pi-coding-agent"}
	// typeCheckedFiles are the first-party files tsconfig.json includes.
	typeCheckedFiles = []string{"site/copy.js", "config/pi/extensions/jev-sonnet-fallback.ts", "tests/unit/*.test.ts"}
)

// recipeBody is the indented body of the recipe, or false when there is none.
func recipeBody(justfile, name string) (string, bool) {
	loc := recipeHeader(name).FindStringIndex(justfile)
	if loc == nil {
		return "", false
	}
	var body []string
	for line := range strings.SplitSeq(justfile[loc[1]:], "\n") {
		if line != "" && line[0] != ' ' && line[0] != '\t' {
			break
		}
		body = append(body, line)
	}
	return strings.Join(body, "\n"), true
}

// jsDepsPinned: the JS gate's dev dependencies are a supply-chain surface. The
// package is private with no runtime dependencies, every dev dependency is an
// exact version, the install keeps the lockfile and runs no install scripts,
// and bun waits seven days for a release (ADR-0079).
func jsDepsPinned() Rule {
	const id = "js-deps-pinned"
	return Rule{
		ID:  id,
		Why: "the JS dev dependencies are exact pins, installed from the frozen lockfile without scripts, after a 7-day cooldown (ADR-0079)",
		Inputs: []Input{
			{Path: packageJSON, Format: JSON},
			{Path: bunfigPath, Format: TOML},
			{Path: justfilePath, Format: Text},
			{Path: bunLock, Format: Text, Glob: true},
		},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: packageJSON}
			// Without a lockfile, `bun install --frozen-lockfile` still succeeds
			// and resolves every transitive version afresh.
			if locks, _ := in[bunLock].(map[string]any); len(locks) == 0 {
				r.addAt(bunLock, "bun.lock must be tracked: without it a frozen install resolves every version afresh")
			}
			pkg := in[packageJSON]
			if v, _ := at(pkg, "private"); v != true {
				r.add("package.json must be private")
			}
			if _, ok := at(pkg, "dependencies"); ok {
				r.add("package.json must have no dependencies; the gate needs dev dependencies only")
			}
			dev, _ := table(pkg, "devDependencies")
			for _, name := range gateDevDependencies {
				if _, ok := dev[name]; !ok {
					r.add("devDependencies must keep %s; the gate runs it", name)
				}
			}
			for _, name := range slices.Sorted(maps.Keys(dev)) {
				if !slices.Contains(gateDevDependencies, name) {
					r.add("devDependency %s is not one the gate runs %v; each new one is a supply-chain decision", name, gateDevDependencies)
				}
				if v, _ := dev[name].(string); !exactVersion.MatchString(v) {
					r.add("devDependency %s must be an exact x.y.z, not %q", name, v)
				}
			}
			text, _ := in[justfilePath].(string)
			_, ok := recipeBody(text, "js-install")
			if !ok {
				r.addAt(justfilePath, "the justfile has no js-install recipe")
			}
			install := strings.Join(recipeCommands(text, "js-install"), "\n")
			for _, flag := range []string{"--frozen-lockfile", "--ignore-scripts"} {
				if ok && !strings.Contains(install, flag) {
					r.addAt(justfilePath, "js-install must pass %s", flag)
				}
			}
			if age, _ := at(in[bunfigPath], "install", "minimumReleaseAge"); fmt.Sprint(age) != strconv.Itoa(sevenDays) {
				r.addAt(bunfigPath, "install.minimumReleaseAge must be %d (seven days), not %v", sevenDays, age)
			}
			if exact, _ := at(in[bunfigPath], "install", "exact"); exact != true {
				r.addAt(bunfigPath, "install.exact must be true")
			}
			return r.out
		},
	}
}

// jsTypeCheckNotWeakened: the type check stays strict and reaches the page's
// script, and `bun check` always runs the checker, never a package script.
func jsTypeCheckNotWeakened() Rule {
	const id = "js-type-check-not-weakened"
	return Rule{
		ID:  id,
		Why: "the type check is strict, reads the page script, and `bun check` can never run a package script instead",
		Inputs: []Input{
			{Path: tsconfigPath, Format: JSON},
			{Path: siteCopy, Format: Text},
			{Path: justfilePath, Format: Text},
			{Path: packageJSON, Format: JSON},
		},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: tsconfigPath}
			for _, want := range []struct {
				key   string
				value bool
			}{{"strict", true}, {"noEmit", true}, {"allowJs", true}, {"checkJs", false}} {
				if v, _ := at(in[tsconfigPath], "compilerOptions", want.key); v != want.value {
					r.add("compilerOptions.%s must be %v", want.key, want.value)
				}
			}
			if include := strs(in[tsconfigPath], "include"); !sameSet(include, typeCheckedFiles) {
				r.add("include must be exactly the first-party files %v (no vendored bytes), not %v", typeCheckedFiles, include)
			}
			// JS is checked only where a file opts in, so the vendored bundle
			// the page imports is loaded but not checked.
			if copyJS, _ := in[siteCopy].(string); !strings.HasPrefix(copyJS, "// @ts-check\n") {
				r.addAt(siteCopy, "site/copy.js must start with // @ts-check so the type check reads it")
			}
			text, _ := in[justfilePath].(string)
			if !slices.ContainsFunc(recipeCommands(text, "js-typecheck"), func(c string) bool { return bunCheckLine.MatchString(c) && strings.Contains(c, "--no-script") }) {
				r.addAt(justfilePath, "js-typecheck must run `bun check --no-script`")
			}
			for line := range strings.SplitSeq(text, "\n") {
				trimmed := strings.TrimSpace(line)
				if strings.HasPrefix(trimmed, "#") || strings.HasPrefix(trimmed, "@echo") {
					continue
				}
				if bunCheckLine.MatchString(line) && !strings.Contains(line, "--no-script") {
					r.addAt(justfilePath, "%q must pass --no-script, or a package script can shadow the type check", trimmed)
				}
			}
			if _, ok := at(in[packageJSON], "scripts", "check"); ok {
				r.addAt(packageJSON, "package.json must have no check script: `bun check` would run it")
			}
			return r.out
		},
	}
}

// oxlintStrict: no oxlint check is weakened. Every category is error, no rule
// is lowered to a warning, the default plugins stay, type-aware rules stay on,
// only vendored bytes are skipped, and a rule turned off carries a reason on
// the line above it.
func oxlintStrict() Rule {
	const id = "oxlint-strict"
	return Rule{
		ID:     id,
		Why:    "oxlint keeps every category and rule at error, its default plugins and type-aware rules, and a written reason for each opt-out",
		Inputs: []Input{{Path: oxlintPath, Format: Text}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: oxlintPath}
			text, _ := in[oxlintPath].(string)
			cfg, err := jsonc.Decode(text)
			if err != nil {
				r.add("cannot decode .oxlintrc.json: %v", err)
				return r.out
			}
			categories, _ := table(cfg, "categories")
			for _, c := range oxlintCategories {
				if categories[c] != "error" {
					r.add("category %s must be error, not %v", c, categories[c])
				}
			}
			blocks := []any{cfg}
			for _, o := range tables(cfg, "overrides") {
				blocks = append(blocks, o)
			}
			for _, b := range blocks {
				rules, _ := table(b, "rules")
				for _, name := range slices.Sorted(maps.Keys(rules)) {
					level := rules[name]
					if list, isList := level.([]any); isList && len(list) > 0 {
						level = list[0]
					}
					if level != "off" && level != "error" {
						r.add("rule %s is %v; a rule is error or off, never a warning", name, level)
					}
				}
			}
			plugins := strs(cfg, "plugins")
			for _, p := range oxlintDefaultPlugins {
				if !slices.Contains(plugins, p) {
					r.add("plugin %s must stay in the list", p)
				}
			}
			if v, _ := at(cfg, "options", "typeAware"); v != true {
				r.add("options.typeAware must be true")
			}
			if ignored := strs(cfg, "ignorePatterns"); !sameSet(ignored, oxlintVendored) {
				r.add("ignorePatterns must be exactly the vendored files %v, not %v", oxlintVendored, ignored)
			}
			off := map[string]bool{}
			for _, b := range blocks {
				rules, _ := table(b, "rules")
				for name, level := range rules {
					if list, isList := level.([]any); isList && len(list) > 0 {
						level = list[0]
					}
					if level == "off" {
						off[name] = true
					}
				}
			}
			lines := strings.Split(text, "\n")
			offKey := func(line string) bool {
				m := ruleKey.FindStringSubmatch(line)
				return m != nil && off[m[1]]
			}
			for n, line := range lines {
				if !offKey(line) {
					continue
				}
				above := n - 1
				for above >= 0 && offKey(lines[above]) {
					above-- // several rules can share one reason
				}
				reason := ""
				if above >= 0 {
					reason = strings.TrimSpace(lines[above])
				}
				if !strings.HasPrefix(reason, "// ") || len(reason) <= len("// ")+20 {
					r.add("%s is off with no reason; write one as a // comment above it", strings.TrimSpace(line))
				}
			}
			return r.out
		},
	}
}

// piExtensionsTypeOnlyImports: Pi places an extension as a symlink into this
// checkout, so a value import of Pi's packages would resolve to the dev
// dependency here instead of the running Pi (ADR-0059). A type-only import is
// erased.
func piExtensionsTypeOnlyImports() Rule {
	const id = "pi-extensions-type-only-imports"
	return Rule{
		ID:     id,
		Why:    "a Pi extension imports Pi's own packages as types only, so nothing resolves to this checkout at run time (ADR-0059)",
		Inputs: []Input{{Path: piExtensions, Format: Text, Glob: true}, {Path: justfilePath, Format: Text}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id}
			// js-build bundles the extensions and fails when the output still
			// imports @earendil-works/ at run time.
			text, _ := in[justfilePath].(string)
			if !slices.ContainsFunc(recipeCommands(text, "js-build"), func(c string) bool {
				return strings.Contains(c, "grep") && strings.Contains(c, "@earendil-works/")
			}) {
				r.addAt(justfilePath, "js-build must search its build output for @earendil-works/ and fail on a match")
			}
			files, _ := in[piExtensions].(map[string]any)
			for _, p := range slices.Sorted(maps.Keys(files)) {
				text, _ := files[p].(string)
				for _, m := range importStatement.FindAllStringSubmatch(text, -1) {
					if strings.HasPrefix(m[1], "@earendil-works/") && !strings.HasPrefix(m[0], "import type") {
						r.addAt(p, "import %s with `import type`; a value import resolves to this checkout, not the running Pi", m[1])
					}
				}
			}
			return r.out
		},
	}
}

// piRtkExtensionScoped: the vendored rtk extension runs on every Pi tool call.
// It is the managed, licensed copy, and its upstream body rewrites only Bash,
// honours the RTK_DISABLED kill switch, and fails open.
func piRtkExtensionScoped() Rule {
	const id = "pi-rtk-extension-scoped"
	return Rule{
		ID:     id,
		Why:    "the vendored rtk extension is the managed Apache-2.0 copy that rewrites only Bash, has a kill switch, and fails open",
		Inputs: []Input{{Path: piRtkExtension, Format: Text}, {Path: piInstaller, Format: Text}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: piRtkExtension}
			text, _ := in[piRtkExtension].(string)
			if !strings.HasPrefix(text, "// dotfiles-managed: rtk\n") {
				r.add("rtk.ts must start with the // dotfiles-managed: rtk header")
			}
			installer, _ := in[piInstaller].(string)
			m := sentinelConstant.FindStringSubmatch(installer)
			if m == nil {
				r.addAt(piInstaller, "VENDORED_SENTINEL must be a string constant")
				return r.out
			}
			sentinel, err := strconv.Unquote(m[1])
			if err != nil {
				r.addAt(piInstaller, "cannot read VENDORED_SENTINEL: %v", err)
				return r.out
			}
			header, body, found := strings.Cut(text, sentinel)
			if !found {
				r.add("rtk.ts has no sentinel line %q", strings.TrimSpace(sentinel))
				return r.out
			}
			if !strings.Contains(header, "Apache License 2.0") {
				r.add("the header above the sentinel must keep rtk's Apache License 2.0 notice")
			}
			for _, want := range []struct{ text, why string }{
				{`event.toolName === "bash"`, "rewrite only Bash (event.toolName)"},
				{`process.env.RTK_DISABLED === "1"`, "honour the RTK_DISABLED kill switch"},
				{"Fail open", "Fail open on an unexpected error"},
			} {
				if !strings.Contains(body, want.text) {
					r.add("the vendored body must %s", want.why)
				}
			}
			return r.out
		},
	}
}
