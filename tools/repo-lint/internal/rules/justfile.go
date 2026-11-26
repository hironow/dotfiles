package rules

import (
	"maps"
	"regexp"
	"slices"
	"strings"
)

const (
	templateJustfile = "templates/agent-baseline/justfile"
	// spokeGlob is the spokes, whose ```just blocks other repositories copy.
	spokeGlob = "ROOT_AGENTS_docs_agents_*.md"
)

// gateLeg is one fact a gate keeps. Each was a test that read the justfile
// (ADR-0093), and each searches what its test searched, comments included.
type gateLeg struct {
	recipe string
	// header: the header line, after the name, matches.
	header *regexp.Regexp
	// has: the body holds it.
	has string
	// blockHas: the header line, after the name, or the body holds it.
	blockHas string
	// blockHasNot: neither the header line, after the name, nor the body
	// holds it.
	blockHasNot string
	// noCode: no body line that is not a comment and holds no echo holds it.
	noCode string
}

// bareGates take no dependency on their header line: the tests found each
// as a line of its own name.
var bareGates = []string{"check", "check-except-go", "fmt", "lint"}

var runsHiddenBuild = regexp.MustCompile(`\brun-hidden-build\b`)

// gateLegs are the legs the gates must keep.
var gateLegs = []gateLeg{
	// each installer copies run-hidden.exe, so it builds it first
	{recipe: "runner-watchdog-install", header: runsHiddenBuild},
	{recipe: "runner-mode-interactive", header: runsHiddenBuild},
	{recipe: "runner-gc-install", header: runsHiddenBuild},
	// `check` runs the cheap legs through check-except-go (ADR-0089)
	{recipe: "check", has: "@just check-except-go"},
	// the local gates run the JS legs CI runs (ADR-0079)
	{recipe: "lint", has: "just js-lint"},
	{recipe: "lint", has: "just js-typecheck"},
	{recipe: "lint", has: "just pi-jev-test"},
	{recipe: "check-except-go", has: "just js-lint"},
	{recipe: "check-except-go", has: "just js-typecheck"},
	{recipe: "check-except-go", has: "just pi-jev-test"},
	{recipe: "check-except-go", has: "vp -C site fmt --check"},
	// text hygiene is a read-only leg of the full check (ADR-0085)
	{recipe: "check-except-go", has: "@mise exec -- go run tools/text-hygiene/main.go"},
	{recipe: "check-except-go", noCode: "--fix"},
	// RTTM is reached by the root gates
	{recipe: "fmt", has: "just rttm-fmt"},
	{recipe: "lint", has: "just rttm-lint"},
	{recipe: "check-except-go", has: "just rttm-check"},
	{recipe: "rttm-fmt"},
	{recipe: "rttm-lint"},
	{recipe: "rttm-typecheck", blockHas: "--group lint ty check"},
	{recipe: "rttm-typecheck", blockHasNot: "--only-group lint ty"},
	{recipe: "rttm-check", blockHas: "rttm-typecheck"},
	{recipe: "rttm-check", blockHas: "--group lint python -m pytest"},
}

var (
	// checkRunsGoLint: `check` runs the Go lint leg.
	checkRunsGoLint = regexp.MustCompile(`\bgo-lint\b|golangci-lint\s+run`)
	// goTools: the Go recipes run golangci-lint, somewhere in the file.
	goTools = []struct {
		recipe, call string
		pattern      *regexp.Regexp
	}{
		{"go-lint", "golangci-lint run", regexp.MustCompile(`golangci-lint\s+run`)},
		{"go-fmt", "golangci-lint fmt", regexp.MustCompile(`golangci-lint\s+fmt`)},
	}
)

// vpNever: vp only formats; oxlint lints and bun check type checks (ADR-0079).
var vpNever = []string{"vp -C site lint", "vp -C site check"}

// recipeBlock is the recipe's header line after the name, and its body.
func recipeBlock(justfile, name string) (string, string, bool) {
	m := recipeHeader(name).FindStringSubmatch(justfile)
	if m == nil {
		return "", "", false
	}
	body, _ := recipeBody(justfile, name)
	return m[1], body, true
}

// codeLines is the file's lines, trimmed, with blank lines and comments left
// out.
func codeLines(text string) []string {
	var out []string
	for line := range strings.SplitSeq(text, "\n") {
		if line = strings.TrimSpace(line); line != "" && !strings.HasPrefix(line, "#") {
			out = append(out, line)
		}
	}
	return out
}

