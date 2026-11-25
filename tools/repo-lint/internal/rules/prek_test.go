package rules

import (
	"strings"
	"testing"
)

const gateFlags = "--require-list --min-tokens 11"

func hook(fields ...any) map[string]any {
	h := map[string]any{}
	for i := 0; i+1 < len(fields); i += 2 {
		h[fields[i].(string)] = fields[i+1]
	}
	return h
}

// precommitConfig is a .pre-commit-config.yaml, as yq decodes it, that every
// prek rule accepts.
func precommitConfig() map[string]any {
	return map[string]any{
		"default_install_hook_types": []any{"pre-commit", "commit-msg"},
		"exclude":                    "(?x)^(\n  emulator/|\n  skills/\n)\n",
		"repos": []any{
			map[string]any{"repo": "local", "hooks": []any{
				hook("id", "forbidden-tokens-staged", "entry", "python3 scripts/check_forbidden_tokens.py staged "+gateFlags,
					"language", "system", "pass_filenames", false, "always_run", true, "stages", []any{"pre-commit"}),
				hook("id", "forbidden-tokens-commit-msg", "entry", "python3 scripts/check_forbidden_tokens.py commit-msg "+gateFlags,
					"language", "system", "stages", []any{"commit-msg"}),
			}},
			map[string]any{"repo": "builtin", "hooks": []any{
				hook("id", "check-yaml", "stages", []any{"pre-commit"}),
				hook("id", "check-toml", "stages", []any{"pre-commit"}),
				hook("id", "check-json", "stages", []any{"pre-commit"}),
				hook("id", "check-added-large-files", "stages", []any{"pre-commit"}),
				hook("id", "check-merge-conflict", "stages", []any{"pre-commit"}),
				hook("id", "detect-private-key", "stages", []any{"pre-commit"}),
			}},
			map[string]any{"repo": "local", "hooks": []any{
				hook("id", "mise-versions-check", "entry", "just mise-versions-check", "language", "system",
					"pass_filenames", false, "stages", []any{"pre-commit"},
					"files", `^(config/mise/(image-tools|config)\.toml|\.devcontainer/features/dotfiles-tools/install\.sh|install\.sh|tools/mise-versions/.*)$`),
			}},
		},
	}
}

const prekJustfile = "FORBIDDEN_TOKEN_GATE := \"" + gateFlags + "\"\n\nmise-versions-check:\n    @mise exec -- go run tools/mise-versions/main.go check\n"

func prekInputs() Inputs {
	return Inputs{
		precommitPath: precommitConfig(),
		justfilePath:  prekJustfile,
		siteFiles:     map[string]any{"site/copy.js": "", "site/vendor/ui-sdk/web.css": "", "site/vendor/ui-sdk/web.js": ""},
	}
}

// prekHook is the hook with the id in the config.
func prekHook(in Inputs, id string) map[string]any {
	for _, repo := range tables(in[precommitPath], "repos") {
		for _, h := range tables(repo, "hooks") {
			if h["id"] == id {
				return h
			}
		}
	}
	return nil
}

func addHook(in Inputs, h map[string]any) {
	cfg := in[precommitPath].(map[string]any)
	cfg["repos"] = append(cfg["repos"].([]any), map[string]any{"repo": "local", "hooks": []any{h}})
}

func TestPrekRunsTheConfidentialityGuardsFirstAndFailClosed(t *testing.T) {
	runCases(t, prekConfidentialityGuards(), prekInputs, []ruleCase{
		{"no commit-msg shim", func(in Inputs) { set(in[precommitPath], []any{"pre-commit"}, "default_install_hook_types") }, "commit-msg"},
		{"another hook before the guards", func(in Inputs) {
			cfg := in[precommitPath].(map[string]any)
			repos := cfg["repos"].([]any)
			cfg["repos"] = append([]any{repos[1]}, repos...)
		}, "before every other hook"},
		{"the staged guard lowered", func(in Inputs) {
			prekHook(in, "forbidden-tokens-staged")["entry"] = "python3 scripts/check_forbidden_tokens.py staged --require-list --min-tokens 1"
		}, "forbidden-tokens-staged"},
		{"the commit-msg guard at another stage", func(in Inputs) {
			prekHook(in, "forbidden-tokens-commit-msg")["stages"] = []any{"pre-commit"}
		}, "forbidden-tokens-commit-msg"},
		{"the gate without the list", func(in Inputs) {
			in[justfilePath] = "FORBIDDEN_TOKEN_GATE := \"--min-tokens 11\"\n"
		}, "FORBIDDEN_TOKEN_GATE"},
		{"no gate", func(in Inputs) { in[justfilePath] = "mise-versions-check:\n" }, "FORBIDDEN_TOKEN_GATE"},
		{"a shorter list accepted everywhere", func(in Inputs) {
			in[justfilePath] = strings.ReplaceAll(prekJustfile, "--min-tokens 11", "--min-tokens 1")
			for _, g := range []string{"forbidden-tokens-staged", "forbidden-tokens-commit-msg"} {
				h := prekHook(in, g)
				h["entry"] = strings.ReplaceAll(h["entry"].(string), "--min-tokens 11", "--min-tokens 1")
			}
		}, "11"},
	})
}

