package rules

import (
	"maps"
	"regexp"
	"slices"
	"strconv"
	"strings"
)

const templatePrecommitPath = "templates/agent-baseline/.pre-commit-config.yaml"

var (
	forbiddenTokenGate = regexp.MustCompile(`(?m)^FORBIDDEN_TOKEN_GATE := "([^"]*)"$`)
	recipeHeader       = func(name string) *regexp.Regexp {
		return regexp.MustCompile(`(?m)^` + regexp.QuoteMeta(name) + `:(.*)$`)
	}
)

// guardHooks are the confidentiality guards, in the order they run first.
var guardHooks = []struct{ id, mode, stage string }{
	{"forbidden-tokens-staged", "staged", "pre-commit"},
	{"forbidden-tokens-commit-msg", "commit-msg", "commit-msg"},
}

// fastCheckInputs are the files the fast version check reads; fastCheckOthers
// are files it must not run for.
var (
	fastCheckInputs = []string{
		"config/mise/image-tools.toml", "config/mise/config.toml",
		".devcontainer/features/dotfiles-tools/install.sh", "install.sh", "tools/mise-versions/main.go",
	}
	fastCheckOthers = []string{"README.md", "scripts/install.sh", "config/mise/other.toml"}
)

// minForbiddenTokens is the fewest tokens the private list may hold; a gate
// that accepts a shorter list lets a truncated list pass.
const minForbiddenTokens = 11

// requiredHooks are the read-only guards each config keeps (ADR 0085): the
// confidentiality guards, prek's builtin checks, the secret-key detector, and
// the fast version check (dotfiles) or ruff (the scaffold).
var (
	requiredHooks = []string{
		"forbidden-tokens-staged", "forbidden-tokens-commit-msg", "check-yaml", "check-toml", "check-json",
		"check-added-large-files", "check-merge-conflict", "detect-private-key", "mise-versions-check",
	}
	templateRequiredHooks = []string{
		"trailing-whitespace", "end-of-file-fixer", "check-yaml", "check-toml", "check-json",
		"check-added-large-files", "check-merge-conflict", "detect-private-key", "ruff-format-check", "ruff-check",
	}
)

// exactHooks reports each required hook the config lacks and each hook it has
// beyond them: a new hook, under any name, is a decision for ADR 0085.
func exactHooks(r *report, hooks []map[string]any, required []string) {
	for _, want := range required {
		if hookByID(hooks, want) == nil {
			r.add("hook %s is missing; it is one of the required read-only guards", want)
		}
	}
	for _, h := range hooks {
		if id := hookID(h); !slices.Contains(required, id) {
			r.add("hook %s is not one of the read-only guards %v", id, required)
		}
	}
}

// recipeCommands is the recipe's command lines, trimmed, without blank lines
// and comments.
func recipeCommands(justfile, name string) []string {
	body, _ := recipeBody(justfile, name)
	var out []string
	for line := range strings.SplitSeq(body, "\n") {
		line = strings.TrimSpace(line)
		if line != "" && !strings.HasPrefix(line, "#") {
			out = append(out, line)
		}
	}
	return out
}

// fastRecipe is the whole body of the fast version check: one command whose
// failure fails the hook.
const fastRecipe = "@mise exec -- go run tools/mise-versions/main.go check"

// templateRuffEntries are the scaffold's ruff hooks, checking the staged
// Python: never fixing (--no-fix --no-fix-only), never changing uv.lock
// (--locked), and honouring excludes for named files (--force-exclude).
var templateRuffEntries = map[string]string{
	"ruff-format-check": "uv run --locked --only-group lint ruff format --check --force-exclude --",
	"ruff-check":        "uv run --locked --only-group lint ruff check --no-fix --no-fix-only --force-exclude --",
}

// minPrek is the first prek whose builtin whitespace hooks take --check.
const minPrek = "0.5.4"

// rewritingHooks fix files in place; ADR 0083/0085 keep hooks read-only.
var rewritingHooks = []string{"trailing-whitespace", "end-of-file-fixer"}

// allHooks is every hook of a prek config, in order.
func allHooks(cfg any) []map[string]any {
	var out []map[string]any
	for _, repo := range tables(cfg, "repos") {
		out = append(out, tables(repo, "hooks")...)
	}
	return out
}

func hookID(h map[string]any) string {
	id, _ := str(h, "id")
	return id
}