// justfileGateLegs: the gates keep their legs, and a leg that is gone fails
// nothing on its own, so the table holds them.
func justfileGateLegs() Rule {
	const id = "justfile-gate-legs"
	return Rule{
		ID:     id,
		Why:    "the gates keep the legs that hold the repository's checks: a dropped leg passes silently",
		Inputs: []Input{{Path: justfilePath, Format: Text}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: justfilePath}
			text, _ := in[justfilePath].(string)
			checkCIScansTheBranch(r, text)
			missing := map[string]bool{}
			for _, leg := range gateLegs {
				header, body, ok := recipeBlock(text, leg.recipe)
				if !ok {
					if !missing[leg.recipe] {
						r.add("recipe %s must exist", leg.recipe)
						missing[leg.recipe] = true
					}
					continue
				}
				checkGateLeg(r, leg, header, body)
			}
			for _, gate := range bareGates {
				if header, _, ok := recipeBlock(text, gate); ok && strings.TrimSpace(header) != "" {
					r.add("recipe %s must stand on a line of its own name, with no dependency: %q", gate, header)
				}
			}
			if _, body, ok := recipeBlock(text, "check"); ok && !checkRunsGoLint.MatchString(body) {
				r.add("recipe check must run the Go lint gate (go-lint or golangci-lint run)")
			}
			checkFileWideLegs(r, text)
			return r.out
		},
	}
}

// checkCIScansTheBranch: a gate that stops scanning the branch lets a leaked
// token through.
func checkCIScansTheBranch(r *report, text string) {
	lines := strings.Split(text, "\n")
	ci := slices.IndexFunc(lines, func(l string) bool { return strings.HasPrefix(l, "ci: check ") })
	switch {
	case ci < 0:
		r.add("recipe ci must start with `ci: check ` and depend on check-forbidden-tokens-branch")
	case !strings.Contains(lines[ci], "check-forbidden-tokens-branch"):
		r.add("recipe ci must depend on check-forbidden-tokens-branch")
	}
}

// checkGateLeg checks one row against the recipe's header line and body.
func checkGateLeg(r *report, leg gateLeg, header, body string) {
	block := header + "\n" + body
	switch {
	case leg.header != nil && !leg.header.MatchString(header):
		r.add("recipe %s must depend on %s", leg.recipe, leg.header)
	case leg.has != "" && !strings.Contains(body, leg.has):
		r.add("recipe %s must run %s", leg.recipe, leg.has)
	case leg.blockHas != "" && !strings.Contains(block, leg.blockHas):
		r.add("recipe %s must run %s", leg.recipe, leg.blockHas)
	case leg.blockHasNot != "" && strings.Contains(block, leg.blockHasNot):
		r.add("recipe %s must not hold %s", leg.recipe, leg.blockHasNot)
	case leg.noCode != "":
		for line := range strings.SplitSeq(body, "\n") {
			if !strings.HasPrefix(strings.TrimLeft(line, " \t"), "#") && !strings.Contains(line, "echo") && strings.Contains(line, leg.noCode) {
				r.add("recipe %s must not run %s: %s", leg.recipe, leg.noCode, strings.TrimSpace(line))
			}
		}
	}
}

// checkFileWideLegs: the facts their tests searched the whole file for.
func checkFileWideLegs(r *report, text string) {
	// supply-chain hardening is one recipe away
	if _, _, ok := recipeBlock(text, "harden-env"); !ok {
		r.add("recipe harden-env must exist")
	}
	if !strings.Contains(text, "scripts/harden_env.sh") {
		r.add("the harden-env recipe must invoke scripts/harden_env.sh")
	}
	code := codeLines(text)
	for _, g := range goTools {
		if _, _, ok := recipeBlock(text, g.recipe); !ok {
			r.add("recipe %s must exist", g.recipe)
		}
		if !slices.ContainsFunc(code, g.pattern.MatchString) {
			r.add("%s must invoke %s", g.recipe, g.call)
		}
	}
	for _, never := range vpNever {
		if strings.Contains(text, never) {
			r.add("no recipe may run %s; vp only formats (ADR-0079)", never)
		}
	}
}