func TestPrekHooksOnlyCheck(t *testing.T) {
	mise := func(in Inputs) map[string]any { return prekHook(in, "mise-versions-check") }
	runCases(t, prekCheckOnlyHooks(), prekInputs, []ruleCase{
		{"a hook on pre-push", func(in Inputs) { prekHook(in, "check-yaml")["stages"] = []any{"pre-commit", "pre-push"} }, "pre-push"},
		{"pre-push by default", func(in Inputs) { set(in[precommitPath], []any{"pre-push"}, "default_stages") }, "pre-push"},
		{"a hook with no stages", func(in Inputs) { delete(prekHook(in, "check-yaml"), "stages") }, "check-yaml"},
		{"a recipe as a hook", func(in Inputs) {
			addHook(in, hook("id", "check", "entry", "just check", "stages", []any{"pre-commit"}))
		}, "just check"},
		{"a rewriting hook", func(in Inputs) {
			addHook(in, hook("id", "trailing-whitespace", "stages", []any{"pre-commit"}))
		}, "trailing-whitespace"},
		{"the fast check on every commit", func(in Inputs) { mise(in)["always_run"] = true }, "always_run"},
		{"the fast check on every file", func(in Inputs) { mise(in)["files"] = "." }, "README.md"},
		{"the fast check misses a generator input", func(in Inputs) {
			mise(in)["files"] = `^config/mise/config\.toml$`
		}, "image-tools.toml"},
		{"the fast check with file names", func(in Inputs) { mise(in)["pass_filenames"] = true }, "pass_filenames"},
		{"the fast recipe with dependencies", func(in Inputs) {
			in[justfilePath] = "FORBIDDEN_TOKEN_GATE := \"" + gateFlags + "\"\n\nmise-versions-check: lint\n    @true\n"
		}, "dependencies"},
		{"the secret-key guard dropped", func(in Inputs) {
			repos := in[precommitPath].(map[string]any)["repos"].([]any)
			builtin := repos[1].(map[string]any)
			builtin["hooks"] = builtin["hooks"].([]any)[:5]
		}, "detect-private-key"},
		{"the secret-key guard at another stage", func(in Inputs) {
			prekHook(in, "detect-private-key")["stages"] = []any{"commit-msg"}
		}, "detect-private-key"},
		{"an extra builtin hook", func(in Inputs) {
			addHook(in, hook("id", "mixed-line-ending", "stages", []any{"pre-commit"}))
		}, "mixed-line-ending"},
		{"the fast check behind a comment", func(in Inputs) {
			in[justfilePath] = strings.Replace(prekJustfile, "    @mise exec", "    @true # mise exec", 1)
		}, "mise-versions"},
		{"the fast check failure swallowed", func(in Inputs) {
			in[justfilePath] = strings.Replace(prekJustfile, "main.go check\n", "main.go check || true\n", 1)
		}, "mise-versions"},
		{"the fast recipe checks nothing", func(in Inputs) {
			in[justfilePath] = strings.Replace(prekJustfile, "@mise exec -- go run tools/mise-versions/main.go check", "@true", 1)
		}, "mise-versions"},
		{"the vendored styles excluded", func(in Inputs) {
			set(in[precommitPath], "^site/vendor/.*\\.css$", "exclude")
		}, "site/vendor/ui-sdk/web.css"},
		{"the vendored folder excluded", func(in Inputs) {
			set(in[precommitPath], "(?x)^(\n  emulator/|\n  site/\n)\n", "exclude")
		}, "site/"},
	})
}

func templatePrecommit() map[string]any {
	stages := []any{"pre-commit"}
	return map[string]any{
		"minimum_prek_version":       "0.5.4",
		"default_install_hook_types": []any{"pre-commit"},
		"default_stages":             []any{"pre-commit"},
		"repos": []any{
			map[string]any{"repo": "builtin", "hooks": []any{
				hook("id", "trailing-whitespace", "stages", stages, "args", []any{"--check"}),
				hook("id", "end-of-file-fixer", "stages", stages, "args", []any{"--check"}),
				hook("id", "check-yaml", "stages", stages),
				hook("id", "check-toml", "stages", stages),
				hook("id", "check-json", "stages", stages),
				hook("id", "check-added-large-files", "stages", stages),
				hook("id", "check-merge-conflict", "stages", stages),
				hook("id", "detect-private-key", "stages", stages),
			}},
			map[string]any{"repo": "local", "hooks": []any{
				hook("id", "ruff-format-check", "stages", stages, "language", "system", "types_or", []any{"python", "pyi"}, "require_serial", true,
					"entry", "uv run --locked --only-group lint ruff format --check --force-exclude --"),
				hook("id", "ruff-check", "stages", stages, "language", "system", "types_or", []any{"python", "pyi"}, "require_serial", true,
					"entry", "uv run --locked --only-group lint ruff check --no-fix --no-fix-only --force-exclude --"),
			}},
		},
	}
}

