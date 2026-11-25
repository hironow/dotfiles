package rules

import (
	"slices"
	"strings"
	"testing"
)

func pluginDeclaration() map[string]any {
	return map[string]any{
		"marketplaces": map[string]any{
			"openai-codex":                "openai/codex-plugin-cc#v1.0.6",
			"claude-plugins-official":     "anthropics/claude-plugins-official",
			"egm":                         "google/elephant-goldfish-model#v0.1.1",
			"antigravity-for-claude-code": "yuting0624/antigravity-for-claude-code#v0.31.1",
			"hironow-plugins":             "./.claude-plugin/marketplace.json",
		},
		"plugins": []any{
			"antigravity@antigravity-for-claude-code", "codex@openai-codex", "egm@egm",
			"grilling@hironow-plugins", "vercel@claude-plugins-official",
		},
	}
}

func skillLockFile(names ...string) map[string]any {
	skills := make([]any, 0, len(names))
	for _, name := range names {
		skills = append(skills, map[string]any{"installed_dir": name, "source": "hironow/skills"})
	}
	return map[string]any{"skills": skills}
}

func marketplaceFile() map[string]any {
	return map[string]any{
		"metadata": map[string]any{"version": "1.3.5"},
		"plugins":  []any{map[string]any{"name": "grilling", "source": "./plugins/grilling", "version": "0.3.0"}},
	}
}

const egmReviewerText = `---
name: egm-reviewer
tools: read, grep, find, ls
extensions:
systemPromptMode: replace
inheritProjectContext: false
inheritGlobalContext: false
inheritSkills: false
defaultContext: fresh
---

Review only the supplied target.
`

// pluginInputs is the plugin and skill declarations, as the shell decodes
// them, that every plugin rule accepts.
func pluginInputs() Inputs {
	return Inputs{
		pluginsDecl:       pluginDeclaration(),
		localMarketplaces: map[string]any{marketplacePath: marketplaceFile()},
		marketplacePath:   marketplaceFile(),
		pluginManifests:   map[string]any{"plugins/grilling/.claude-plugin/plugin.json": map[string]any{"name": "grilling", "version": "0.3.0"}},
		skillLock:         skillLockFile("ui-sdk", "provable-glossary"),
		instructionHub:    "Use the `provable-glossary` skill.\n",
		instructionSpokes: map[string]any{"ROOT_AGENTS.md": "Score with the `grilling:grit-grill`\nskill.\n", "ROOT_AGENTS_docs_agents_web-ui.md": "Read the `ui-sdk` skill.\n"},
		piPackages:        []any{"npm:pi-goal-x", "git:github.com/google/elephant-goldfish-model@v0.1.1"},
		piInstaller:       "EGM_PACKAGE = \"git:github.com/google/elephant-goldfish-model\"\nEGM_SOURCE = \"git:github.com/google/elephant-goldfish-model@v0.1.1\"\n",
		egmReviewer:       egmReviewerText,
	}
}

func decl(in Inputs) map[string]any { return in[pluginsDecl].(map[string]any) }

func markets(in Inputs) map[string]any { return decl(in)["marketplaces"].(map[string]any) }

func addPlugin(in Inputs, id string) { decl(in)["plugins"] = append(decl(in)["plugins"].([]any), id) }

func TestClaudePluginsComeFromPinnedMarketplaces(t *testing.T) {
	runCases(t, claudePluginsPinned(), pluginInputs, []ruleCase{
		{"codex unpinned", func(in Inputs) { markets(in)["openai-codex"] = "openai/codex-plugin-cc" }, "openai-codex"},
		{"codex from another repository", func(in Inputs) { markets(in)["openai-codex"] = "someone/codex#v1.0.0" }, "openai/codex-plugin-cc"},
		{"codex not declared", func(in Inputs) {
			decl(in)["plugins"] = []any{"antigravity@antigravity-for-claude-code", "egm@egm", "grilling@hironow-plugins"}
		}, "codex@openai-codex"},
		{"antigravity on a branch", func(in Inputs) {
			markets(in)["antigravity-for-claude-code"] = "yuting0624/antigravity-for-claude-code#main"
		}, "antigravity-for-claude-code"},
		{"a remote marketplace on a branch", func(in Inputs) { markets(in)["egm"] = "google/elephant-goldfish-model#main" }, "egm"},
		{"the unpinned one pinned", func(in Inputs) {
			markets(in)["claude-plugins-official"] = "anthropics/claude-plugins-official#v1.0.0"
		}, "claude-plugins-official"},
		{"the unpinned exception undeclared", func(in Inputs) {
			delete(markets(in), "claude-plugins-official")
			decl(in)["plugins"] = []any{"antigravity@antigravity-for-claude-code", "codex@openai-codex", "egm@egm"}
		}, "claude-plugins-official"},
		{"a local marketplace that is not there", func(in Inputs) { markets(in)["local"] = "./elsewhere/marketplace.json" }, "elsewhere/marketplace.json"},
		{"a plugin from an undeclared marketplace", func(in Inputs) { addPlugin(in, "x@nowhere") }, "x@nowhere"},
		{"a plugin twice", func(in Inputs) { addPlugin(in, "egm@egm") }, "egm@egm"},
		{"pyright", func(in Inputs) { addPlugin(in, "pyright-lsp@claude-plugins-official") }, "pyright"},
	})
}