// bashWrappers are the recipes PowerShell runs: a shebang recipe resolves
// `env bash` to WSL's bash from PowerShell, so each stays a linewise call of
// plain bash on its script.
// Each header pattern is the one its test found the recipe by: doctor may
// take parameters, the others may not.
var bashWrappers = []struct {
	recipe, command string
	header          *regexp.Regexp
}{
	{"deploy", "bash scripts/deploy.sh", regexp.MustCompile(`(?m)^deploy\s*:.*$`)},
	{"clean", "bash scripts/clean.sh", regexp.MustCompile(`(?m)^clean\s*:.*$`)},
	{"doctor", "bash scripts/doctor.sh", regexp.MustCompile(`(?m)^doctor[^:\n]*:.*$`)},
	{"prune-rogue-npm-globals", "bash scripts/rogue_npm_globals.sh prune", regexp.MustCompile(`(?m)^prune-rogue-npm-globals:.*$`)},
}

// bodyAfter is the indented body below the header the pattern finds.
func bodyAfter(justfile string, header *regexp.Regexp) (string, bool) {
	loc := header.FindStringIndex(justfile)
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

// The Windows prelude each OS setting runs: /usr/bin first on PATH, then the
// real shell, keeping errexit, nounset and pipefail for recipes.
var (
	shellPrelude      = regexp.MustCompile(`exec /usr/bin/sh .*-c "\$0"`)
	interpreterRunner = regexp.MustCompile(`exec /usr/bin/bash "\$0" "\$@"$`)
)

var quotedArg = regexp.MustCompile(`"([^"]*)"|'([^']*)'`)

// osSetting is the argv of a list setting (`shell`, `script-interpreter`)
// under the OS attribute, or false when the justfile sets none.
func osSetting(justfile, osAttr, setting string) ([]string, bool) {
	m := regexp.MustCompile(`(?m)^\[` + osAttr + `\]\nset ` + setting + ` := \[(.+)\]$`).FindStringSubmatch(justfile)
	if m == nil {
		return nil, false
	}
	var argv []string
	for _, q := range quotedArg.FindAllStringSubmatch(m[1], -1) {
		argv = append(argv, q[1]+q[2])
	}
	return argv, true
}

// shebangRecipes is the header line of each recipe whose body starts with a
// shebang.
func shebangRecipes(justfile string) []string {
	lines := strings.Split(justfile, "\n")
	var out []string
	for i := 1; i < len(lines); i++ {
		if strings.HasPrefix(lines[i], "    #!") && !strings.HasPrefix(lines[i-1], " ") {
			out = append(out, lines[i-1])
		}
	}
	return out
}

// justfileShellSafety: on Windows a shebang recipe runs WSL's bash, so no
// recipe has one; the PowerShell entry points call plain bash; and the
// template runs scripts with the same interpreters.
func justfileShellSafety() Rule {
	const id = "justfile-shell-safety"
	return Rule{
		ID:     id,
		Why:    "a shebang recipe runs WSL's bash from PowerShell; recipes stay linewise or [script], and the template uses the same interpreters",
		Inputs: []Input{{Path: justfilePath, Format: Text}, {Path: templateJustfile, Format: Text}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: justfilePath}
			text, _ := in[justfilePath].(string)
			tpl, _ := in[templateJustfile].(string)
			for _, w := range bashWrappers {
				body, ok := bodyAfter(text, w.header)
				if !ok {
					r.add("recipe %s must exist and run `%s`", w.recipe, w.command)
					continue
				}
				if strings.Contains(body, "#!") {
					r.add("recipe %s must not carry a shebang: from PowerShell it runs WSL's bash", w.recipe)
				}
				if !strings.Contains(body, w.command) {
					r.add("recipe %s must run `%s` linewise", w.recipe, w.command)
				}
			}
			for _, f := range []struct{ path, text string }{{justfilePath, text}, {templateJustfile, tpl}} {
				for _, header := range shebangRecipes(f.text) {
					r.addAt(f.path, "recipe %q runs through a shebang line; use [script] or a linewise body", header)
				}
			}
			// On Windows the entry point is `sh`, which System32 does not hold,
			// so neither runs WSL's bash; the prelude after it is run by the
			// mechanism tests.
			shell, _ := osSetting(text, "windows", "shell")
			if len(shell) < 2 || shell[0] != "sh" || shell[len(shell)-2] != "-c" {
				r.add("the [windows] shell must start with `sh` and hand the recipe to `-c`: %q", shell)
			} else {
				prelude := shell[len(shell)-1]
				if !strings.Contains(prelude, `PATH="/usr/bin:$PATH"`) || !shellPrelude.MatchString(prelude) ||
					!strings.Contains(prelude, "-eu") || !strings.Contains(prelude, "pipefail") {
					r.add("the [windows] shell must put /usr/bin first and exec /usr/bin/sh with -eu and pipefail on \"$0\": %q", prelude)
				}
			}
			interp, _ := osSetting(text, "windows", "script-interpreter")
			if len(interp) < 3 || interp[0] != "sh" || interp[1] != "-c" {
				r.add("the [windows] script-interpreter must start with `sh -c`: %q", interp)
			} else if !strings.Contains(interp[2], `PATH="/usr/bin:$PATH"`) || !interpreterRunner.MatchString(interp[2]) {
				r.add("the [windows] script-interpreter must put /usr/bin first and exec /usr/bin/bash \"$0\" \"$@\": %q", interp[2])
			}
			// On Unix a [script] recipe runs as plain bash; the recipe sets its
			// own errexit (set -euo pipefail).
			if unix, ok := osSetting(text, "unix", "script-interpreter"); ok && !slices.Equal(unix, []string{"bash"}) {
				r.add("the [unix] script-interpreter must be exactly [\"bash\"], not %q", unix)
			}
			for _, osAttr := range []string{"unix", "windows"} {
				root, ok := osSetting(text, osAttr, "script-interpreter")
				if !ok {
					r.add("the justfile must set script-interpreter under [%s]", osAttr)
					continue
				}
				if got, _ := osSetting(tpl, osAttr, "script-interpreter"); !slices.Equal(got, root) {
					r.addAt(templateJustfile, "the template's [%s] script-interpreter %q must equal the justfile's %q", osAttr, got, root)
				}
			}
			return r.out
		},
	}
}

