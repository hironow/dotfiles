package rules

import "testing"

func hostInputs() Inputs {
	return Inputs{
		codexAgyScript: "import x\n\nANTIGRAVITY_NAMES = (\"antigravity\", \"agy\")\nRun = int\n",
		hostConfig: map[string]any{"tools": map[string]any{
			"github:google-antigravity/antigravity-cli": map[string]any{"version": "latest", "rename_exe": "antigravity"},
		}},
		justfilePath: "JUST_FMT := \"mise x just@1.59.0 -- just\"\n",
		imageConfig:  map[string]any{"tools": map[string]any{"just": "1.59.0"}},
		repoClaudeMd: "@AGENTS.md\n",
		repoAgentsMd: "# Project conventions\n",
		wslConf:      "[boot]\nsystemd=true\n\n[interop]\nappendWindowsPath=false\n",
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
		{"another version", func(in Inputs) { in[justfilePath] = "JUST_FMT := \"mise x just@1.58.0 -- just\"\n" }, "1.58.0"},
		{"the just on PATH", func(in Inputs) { in[justfilePath] = "JUST_FMT := \"just\"\n" }, "JUST_FMT"},
		{"no formatter", func(in Inputs) { in[justfilePath] = "fmt:\n    just --fmt\n" }, "JUST_FMT"},
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
		{"sparse disks", add("sparseVhd=true"), "sparseVhd"},
		{"an idle timeout", add("vmIdleTimeout=60000"), "vmIdleTimeout"},
		{"a memory limit", add("[wsl2]\nmemory=8GB"), "memory"},
		{"a processor limit", add("processors = 4"), "processors"},
		{"mirrored networking on", add("networkingMode=mirrored"), "networkingMode"},
		{"DNS tunneling on", add("dnsTunneling=true"), "dnsTunneling"},
		{"auto proxy on", add("autoProxy=true"), "autoProxy"},
	})
}
