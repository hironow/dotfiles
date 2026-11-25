package rules

import (
	"strings"
	"testing"
)

const jsJustfile = `js-install:
    @{{ BUN }} install --frozen-lockfile --ignore-scripts

js-typecheck: js-install
    {{ BUN }} check --no-script

lint:
    @echo '🔍 JS/TS (oxlint, bun check)...'
    # bun check reads tsconfig.json
`

// jsInputs is the JS gate's files, as decoded, that every JS rule accepts.
func jsInputs() Inputs {
	return Inputs{
		packageJSON: map[string]any{
			"private": true, "type": "module",
			"devDependencies": map[string]any{"oxlint": "1.93.0", "@types/bun": "1.4.4"},
		},
		bunfigPath:   map[string]any{"install": map[string]any{"minimumReleaseAge": float64(604800), "exact": true}},
		justfilePath: jsJustfile,
		tsconfigPath: map[string]any{"compilerOptions": map[string]any{"strict": true, "noEmit": true}},
		siteCopy:     "// @ts-check\nexport {};\n",
		oxlintPath:   oxlintText,
		piExtensions: map[string]any{
			"config/pi/extensions/jev.ts": "import type { ExtensionAPI } from \"@earendil-works/pi-coding-agent\";\nimport { x } from \"./y\";\n",
		},
		piRtkExtension: rtkExtensionText,
		piInstaller:    "VENDORED_SENTINEL = \"// --- upstream rtk.ts follows, unmodified ---\\n\"\n",
	}
}

func pkg(in Inputs) map[string]any { return in[packageJSON].(map[string]any) }

func TestJSDevDependenciesArePinnedAndInstalledWithoutScripts(t *testing.T) {
	runCases(t, jsDepsPinned(), jsInputs, []ruleCase{
		{"a public package", func(in Inputs) { pkg(in)["private"] = false }, "private"},
		{"a runtime dependency", func(in Inputs) { pkg(in)["dependencies"] = map[string]any{"x": "1.0.0"} }, "dependencies"},
		{"a range", func(in Inputs) { set(in[packageJSON], "^1.93.0", "devDependencies", "oxlint") }, "^1.93.0"},
		{"install scripts run", func(in Inputs) {
			in[justfilePath] = strings.Replace(jsJustfile, " --ignore-scripts", "", 1)
		}, "--ignore-scripts"},
		{"the lockfile may move", func(in Inputs) {
			in[justfilePath] = strings.Replace(jsJustfile, " --frozen-lockfile", "", 1)
		}, "--frozen-lockfile"},
		{"no install recipe", func(in Inputs) { in[justfilePath] = "lint:\n    true\n" }, "js-install"},
		{"no cooldown", func(in Inputs) { set(in[bunfigPath], float64(0), "install", "minimumReleaseAge") }, "minimumReleaseAge"},
		{"ranges saved", func(in Inputs) { set(in[bunfigPath], nil, "install", "exact") }, "exact"},
	})
}

func TestTheTypeCheckIsNotWeakened(t *testing.T) {
	runCases(t, jsTypeCheckNotWeakened(), jsInputs, []ruleCase{
		{"not strict", func(in Inputs) { set(in[tsconfigPath], false, "compilerOptions", "strict") }, "strict"},
		{"emits", func(in Inputs) { set(in[tsconfigPath], nil, "compilerOptions", "noEmit") }, "noEmit"},
		{"the page script unchecked", func(in Inputs) { in[siteCopy] = "export {};\n" }, "@ts-check"},
		{"a check that a script can shadow", func(in Inputs) {
			in[justfilePath] = jsJustfile + "\nci:\n    bun check\n"
		}, "--no-script"},
		{"a check script", func(in Inputs) { pkg(in)["scripts"] = map[string]any{"check": "true"} }, "check script"},
	})
}

const oxlintText = `{
// Every category is error.
"plugins": ["eslint", "typescript", "unicorn", "oxc", "import"],
"categories": {
"correctness": "error",
"suspicious": "error",
"pedantic": "error",
"perf": "error",
"style": "error",
"restriction": "error",
"nursery": "error"
},
"options": { "typeAware": true },
// Third-party bytes we must not edit.
"ignorePatterns": ["site/vendor/**", "config/pi/extensions/rtk.ts"],
"rules": {
"one-var": ["error", "never"],
// The two rules ban each other's only alternative, so both stay off.
"import/no-default-export": "off",
"import/no-named-export": "off"
},
"overrides": [
{ "files": ["tests/**"], "rules": {
// A test lives in tests/unit/ and imports the code it tests from config/.
"import/no-relative-parent-imports": "off",
"max-statements": ["error", 15]
} }
]
}
`