// deprecatedJust are settings and functions the pinned just deprecates.
var deprecatedJust = []struct {
	label   string
	pattern *regexp.Regexp
}{
	{"set windows-shell", regexp.MustCompile(`(?m)^\s*set\s+windows-shell\b`)},
	{"set windows-powershell", regexp.MustCompile(`(?m)^\s*set\s+windows-powershell\b`)},
	{"env_var()", regexp.MustCompile(`\benv_var\s*\(`)},
	{"env_var_or_default()", regexp.MustCompile(`\benv_var_or_default\s*\(`)},
}

var justBlock = regexp.MustCompile("(?ms)^```just\n(.*?)^```$")

// justfileNoDeprecated: neither justfile, nor a spoke's ```just block that
// other repositories copy, uses a deprecated just setting or function.
func justfileNoDeprecated() Rule {
	const id = "justfile-no-deprecated"
	return Rule{
		ID:  id,
		Why: "no justfile and no spoke's just block uses a deprecated just setting or function",
		Inputs: []Input{
			{Path: justfilePath, Format: Text},
			{Path: templateJustfile, Format: Text},
			{Path: spokeGlob, Format: Text, Glob: true},
		},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: justfilePath}
			type source struct{ path, text string }
			var sources []source
			for _, p := range []string{justfilePath, templateJustfile} {
				text, _ := in[p].(string)
				sources = append(sources, source{p, text})
			}
			spokes, _ := in[spokeGlob].(map[string]any)
			for _, p := range slices.Sorted(maps.Keys(spokes)) {
				text, _ := spokes[p].(string)
				var blocks []string
				for _, m := range justBlock.FindAllStringSubmatch(text, -1) {
					blocks = append(blocks, m[1])
				}
				sources = append(sources, source{p, strings.Join(blocks, "\n")})
			}
			for _, s := range sources {
				for _, d := range deprecatedJust {
					if d.pattern.MatchString(s.text) {
						r.addAt(s.path, "uses the deprecated %s", d.label)
					}
				}
			}
			return r.out
		},
	}
}

// notRecipeHeader is a justfile line that does not start a recipe: a comment,
// an attribute, a setting, an alias, an export, an import, a module, a body
// line, a closing brace, a blank line, or a variable or function definition.
var notRecipeHeader = regexp.MustCompile(`^(#|\[|set |alias |export |import |mod |\s|\}|$)` +
	`|^[A-Za-z_][\w-]*\s*:=` +
	`|^[A-Za-z_][\w-]*\([^)]*\)\s*:=`)

