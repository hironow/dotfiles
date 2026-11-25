package rules

import (
	"strings"
	"testing"
)

const hostJustfile = `JUST_FMT := "mise x just@1.59.0 -- just"

fmt:
    {{ JUST_FMT }} --justfile justfile --fmt
    {{ JUST_FMT }} --justfile templates/agent-baseline/justfile --fmt

check-except-go:
    {{ JUST_FMT }} --justfile justfile --fmt --check
    {{ JUST_FMT }} --justfile templates/agent-baseline/justfile --fmt --check
`

func hostInputs() Inputs {
	return Inputs{
		codexAgyScript: "import x\n\nANTIGRAVITY_NAMES = (\"antigravity\", \"agy\")\nRun = int\n",
		hostConfig: map[string]any{"tools": map[string]any{
			"github:google-antigravity/antigravity-cli": map[string]any{"version": "latest", "rename_exe": "antigravity"},
		}},
		justfilePath:  hostJustfile,
		ghosttyConfig: "# Send CSI-u for ctrl+enter\nkeybind = ctrl+enter=text:\\x1b[13;5u\nkeybind = opt+left=esc:b\nkeybind = opt+right=esc:f\n",
		zshrcPath:     "bindkey '^[[13;5u' _ctrl_enter_newline\n",
		imageConfig:   map[string]any{"tools": map[string]any{"just": "1.59.0"}},
		repoClaudeMd:  "@AGENTS.md\n",
		repoAgentsMd:  "# Project conventions\n",
		wslConf:       "[boot]\nsystemd=true\n\n[interop]\nappendWindowsPath=false\n",
		wslconfigTemplate: "# Deliberately absent: sparseVhd=true, vmIdleTimeout, memory=, processors=.\n[experimental]\n" +
			"autoMemoryReclaim=gradual\n# Optional:\n# [wsl2]\n# networkingMode=mirrored\n# dnsTunneling=true\n# autoProxy=true\n",
	}
}

func TestDeployLooksForTheNameMiseInstallsAntigravityAs(t *testing.T) {
	runCases(t, codexAgyNamesFollowMise(), hostInputs, []ruleCase{
		{"the short name first", func(in Inputs) {
			in[codexAgyScript] = "ANTIGRAVITY_NAMES = (\"agy\", \"antigravity\")\n"
		}, "agy"},
		{"mise renames it", func(in Inputs) {
			set(in[hostConfig], "agy2", "tools", "github:google-antigravity/antigravity-cli", "rename_exe")
		}, "agy2"},
		{"no names", func(in Inputs) { in[codexAgyScript] = "x = 1\n" }, "ANTIGRAVITY_NAMES"},
		{"no antigravity tool", func(in Inputs) {
			set(in[hostConfig], nil, "tools", "github:google-antigravity/antigravity-cli")
		}, "antigravity-cli"},
	})
}

func TestJustFormatsWithThePinnedJust(t *testing.T) {
	runCases(t, justFmtPinned(), hostInputs, []ruleCase{
		{"another version", func(in Inputs) {
			in[justfilePath] = strings.Replace(hostJustfile, "just@1.59.0", "just@1.58.0", 1)
		}, "1.58.0"},
		{"the just on PATH", func(in Inputs) {
			in[justfilePath] = strings.Replace(hostJustfile, `"mise x just@1.59.0 -- just"`, `"just"`, 1)
		}, "JUST_FMT"},
		{"no formatter", func(in Inputs) { in[justfilePath] = "fmt:\n    just --fmt\n" }, "JUST_FMT"},
		{"the check formats with another just", func(in Inputs) {
			in[justfilePath] = strings.Replace(hostJustfile, "{{ JUST_FMT }} --justfile justfile --fmt --check", "just --justfile justfile --fmt --check", 1)
		}, "check-except-go"},
		{"fmt skips the template", func(in Inputs) {
			in[justfilePath] = strings.Replace(hostJustfile, "    {{ JUST_FMT }} --justfile templates/agent-baseline/justfile --fmt\n", "", 1)
		}, "templates/agent-baseline/justfile"},
	})
}