// prekConfidentialityGuards: the forbidden-token guards keep confidential
// words out of commits. Both git shims are installed, the guards run before
// every other hook, and each runs fail-closed with the justfile's one gate
// value, so a hook quietly moved to `--min-tokens 1` fails.
func prekConfidentialityGuards() Rule {
	const id = "prek-confidentiality-guards"
	return Rule{
		ID:     id,
		Why:    "the forbidden-token guards run first at both git stages, fail-closed with the justfile's gate",
		Inputs: []Input{{Path: precommitPath, Format: YAML}, {Path: justfilePath, Format: Text}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: precommitPath}
			types := strs(in[precommitPath], "default_install_hook_types")
			for _, stage := range []string{"pre-commit", "commit-msg"} {
				if !slices.Contains(types, stage) {
					r.add("default_install_hook_types must install the %s shim", stage)
				}
			}
			text, _ := in[justfilePath].(string)
			m := forbiddenTokenGate.FindStringSubmatch(text)
			n := 0
			if m != nil {
				n, _ = strconv.Atoi(strings.TrimPrefix(m[1], "--require-list --min-tokens "))
			}
			if m == nil || !strings.HasPrefix(m[1], "--require-list --min-tokens ") || n < minForbiddenTokens {
				r.addAt(justfilePath, `FORBIDDEN_TOKEN_GATE must be "--require-list --min-tokens <n>" with n at least %d`, minForbiddenTokens)
				return r.out
			}
			hooks := allHooks(in[precommitPath])
			for i, g := range guardHooks {
				if i >= len(hooks) || hookID(hooks[i]) != g.id {
					r.add("%s must be hook %d, before every other hook", g.id, i+1)
				}
				h := hookByID(hooks, g.id)
				if h == nil {
					continue
				}
				if want := "python3 scripts/check_forbidden_tokens.py " + g.mode + " " + m[1]; h["entry"] != want {
					r.add("%s must run %q", g.id, want)
				}
				if stages := strs(h, "stages"); !slices.Equal(stages, []string{g.stage}) {
					r.add("%s must run at stage %s, not %v", g.id, g.stage, stages)
				}
			}
			return r.out
		},
	}
}

func hookByID(hooks []map[string]any, id string) map[string]any {
	for _, h := range hooks {
		if hookID(h) == id {
			return h
		}
	}
	return nil
}

// prekCheckOnlyHooks: git hooks only check (ADR 0083/0084/0085). No hook runs
// at pre-push, every hook names its stage, no hook rewrites files, the only
// local hooks are the guards and the fast version check, which runs only when
// one of its files is staged, and the vendored folder stays read by the hooks.
func prekCheckOnlyHooks() Rule {
	const id = "prek-check-only-hooks"
	return Rule{
		ID:     id,
		Why:    "the git hooks only check: no pre-push, no rewriting, no recipe but the fast version check (ADR 0083/0084/0085)",
		Inputs: []Input{{Path: precommitPath, Format: YAML}, {Path: justfilePath, Format: Text}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: precommitPath}
			cfg := in[precommitPath]
			if slices.Contains(strs(cfg, "default_stages"), "pre-push") {
				r.add("default_stages must not name pre-push (ADR 0084 D2)")
			}
			for _, h := range allHooks(cfg) {
				hid := hookID(h)
				want := []string{"pre-commit"}
				if hid == "forbidden-tokens-commit-msg" {
					want = []string{"commit-msg"}
				}
				if stages := strs(h, "stages"); !slices.Equal(stages, want) {
					r.add("hook %s must name its own stages %v, not %v (ADR 0084 D2)", hid, want, stages)
				}
				if slices.Contains(rewritingHooks, hid) {
					r.add("hook %s rewrites files; hooks only check (ADR 0085)", hid)
				}
				if entry, ok := str(h, "entry"); ok && hookByIDList(guardHooks, hid) == "" && entry != "just mise-versions-check" {
					r.add("hook %s runs %q; the only local hooks are the guards and `just mise-versions-check`", hid, entry)
				}
			}
			exactHooks(r, allHooks(cfg), requiredHooks)
			checkFastHook(r, hookByID(allHooks(cfg), "mise-versions-check"))
			text, _ := in[justfilePath].(string)
			if m := recipeHeader("mise-versions-check").FindStringSubmatch(text); m == nil {
				r.addAt(justfilePath, "the justfile has no mise-versions-check recipe")
			} else if strings.TrimSpace(m[1]) != "" {
				r.addAt(justfilePath, "mise-versions-check must have no dependencies; the hook stays fast")
			}
			if cmds := recipeCommands(text, "mise-versions-check"); !slices.Equal(cmds, []string{fastRecipe}) {
				r.addAt(justfilePath, "mise-versions-check must run exactly `%s`, not %q", fastRecipe, cmds)
			}
			if exclude, ok := str(cfg, "exclude"); ok {
				if re, err := excludeRegexp(exclude); err == nil && re.MatchString("site/vendor/x.js") {
					r.add("the exclude leaves site/ out; the other hooks must still read the vendored files")
				}
			}
			return r.out
		},
	}
}