var recipeName = regexp.MustCompile(`^@?([A-Za-z_][\w-]*)`)

// justfileRecipeDoc: `just --list` shows only the comment line right above a
// recipe. Under a block of explanation that line is a fragment, so such a
// recipe gives its summary with [doc('...')].
func justfileRecipeDoc() Rule {
	const id = "justfile-recipe-doc"
	return Rule{
		ID:     id,
		Why:    "a public recipe under a block of comments gives its one-line summary with [doc('...')]",
		Inputs: []Input{{Path: justfilePath, Format: Text}, {Path: templateJustfile, Format: Text}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: justfilePath}
			for _, path := range []string{justfilePath, templateJustfile} {
				text, _ := in[path].(string)
				lines := strings.Split(text, "\n")
				for i, line := range lines {
					if notRecipeHeader.MatchString(line) {
						continue
					}
					m := recipeName.FindStringSubmatch(line)
					if m == nil || strings.HasPrefix(m[1], "_") {
						continue
					}
					j := i - 1
					var attrs []string
					for j >= 0 && strings.HasPrefix(lines[j], "[") {
						attrs = append(attrs, lines[j])
						j--
					}
					if slices.Contains(attrs, "[private]") || slices.ContainsFunc(attrs, func(a string) bool { return strings.HasPrefix(a, "[doc(") }) {
						continue
					}
					if j >= 1 && strings.HasPrefix(lines[j], "#") && strings.HasPrefix(lines[j-1], "#") {
						r.addAt(path, "recipe %s sits under a comment block; give its summary with [doc('...')]", m[1])
					}
				}
			}
			return r.out
		},
	}
}

// nodeTool in command position: at line start, after a separator or a
// backtick, after a command-introducing word, or after `mise x ... --` or
// `xargs`. RE2 has no lookahead, so the tool's end is a character that cannot
// continue its name (a `:` continues a mise backend such as npm:pkg).
var (
	nodeToolInCommand = regexp.MustCompile("(?:^|[;&|({`]\\s*" +
		`|\bmise\s+(?:x|exec)\s+(?:[^\s;&|]+\s+)*?--\s+` +
		`|\b(?:then|do|exec|command -v|x|sudo|env|time|nice)\s+(?:--\s+)?(?:\w+=\S+\s+)*` +
		`|\bxargs\s+(?:-\S+\s+)*)(?:npm|npx|pnpm|yarn)(?:[^\w:-]|$)`)
	// nodeToolHint tells the operator to run one, e.g. "npm i -g x".
	nodeToolHint = regexp.MustCompile(`\b(?:npm|pnpm|yarn)\s+(?:i|install|add|dlx|run|ls|exec)\b|\bnpx\s`)
)

// justfileBunOnly: Node tooling runs through bun only (two resolvers put the
// lockfile out of sync). A comment, a [doc] attribute, or a name that only
// mentions npm runs nothing and stays allowed.
func justfileBunOnly() Rule {
	const id = "justfile-bun-only"
	return Rule{
		ID:     id,
		Why:    "the justfile runs Node tooling through bun only: no npm, npx, pnpm or yarn invocation or hint",
		Inputs: []Input{{Path: justfilePath, Format: Text}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: justfilePath}
			text, _ := in[justfilePath].(string)
			for n, raw := range strings.Split(text, "\n") {
				line := strings.TrimSpace(raw)
				if line == "" || strings.HasPrefix(line, "#") || strings.HasPrefix(raw, "[doc(") {
					continue
				}
				command := strings.TrimSpace(strings.TrimLeft(line, "@-"))
				if nodeToolInCommand.MatchString(command) || nodeToolHint.MatchString(command) {
					r.add("line %d runs Node tooling outside bun: %s", n+1, line)
				}
			}
			return r.out
		},
	}
}

var vpGateLine = regexp.MustCompile(`^\s+git -C site --work-tree=\.\. ls-files -z (.+?) \| xargs -0 -r mise x -- vp -C site (fmt(?: --check)?)\s*$`)

