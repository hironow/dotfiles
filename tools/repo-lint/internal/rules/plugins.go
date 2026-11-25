package rules

import (
	"maps"
	"path"
	"reflect"
	"regexp"
	"slices"
	"strings"
)

const (
	pluginsDecl       = "dump/harness/claude-plugins.json"
	skillLock         = "dump/harness/skill-lock.json"
	piPackages        = "dump/harness/pi-packages.json"
	marketplacePath   = ".claude-plugin/marketplace.json"
	localMarketplaces = "**/.claude-plugin/marketplace.json"
	pluginManifests   = "**/.claude-plugin/plugin.json"
	instructionHub    = "ROOT_CLAUDE.md"
	instructionSpokes = "ROOT_AGENTS*.md"
	piInstaller       = "scripts/install_pi_extensions.py"
	egmReviewer       = "config/pi/agents/egm-reviewer.md"
	egmRepo           = "google/elephant-goldfish-model"
)

var (
	// releaseTag is the ref of a pinned marketplace: a release tag
	// (v1.0.6), as claude_plugins.py reads it.
	releaseTag = regexp.MustCompile(`^v?\d+\.\d+\.\d+$`)
	// namedSkill is how the instructions name a skill: the `x` skill, or the
	// `plugin:x` skill.
	namedSkill = regexp.MustCompile("\\bthe `([a-z0-9][a-z0-9:-]*)` skill\\b")
	// egmPackageAssign and egmSourceAssign are a line, at any indentation,
	// that assigns the name: plain, annotated or augmented, never `==`.
	egmPackageAssign = regexp.MustCompile(`(?m)^[ \t]*EGM_PACKAGE\b[^=\n]*=(?:[^=\n].*)?$`)
	egmSourceAssign  = regexp.MustCompile(`(?m)^[ \t]*EGM_SOURCE\b[^=\n]*=(?:[^=\n].*)?$`)
	// stringConstant is a module-level assignment of a string literal, with
	// an optional type annotation and trailing comment.
	stringConstant = regexp.MustCompile(`^\w+\s*(?::\s*\w+\s*)?=\s*"([^"\\]*)"\s*(?:#.*)?$`)
)

// unpinnedMarketplaces publish no tags, so they are declared without a ref
// (ADR 0056): the CLI clones `--branch <ref>` and cannot take a commit SHA. A
// `./` source is this repository's own tracked content.
var unpinnedMarketplaces = []string{"claude-plugins-official"}

// pinnedPlugins are the plugins every home declares, each from its own
// repository pinned to a v tag (the antigravity one: ADR 0082).
var pinnedPlugins = []struct{ id, repo string }{
	{"codex@openai-codex", "openai/codex-plugin-cc"},
	{"antigravity@antigravity-for-claude-code", "yuting0624/antigravity-for-claude-code"},
}

// claudePluginsPinned: a plugin comes from a declared marketplace, and a remote
// marketplace is pinned to a release tag, except the ones that publish none. A
// stale exception would let a later marketplace of that name go unpinned.
func claudePluginsPinned() Rule {
	const id = "claude-plugins-pinned"
	return Rule{
		ID:     id,
		Why:    "every declared plugin comes from a declared marketplace, and every remote marketplace is pinned to a release tag",
		Inputs: []Input{{Path: pluginsDecl, Format: JSON}, {Path: localMarketplaces, Format: JSON, Glob: true}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: pluginsDecl}
			markets, _ := table(in[pluginsDecl], "marketplaces")
			local, _ := in[localMarketplaces].(map[string]any)
			for _, name := range slices.Sorted(maps.Keys(markets)) {
				source, _ := markets[name].(string)
				if rel, isLocal := strings.CutPrefix(source, "./"); isLocal {
					if _, ok := local[rel]; !ok {
						r.add("the local marketplace %s is not a tracked .claude-plugin/marketplace.json: %s", name, source)
					}
					continue
				}
				_, ref, _ := strings.Cut(source, "#")
				switch {
				case slices.Contains(unpinnedMarketplaces, name) && ref != "":
					r.add("marketplace %s publishes no tags and stays unpinned, not %q", name, source)
				case !slices.Contains(unpinnedMarketplaces, name) && !releaseTag.MatchString(ref):
					r.add("pin marketplace %s to a release tag, not %q", name, source)
				}
			}
			for _, name := range unpinnedMarketplaces {
				if _, ok := markets[name]; !ok {
					r.add("the unpinned exception names %s, which is not declared; drop it so a later marketplace of that name is pinned", name)
				}
			}
			plugins := strs(in[pluginsDecl], "plugins")
			seen := map[string]bool{}
			for _, plugin := range plugins {
				if seen[plugin] {
					r.add("plugin %s is declared twice", plugin)
				}
				seen[plugin] = true
				if _, market, _ := strings.Cut(plugin, "@"); markets[market] == nil {
					r.add("plugin %s comes from an undeclared marketplace", plugin)
				}
				if strings.Contains(plugin, "pyright") {
					r.add("plugin %s: ty is the only Python type checker (ADR 0044)", plugin)
				}
			}
			for _, p := range pinnedPlugins {
				if !seen[p.id] {
					r.add("declare %s", p.id)
				}
				_, market, _ := strings.Cut(p.id, "@")
				source, _ := markets[market].(string)
				if repo, ref, _ := strings.Cut(source, "#"); repo != p.repo || !strings.HasPrefix(ref, "v") {
					r.add("marketplace %s must be %s pinned to a v tag, not %q", market, p.repo, source)
				}
			}
			return r.out
		},
	}
}