func hookByIDList(guards []struct{ id, mode, stage string }, id string) string {
	for _, g := range guards {
		if g.id == id {
			return g.id
		}
	}
	return ""
}

// checkFastHook checks the one recipe hook: it runs only when one of its
// files is staged (ADR 0084 D1(d)) and gets no file names.
func checkFastHook(r *report, h map[string]any) {
	if h == nil {
		r.add("hook mise-versions-check is missing")
		return
	}
	if pf, ok := at(h, "pass_filenames"); !ok || pf != false {
		r.add("hook mise-versions-check must set pass_filenames: false")
	}
	if lang, _ := str(h, "language"); lang != "system" {
		r.add("hook mise-versions-check must use language: system")
	}
	if _, ok := at(h, "always_run"); ok {
		r.add("hook mise-versions-check must not set always_run; it runs only when one of its files is staged")
	}
	files, _ := str(h, "files")
	re, err := regexp.Compile(files)
	if files == "" || err != nil {
		r.add("hook mise-versions-check needs a files pattern RE2 can read")
		return
	}
	for _, p := range fastCheckInputs {
		if !re.MatchString(p) {
			r.add("hook mise-versions-check must run when %s is staged", p)
		}
	}
	for _, p := range fastCheckOthers {
		if re.MatchString(p) {
			r.add("hook mise-versions-check must not run for %s", p)
		}
	}
}

// templatePrekCheckOnly: the scaffold that new repositories start from ships
// only check-only hooks at pre-commit, and its ruff hooks check the staged
// Python without fixing it.
func templatePrekCheckOnly() Rule {
	const id = "template-prek-check-only"
	return Rule{
		ID:     id,
		Why:    "the agent-baseline scaffold ships only check-only pre-commit hooks, and its ruff hooks check staged Python without fixing it",
		Inputs: []Input{{Path: templatePrecommitPath, Format: YAML}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: templatePrecommitPath}
			cfg := in[templatePrecommitPath]
			for _, key := range []string{"default_install_hook_types", "default_stages"} {
				if got := strs(cfg, key); !slices.Equal(got, []string{"pre-commit"}) {
					r.add("%s must be [pre-commit], not %v", key, got)
				}
			}
			if v, _ := str(cfg, "minimum_prek_version"); v == "" || less(v, minPrek) {
				r.add("minimum_prek_version must be at least %s, the first prek whose whitespace hooks take --check, not %q", minPrek, v)
			}
			hooks := allHooks(cfg)
			exactHooks(r, hooks, templateRequiredHooks)
			for _, h := range hooks {
				hid := hookID(h)
				if stages := strs(h, "stages"); !slices.Equal(stages, []string{"pre-commit"}) {
					r.add("hook %s must run at [pre-commit] only, not %v", hid, stages)
				}
				if entry, _ := str(h, "entry"); strings.HasPrefix(strings.TrimSpace(entry), "just ") {
					r.add("hook %s runs a just recipe; the scaffold's hooks call none", hid)
				}
				if slices.Contains(rewritingHooks, hid) && !slices.Contains(strs(h, "args"), "--check") {
					r.add("hook %s must pass --check; scaffold hooks never rewrite", hid)
				}
			}
			for _, id := range slices.Sorted(maps.Keys(templateRuffEntries)) {
				h := hookByID(hooks, id)
				if h == nil {
					continue
				}
				if entry, _ := str(h, "entry"); entry != templateRuffEntries[id] {
					r.add("hook %s must run %q (checks only, uv.lock untouched, excludes kept), not %q", id, templateRuffEntries[id], entry)
				}
				if v, _ := at(h, "require_serial"); v != true {
					r.add("hook %s must set require_serial: true", id)
				}
				if !slices.Equal(strs(h, "types_or"), []string{"python", "pyi"}) {
					r.add("hook %s must set types_or: [python, pyi]", id)
				}
				if lang, _ := str(h, "language"); lang != "system" {
					r.add("hook %s must use language: system", id)
				}
				if pf, ok := at(h, "pass_filenames"); ok && pf == false {
					r.add("hook %s must get the staged file names (no pass_filenames: false)", id)
				}
			}
			return r.out
		},
	}
}