func TestMarketplaceEntriesMatchTheirPluginManifests(t *testing.T) {
	entry := func(in Inputs) map[string]any {
		return in[marketplacePath].(map[string]any)["plugins"].([]any)[0].(map[string]any)
	}
	runCases(t, marketplaceMatchesManifests(), pluginInputs, []ruleCase{
		{"a plugin root", func(in Inputs) { set(in[marketplacePath], "./plugins", "metadata", "pluginRoot") }, "pluginRoot"},
		{"a source with no manifest", func(in Inputs) { entry(in)["source"] = "./plugins/missing" }, "plugins/missing"},
		{"another name", func(in Inputs) { entry(in)["name"] = "grill" }, "grill"},
		{"another version", func(in Inputs) { entry(in)["version"] = "0.3.1" }, "0.3.1"},
		{"no version on one side", func(in Inputs) { delete(entry(in), "version") }, "version"},
	})
}

func TestEveryNamedSkillIsInstalled(t *testing.T) {
	runCases(t, namedSkillsDeclared(), pluginInputs, []ruleCase{
		{"a store skill not in the lock", func(in Inputs) { in[instructionHub] = "Use the `no-such` skill.\n" }, "no-such"},
		{"a plugin skill from an undeclared plugin", func(in Inputs) {
			in[instructionSpokes].(map[string]any)["ROOT_AGENTS.md"] = "Use the `nope:x` skill.\n"
		}, "nope:x"},
		{"no skill named at all", func(in Inputs) {
			in[instructionHub] = "x\n"
			in[instructionSpokes] = map[string]any{"ROOT_AGENTS.md": "y\n"}
		}, "name no skill"},
	})
}

func TestTheSkillNamePatternReadsStoreAndPluginSkills(t *testing.T) {
	var got []string
	for _, m := range namedSkill.FindAllStringSubmatch("Follow the `ui-sdk` skill, or the `grilling:grit-grill` skill.", -1) {
		got = append(got, m[1])
	}
	if want := []string{"ui-sdk", "grilling:grit-grill"}; !slices.Equal(got, want) {
		t.Fatalf("names = %v, want %v", got, want)
	}
}

func TestEGMIsOnePinnedBundleForEveryAgent(t *testing.T) {
	runCases(t, egmPinnedBundle(), pluginInputs, []ruleCase{
		{"the plugin undeclared", func(in Inputs) {
			decl(in)["plugins"] = []any{"codex@openai-codex"}
		}, "egm@egm"},
		{"no tag", func(in Inputs) { markets(in)["egm"] = "google/elephant-goldfish-model" }, "tag"},
		{"another repository", func(in Inputs) { markets(in)["egm"] = "fork/egm#v0.1.1" }, "google/elephant-goldfish-model"},
		{"pi left on the old tag", func(in Inputs) {
			in[piPackages] = []any{"git:github.com/google/elephant-goldfish-model@v0.1.0"}
		}, "pi-packages"},
		{"codex left on the old tag", func(in Inputs) {
			in[piInstaller] = strings.Replace(in[piInstaller].(string), "@v0.1.1", "@v0.1.0", 1)
		}, "EGM_SOURCE"},
		{"detached skills", func(in Inputs) {
			in[skillLock] = map[string]any{"skills": []any{map[string]any{"installed_dir": "egm", "source": "google/elephant-goldfish-model"}}}
		}, "skill-lock"},
	})
}

func TestTheEGMReviewerIsReadOnlyAndStartsFresh(t *testing.T) {
	edit := func(old, new string) func(Inputs) {
		return func(in Inputs) { in[egmReviewer] = strings.Replace(egmReviewerText, old, new, 1) }
	}
	runCases(t, piEgmReviewerReadOnly(), pluginInputs, []ruleCase{
		{"a write tool", edit("tools: read, grep, find, ls", "tools: read, grep, find, ls, write"), "tools"},
		{"an extension", edit("extensions:\n", "extensions: rtk\n"), "extensions"},
		{"project context inherited", edit("inheritProjectContext: false", "inheritProjectContext: true"), "inheritProjectContext"},
		{"system prompt appended", edit("systemPromptMode: replace", "systemPromptMode: append"), "systemPromptMode"},
		{"a forked context", edit("defaultContext: fresh", "defaultContext: fork"), "defaultContext"},
		{"a model override", edit("defaultContext: fresh\n", "defaultContext: fresh\nmodel: x\n"), "model"},
		{"no front matter", func(in Inputs) { in[egmReviewer] = "Review only.\n" }, "front matter"},
	})
}