func TestOxlintKeepsEveryCheckAtError(t *testing.T) {
	edit := func(old, new string) func(Inputs) {
		return func(in Inputs) { in[oxlintPath] = strings.Replace(oxlintText, old, new, 1) }
	}
	runCases(t, oxlintStrict(), jsInputs, []ruleCase{
		{"a category lowered", edit(`"pedantic": "error"`, `"pedantic": "warn"`), "pedantic"},
		{"a category dropped", edit(",\n\"nursery\": \"error\"", ""), "nursery"},
		{"a rule warned", edit(`"one-var": ["error", "never"]`, `"one-var": ["warn", "never"]`), "one-var"},
		{"an override rule warned", edit(`"max-statements": ["error", 15]`, `"max-statements": "warn"`), "max-statements"},
		{"a default plugin dropped", edit(`"oxc", `, ""), "oxc"},
		{"type-aware rules off", edit(`"typeAware": true`, `"typeAware": false`), "typeAware"},
		{"first-party files ignored", edit(`"config/pi/extensions/rtk.ts"]`, `"config/pi/extensions/rtk.ts", "src/**"]`), "src/**"},
		{"an opt-out with no reason", edit("// The two rules ban each other's only alternative, so both stay off.\n", ""), "import/no-default-export"},
		{"an opt-out with a short reason", edit("// A test lives in tests/unit/ and imports the code it tests from config/.", "// tests"), "import/no-relative-parent-imports"},
		{"unreadable", edit(`"options"`, `options`), "decode"},
	})
}

func TestPiExtensionsImportPiTypesOnly(t *testing.T) {
	ext := func(text string) func(Inputs) {
		return func(in Inputs) { in[piExtensions].(map[string]any)["config/pi/extensions/x.ts"] = text }
	}
	runCases(t, piExtensionsTypeOnlyImports(), jsInputs, []ruleCase{
		{"a value import", ext("import { Type } from \"@earendil-works/pi-ai\";\n"), "@earendil-works/pi-ai"},
		{"a value import over lines", ext("import {\n  a,\n  b,\n} from '@earendil-works/pi-tui';\n"), "@earendil-works/pi-tui"},
		{"a default import", ext("import pi from \"@earendil-works/pi-coding-agent\";\n"), "@earendil-works/pi-coding-agent"},
	})
}

const rtkExtensionText = `// dotfiles-managed: rtk
// Vendored from rtk 1.2.0; Apache License 2.0 (https://github.com/rtk-ai/rtk/blob/master/LICENSE).
// --- upstream rtk.ts follows, unmodified ---
function isBash(event) {
  return event.toolName === "bash"
}
export default function (pi) {
  pi.on("tool_call", (event) => {
    try {
      if (process.env.RTK_DISABLED === "1") return
    } catch {
      // Fail open: never block execution on an unexpected error.
    }
  })
}
`

func TestTheVendoredRTKExtensionOnlyRewritesBashAndFailsOpen(t *testing.T) {
	edit := func(old, new string) func(Inputs) {
		return func(in Inputs) { in[piRtkExtension] = strings.Replace(rtkExtensionText, old, new, 1) }
	}
	runCases(t, piRtkExtensionScoped(), jsInputs, []ruleCase{
		{"not the managed copy", edit("// dotfiles-managed: rtk\n", ""), "dotfiles-managed"},
		{"no license", edit("Apache License 2.0", "MIT"), "Apache"},
		{"the license only below the sentinel", func(in Inputs) {
			text := strings.Replace(rtkExtensionText, "Apache License 2.0", "MIT", 1)
			in[piRtkExtension] = text + "// Apache License 2.0\n"
		}, "Apache"},
		{"no sentinel", edit("// --- upstream rtk.ts follows, unmodified ---\n", ""), "sentinel"},
		{"every tool rewritten", edit(`return event.toolName === "bash"`, "return true"), "toolName"},
		{"no kill switch", edit(`if (process.env.RTK_DISABLED === "1") return`, ""), "RTK_DISABLED"},
		{"fails closed", edit("// Fail open: never block execution on an unexpected error.", "throw new Error()"), "Fail open"},
		{"no sentinel constant", func(in Inputs) { in[piInstaller] = "x = 1\n" }, "VENDORED_SENTINEL"},
	})
}