func templateInputs() Inputs { return Inputs{templatePrecommitPath: templatePrecommit()} }

func templateHook(in Inputs, id string) map[string]any {
	for _, repo := range tables(in[templatePrecommitPath], "repos") {
		for _, h := range tables(repo, "hooks") {
			if h["id"] == id {
				return h
			}
		}
	}
	return nil
}

func TestTemplatePrekHooksOnlyCheck(t *testing.T) {
	runCases(t, templatePrekCheckOnly(), templateInputs, []ruleCase{
		{"a push shim", func(in Inputs) {
			set(in[templatePrecommitPath], []any{"pre-commit", "pre-push"}, "default_install_hook_types")
		}, "default_install_hook_types"},
		{"no default stage", func(in Inputs) { delete(in[templatePrecommitPath].(map[string]any), "default_stages") }, "default_stages"},
		{"a hook on pre-push", func(in Inputs) { templateHook(in, "check-yaml")["stages"] = []any{"pre-push"} }, "check-yaml"},
		{"a whitespace hook that rewrites", func(in Inputs) { delete(templateHook(in, "end-of-file-fixer"), "args") }, "end-of-file-fixer"},
		{"a recipe as a hook", func(in Inputs) { templateHook(in, "ruff-check")["entry"] = "just lint" }, "just"},
		{"ruff fixes", func(in Inputs) {
			templateHook(in, "ruff-check")["entry"] = "uv run --locked --only-group lint ruff check --fix --"
		}, "ruff-check"},
		{"ruff formats", func(in Inputs) {
			templateHook(in, "ruff-format-check")["entry"] = "uv run --locked --only-group lint ruff format --force-exclude --"
		}, "ruff-format-check"},
		{"ruff without the staged names", func(in Inputs) { templateHook(in, "ruff-check")["pass_filenames"] = false }, "pass_filenames"},
		{"ruff in parallel", func(in Inputs) { delete(templateHook(in, "ruff-format-check"), "require_serial") }, "require_serial"},
		{"ruff on other files", func(in Inputs) { templateHook(in, "ruff-check")["types_or"] = []any{"python"} }, "types_or"},
		{"ruff in its own environment", func(in Inputs) { templateHook(in, "ruff-check")["language"] = "python" }, "language"},
		{"ruff applies fixes only", func(in Inputs) {
			templateHook(in, "ruff-check")["entry"] = "uv run --locked --only-group lint ruff check --no-fix --force-exclude --"
		}, "ruff-check"},
		{"ruff checks excluded files named on the command line", func(in Inputs) {
			templateHook(in, "ruff-format-check")["entry"] = "uv run --locked --only-group lint ruff format --check --"
		}, "ruff-format-check"},
		{"a formatter under another name", func(in Inputs) {
			repos := in[templatePrecommitPath].(map[string]any)["repos"].([]any)
			local := repos[1].(map[string]any)
			local["hooks"] = append(local["hooks"].([]any), hook("id", "fmt", "stages", []any{"pre-commit"},
				"language", "system", "entry", "uv run --locked --only-group lint ruff format ."))
		}, "fmt"},
		{"no minimum prek", func(in Inputs) { delete(in[templatePrecommitPath].(map[string]any), "minimum_prek_version") }, "minimum_prek_version"},
		{"a prek without --check", func(in Inputs) { set(in[templatePrecommitPath], "0.5.3", "minimum_prek_version") }, "minimum_prek_version"},
		{"a second hook under a required id", func(in Inputs) {
			repos := in[templatePrecommitPath].(map[string]any)["repos"].([]any)
			local := repos[1].(map[string]any)
			local["hooks"] = append(local["hooks"].([]any), hook("id", "ruff-check", "stages", []any{"pre-commit"},
				"language", "system", "entry", "uv run --locked --only-group lint ruff format"))
		}, "ruff-check"},
		{"ruff may change the lockfile", func(in Inputs) {
			templateHook(in, "ruff-check")["entry"] = "uv run --only-group lint ruff check --no-fix --no-fix-only --force-exclude --"
		}, "--locked"},
		{"the secret-key guard dropped", func(in Inputs) {
			repos := in[templatePrecommitPath].(map[string]any)["repos"].([]any)
			builtin := repos[0].(map[string]any)
			builtin["hooks"] = builtin["hooks"].([]any)[:7]
		}, "detect-private-key"},
		{"no ruff check", func(in Inputs) {
			repos := in[templatePrecommitPath].(map[string]any)["repos"].([]any)
			in[templatePrecommitPath].(map[string]any)["repos"] = repos[:1]
		}, "ruff-check"},
	})
}