// marketplaceMatchesManifests: Claude Code's plugin resolver reads this
// repository's marketplace as a local file. Each entry points at a plugin
// directory with a manifest of the same name and version (a version drift
// between the two files once broke silently), through an explicit ./ path;
// metadata.pluginRoot is prepended to relative sources and would prefix them
// twice.
func marketplaceMatchesManifests() Rule {
	const id = "claude-marketplace-matches-plugin-manifests"
	return Rule{
		ID:     id,
		Why:    "each marketplace entry resolves to a plugin manifest with the same name and version, through one path mechanism",
		Inputs: []Input{{Path: marketplacePath, Format: JSON}, {Path: pluginManifests, Format: JSON, Glob: true}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: marketplacePath}
			if _, ok := at(in[marketplacePath], "metadata", "pluginRoot"); ok {
				r.add("metadata.pluginRoot is prepended to relative plugin sources; keep only explicit ./ path sources")
			}
			manifests, _ := in[pluginManifests].(map[string]any)
			items, _ := at(in[marketplacePath], "plugins")
			list, _ := items.([]any)
			for _, item := range list {
				entry, isObject := item.(map[string]any)
				if !isObject {
					r.add("a plugins entry is not an object: %v", item)
					continue
				}
				name, named := str(entry, "name")
				source, _ := str(entry, "source")
				if !named {
					r.add("the entry for %s has no name", source)
				}
				manifest, ok := manifests[path.Join(strings.TrimPrefix(source, "./"), ".claude-plugin/plugin.json")]
				if !ok {
					r.add("%s: %s has no .claude-plugin/plugin.json", name, source)
					continue
				}
				if got, ok := str(manifest, "name"); !ok || got != name {
					r.add("%s: its plugin.json names it %q", name, got)
				}
				want, _ := at(entry, "version")
				if got, _ := at(manifest, "version"); !reflect.DeepEqual(got, want) {
					r.add("%s: marketplace version %v, plugin.json version %v; bump both together", name, want, got)
				}
			}
			return r.out
		},
	}
}

// namedSkillsDeclared: the hub and spokes send agents to skills by name, and a
// name no declaration installs works only on the machine where someone added it
// by hand. A store skill is in skill-lock.json (ADR 0043); a plugin skill,
// written `plugin:skill`, comes from a plugin in claude-plugins.json.
func namedSkillsDeclared() Rule {
	const id = "named-skills-installed"
	return Rule{
		ID:  id,
		Why: "every skill the instructions name by name is declared, as a store skill or a declared plugin's",
		Inputs: []Input{
			{Path: instructionHub, Format: Text},
			{Path: instructionSpokes, Format: Text, Glob: true},
			{Path: skillLock, Format: JSON},
			{Path: pluginsDecl, Format: JSON},
		},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: instructionHub}
			sources := map[string]string{}
			if hub, ok := in[instructionHub].(string); ok {
				sources[instructionHub] = hub
			}
			spokes, _ := in[instructionSpokes].(map[string]any)
			for p, text := range spokes {
				sources[p], _ = text.(string)
			}
			store := map[string]bool{}
			for _, skill := range tables(in[skillLock], "skills") {
				if dir, ok := str(skill, "installed_dir"); ok {
					store[dir] = true
				}
			}
			plugins := map[string]bool{}
			for _, plugin := range strs(in[pluginsDecl], "plugins") {
				name, _, _ := strings.Cut(plugin, "@")
				plugins[name] = true
			}
			named := 0
			for _, p := range slices.Sorted(maps.Keys(sources)) {
				for _, m := range namedSkill.FindAllStringSubmatch(strings.Join(strings.Fields(sources[p]), " "), -1) {
					named++
					skill := m[1]
					if plugin, _, isPlugin := strings.Cut(skill, ":"); isPlugin {
						if !plugins[plugin] {
							r.addAt(p, "the `%s` skill is named, but the plugin %s is not declared", skill, plugin)
						}
					} else if !store[skill] {
						r.addAt(p, "the `%s` skill is named, but dump/harness/skill-lock.json does not declare it", skill)
					}
				}
			}
			if named == 0 {
				r.add("the instructions name no skill; the pattern or the sources changed")
			}
			return r.out
		},
	}
}