// justfileOneJSFileList: `fmt` and the check hand vp the same JS/TS files, so
// an exclusion added to one cannot be missed in the other.
func justfileOneJSFileList() Rule {
	const id = "justfile-one-js-file-list"
	return Rule{
		ID:     id,
		Why:    "every vp gate reads the one JS_FILES list, inside site/",
		Inputs: []Input{{Path: justfilePath, Format: Text}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: justfilePath}
			text, _ := in[justfilePath].(string)
			specs := map[string]string{}
			for line := range strings.SplitSeq(text, "\n") {
				if m := vpGateLine.FindStringSubmatch(line); m != nil {
					specs[m[2]] = m[1]
				}
			}
			for _, mode := range []string{"fmt", "fmt --check"} {
				spec, ok := specs[mode]
				switch {
				case !ok:
					r.add("a recipe must run `vp -C site %s` on {{ JS_FILES }}", mode)
				case spec != "{{ JS_FILES }}":
					r.add("`vp -C site %s` reads %s; it must read {{ JS_FILES }}", mode, spec)
				}
			}
			if strings.Contains(text, " vp fmt") {
				r.add("vp fmt runs outside site/; vp runs only as `vp -C site`")
			}
			if n := strings.Count(text, " vp -C site "); n != len(specs) {
				r.add("%d lines run ` vp -C site `, %d read {{ JS_FILES }} through git ls-files; a vp line the list does not feed", n, len(specs))
			}
			return r.out
		},
	}
}

var (
	uvRun       = regexp.MustCompile(`(?m)^UV_RUN := "(.*)"$`)
	uvRunScript = regexp.MustCompile(`(?m)^UV_RUN_SCRIPT := "(.*)"$`)
)

// justfileUVRunModes: project commands run from the frozen lockfile, and PEP
// 723 scripts, which have no project lock, run the same command without
// --frozen.
func justfileUVRunModes() Rule {
	const id = "justfile-uv-run-modes"
	return Rule{
		ID:     id,
		Why:    "UV_RUN runs from the frozen lockfile; UV_RUN_SCRIPT is the same command without --frozen, for PEP 723 scripts",
		Inputs: []Input{{Path: justfilePath, Format: Text}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: justfilePath}
			text, _ := in[justfilePath].(string)
			project, script := uvRun.FindStringSubmatch(text), uvRunScript.FindStringSubmatch(text)
			switch {
			case project == nil || script == nil:
				r.add("the justfile must define both UV_RUN and UV_RUN_SCRIPT")
			case !strings.HasSuffix(project[1], " --frozen"):
				r.add("UV_RUN %q must end with --frozen: the gates run from the lockfile", project[1])
			case script[1] != strings.TrimSuffix(project[1], " --frozen"):
				r.add("UV_RUN_SCRIPT %q must be UV_RUN without --frozen, %q", script[1], strings.TrimSuffix(project[1], " --frozen"))
			}
			return r.out
		},
	}
}

// awsCLI: the http:aws build mise installs has no Windows asset, so Windows
// runs the standalone aws; elsewhere aws runs from the checkout's mise.
const (
	awsCLI     = `AWS_CLI := if os() == "windows" { "aws" } else { CLI_TOOLS_MISE + " exec http:aws -- aws" }`
	awsListRec = "[group('cloud')]\naws-list:\n    {{ AWS_CLI }} configure list-profiles\n"
)

func justfileAWSCLI() Rule {
	const id = "justfile-aws-cli"
	return Rule{
		ID:     id,
		Why:    "aws runs from the checkout's mise, except on Windows, where the http:aws build has no asset and the standalone aws runs",
		Inputs: []Input{{Path: justfilePath, Format: Text}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: justfilePath}
			text, _ := in[justfilePath].(string)
			if !strings.Contains(text, awsCLI) {
				r.add("the justfile must define %s", awsCLI)
			}
			if !strings.Contains(text, awsListRec) {
				r.add("aws-list must run `{{ AWS_CLI }} configure list-profiles` in group cloud")
			}
			return r.out
		},
	}
}

// justfileNoClaudeCodeLint: the third-party claude-code-lint is retired for
// trust reasons; only the official `claude plugin validate` remains (ADR-0041).
func justfileNoClaudeCodeLint() Rule {
	const id = "justfile-no-claude-code-lint"
	return Rule{
		ID:     id,
		Why:    "the distrusted third-party claude-code-lint never returns to the justfile (ADR-0041)",
		Inputs: []Input{{Path: justfilePath, Format: Text}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: justfilePath}
			if text, _ := in[justfilePath].(string); strings.Contains(text, "claude-code-lint") {
				r.add("the justfile invokes the retired claude-code-lint; only `claude plugin validate` remains (ADR-0041)")
			}
			return r.out
		},
	}
}