func TestTheRepositoryClaudeMdImportsItsRules(t *testing.T) {
	runCases(t, repoClaudeMdImportsAgents(), hostInputs, []ruleCase{
		{"no import", func(in Inputs) { in[repoClaudeMd] = "# Rules\n" }, "@AGENTS.md"},
		{"the import inside a sentence", func(in Inputs) { in[repoClaudeMd] = "Read @AGENTS.md first.\n" }, "@AGENTS.md"},
	})
}

func TestTheWSLDistroTemplateHardens(t *testing.T) {
	runCases(t, wslConfHardens(), hostInputs, []ruleCase{
		{"systemd off", func(in Inputs) { in[wslConf] = "[boot]\n# systemd=true\n[interop]\nappendWindowsPath=false\n" }, "systemd"},
		{"the PATH key in another section", func(in Inputs) {
			in[wslConf] = "[boot]\nsystemd=true\n[broken]\nappendWindowsPath=false\n"
		}, "appendWindowsPath"},
		{"the Windows PATH appended", func(in Inputs) {
			in[wslConf] = "[boot]\nsystemd=true\n[interop]\nappendWindowsPath=true\n"
		}, "appendWindowsPath"},
	})
}

func TestTheWSLHostTemplateShipsOnlyTheSafeSubset(t *testing.T) {
	add := func(line string) func(Inputs) {
		return func(in Inputs) { in[wslconfigTemplate] = in[wslconfigTemplate].(string) + line + "\n" }
	}
	runCases(t, wslconfigSafeSubset(), hostInputs, []ruleCase{
		{"no memory reclaim", func(in Inputs) { in[wslconfigTemplate] = "[experimental]\n# autoMemoryReclaim=gradual\n" }, "autoMemoryReclaim"},
		{"memory reclaim in another section", func(in Inputs) { in[wslconfigTemplate] = "[wsl2]\nautoMemoryReclaim=gradual\n" }, "autoMemoryReclaim"},
		{"sparse disks", add("sparseVhd=true"), "sparseVhd"},
		{"an idle timeout", add("vmIdleTimeout=60000"), "vmIdleTimeout"},
		{"a memory limit", add("[wsl2]\nmemory=8GB"), "memory"},
		{"a processor limit", add("processors = 4"), "processors"},
		{"mirrored networking on", add("networkingMode=mirrored"), "networkingMode"},
		{"DNS tunneling on", add("dnsTunneling=true"), "dnsTunneling"},
		{"auto proxy on", add("autoProxy=true"), "autoProxy"},
	})
}

func TestGhosttySendsWhatTheShellBinds(t *testing.T) {
	runCases(t, ghosttyKeysReachZsh(), hostInputs, []ruleCase{
		{"ghostty sends a bare CR", func(in Inputs) {
			in[ghosttyConfig] = strings.Replace(in[ghosttyConfig].(string), `ctrl+enter=text:\x1b[13;5u`, `ctrl+enter=text:\x0d`, 1)
		}, "ctrl+enter"},
		{"only in a comment", func(in Inputs) {
			in[ghosttyConfig] = strings.Replace(in[ghosttyConfig].(string), "keybind = ctrl+enter", "# keybind = ctrl+enter", 1)
		}, "ctrl+enter"},
		{"option-left deletes a word", func(in Inputs) {
			in[ghosttyConfig] = strings.Replace(in[ghosttyConfig].(string), "opt+left=esc:b", "opt+left=esc:d", 1)
		}, "opt+left"},
		{"option-right bound twice", func(in Inputs) {
			in[ghosttyConfig] = in[ghosttyConfig].(string) + "keybind = opt+right=esc:f\n"
		}, "opt+right"},
		{"zsh does not claim it", func(in Inputs) { in[zshrcPath] = "bindkey '^M' accept-line\n" }, "13;5u"},
	})
}