// egmPinnedBundle: EGM reaches Claude, Pi and Codex as one bundle at one tag.
// `just agent-bump egm` moves the pins together, and Codex takes its ref from
// EGM_SOURCE; a pin left behind would split the agents.
func egmPinnedBundle() Rule {
	const id = "egm-one-pinned-bundle"
	return Rule{
		ID:  id,
		Why: "EGM is one pinned bundle at one tag for Claude, Pi and Codex, never detached skills",
		Inputs: []Input{
			{Path: pluginsDecl, Format: JSON},
			{Path: piPackages, Format: JSON},
			{Path: skillLock, Format: JSON},
			{Path: piInstaller, Format: Text},
		},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: pluginsDecl}
			if !slices.Contains(strs(in[pluginsDecl], "plugins"), "egm@egm") {
				r.add("declare egm@egm: EGM ships as one pinned bundle")
			}
			for _, skill := range tables(in[skillLock], "skills") {
				if source, _ := str(skill, "source"); source == egmRepo {
					dir, _ := str(skill, "installed_dir")
					r.addAt(skillLock, "skill-lock.json takes %s from %s; EGM comes as the pinned bundle, not as detached skills", dir, egmRepo)
				}
			}
			source, _ := str(in[pluginsDecl], "marketplaces", "egm")
			repo, tag, _ := strings.Cut(source, "#")
			if repo != egmRepo {
				r.add("marketplace egm must be %s, not %q", egmRepo, source)
			}
			if tag == "" {
				r.add("pin marketplace egm to a tag; every other EGM pin follows it")
				return r.out
			}
			if want := "git:github.com/" + egmRepo + "@" + tag; !slices.Contains(strs(in[piPackages]), want) {
				r.addAt(piPackages, "pi-packages.json must pin %s, the tag of the Claude marketplace", want)
			}
			text, _ := in[piInstaller].(string)
			pkg, pkgOK := onlyConstant(egmPackageAssign, text)
			src, srcOK := onlyConstant(egmSourceAssign, text)
			switch {
			case !pkgOK || !srcOK:
				r.addAt(piInstaller, "EGM_PACKAGE and EGM_SOURCE must each be assigned once, at module level, to a string constant")
			case src != pkg+"@"+tag:
				r.addAt(piInstaller, "EGM_SOURCE %q must be %s@%s, the tag of the Claude marketplace", src, pkg, tag)
			}
			return r.out
		},
	}
}

// onlyConstant is the string a module holds once imported when the name is
// assigned exactly once, at module level, to a string constant. Any other
// shape (a second assignment, one inside a block, an expression) is false, so
// a value this rule cannot read never passes. Rebinding the name another way
// (an import, globals()) is not read.
func onlyConstant(assign *regexp.Regexp, text string) (string, bool) {
	all := assign.FindAllString(text, -1)
	if len(all) != 1 || all[0][0] == ' ' || all[0][0] == '\t' {
		return "", false
	}
	m := stringConstant.FindStringSubmatch(all[0])
	if m == nil {
		return "", false
	}
	return m[1], true
}

// piEgmReviewerReadOnly: the Pi EGM reviewer reads only what it is given: it has
// read-only tools and no extensions, inherits no context or skills, replaces
// the system prompt, starts fresh, and keeps the route's model.
func piEgmReviewerReadOnly() Rule {
	const id = "pi-egm-reviewer-read-only"
	return Rule{
		ID:     id,
		Why:    "the Pi EGM reviewer is read-only, starts fresh, inherits nothing and keeps the route's model",
		Inputs: []Input{{Path: egmReviewer, Format: Text}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: egmReviewer}
			text, _ := in[egmReviewer].(string)
			parts := strings.SplitN(text, "---", 3)
			if len(parts) < 3 {
				r.add("egm-reviewer.md has no front matter")
				return r.out
			}
			// Only a line that starts at the first column is a key of its own;
			// an indented line belongs to the value above it.
			front := map[string]string{}
			for line := range strings.SplitSeq(parts[1], "\n") {
				if line == "" || line[0] == ' ' || line[0] == '\t' {
					continue
				}
				if k, v, ok := strings.Cut(line, ":"); ok {
					front[strings.TrimSpace(k)] = strings.TrimSpace(v)
				}
			}
			tools := strings.Split(front["tools"], ",")
			for i := range tools {
				tools[i] = strings.TrimSpace(tools[i])
			}
			if !sameSet(tools, []string{"read", "grep", "find", "ls"}) {
				r.add("tools must be read, grep, find, ls, not %q", front["tools"])
			}
			for _, want := range []struct{ key, value string }{
				{"extensions", ""},
				{"inheritProjectContext", "false"},
				{"inheritGlobalContext", "false"},
				{"inheritSkills", "false"},
				{"systemPromptMode", "replace"},
				{"defaultContext", "fresh"},
			} {
				if got, ok := front[want.key]; !ok || got != want.value {
					r.add("%s must be %q, not %q", want.key, want.value, got)
				}
			}
			for _, key := range []string{"model", "thinking", "memory", "allowNestedSubagents"} {
				if _, ok := front[key]; ok {
					r.add("remove %s: the reviewer keeps the route's settings", key)
				}
			}
			return r.out
		},
	}
}
