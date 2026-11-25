package rules

import (
	"fmt"
	"maps"
	"regexp"
	"slices"
	"strings"
	"unicode/utf8"
)

const (
	claudeShared     = ".claude/settings.shared.json"
	claudeProject    = ".claude/settings.json"
	settingsShared   = ".claude/settings.shared*.json"
	settingsProfiles = ".claude/settings.profiles/*.json"
	gitmodules       = ".gitmodules"
)

// instructionGlobs are the files Claude Code loads as instructions.
var instructionGlobs = []string{"**/CLAUDE.md", "**/CLAUDE.local.md", "**/AGENTS.md", "**/GEMINI.md", "**/.claude/rules/**"}

var submodulePath = regexp.MustCompile(`(?m)^\s*path\s*=\s*(\S+)\s*$`)

// agentTelemetryOff are the switches that keep rtk and headroom silent in
// every Claude session and hook.
var agentTelemetryOff = map[string]string{
	"RTK_TELEMETRY_DISABLED": "1",
	"HEADROOM_BEACON":        "off",
	"DO_NOT_TRACK":           "1",
}

// pluginTelemetryOff are the declared plugins that send telemetry by default,
// and the switches that turn it off. The vercel plugin's SessionStart and
// PostToolUse hooks POST to telemetry.vercel.com unless
// VERCEL_PLUGIN_TELEMETRY=off (vercel/vercel-plugin hooks/src/telemetry.mts,
// getTelemetryOverride); it does not read DO_NOT_TRACK. The shared env reaches
// Claude Code and every hook a plugin runs, wherever a session starts.
var pluginTelemetryOff = map[string]map[string]string{
	"vercel@claude-plugins-official": {"VERCEL_PLUGIN_TELEMETRY": "off"},
}

// claudeTelemetryOff: the shared Claude settings turn off the telemetry of the
// agent tools and of the plugins that send it by default.
func claudeTelemetryOff() Rule {
	const id = "claude-telemetry-off"
	return Rule{
		ID:     id,
		Why:    "every Claude session and hook runs with the telemetry of rtk, headroom and the declared plugins off",
		Inputs: []Input{{Path: claudeShared, Format: JSON}, {Path: pluginsDecl, Format: JSON}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: claudeShared}
			env, _ := table(in[claudeShared], "env")
			for _, name := range slices.Sorted(maps.Keys(agentTelemetryOff)) {
				if want := agentTelemetryOff[name]; env[name] != want {
					r.add("env %s must be %q: rtk and headroom send nothing from a Claude session or hook", name, want)
				}
			}
			plugins := strs(in[pluginsDecl], "plugins")
			for _, plugin := range slices.Sorted(maps.Keys(pluginTelemetryOff)) {
				if !slices.Contains(plugins, plugin) {
					r.addAt(pluginsDecl, "%s is no longer declared; drop it from this rule's telemetry switches", plugin)
				}
				switches := pluginTelemetryOff[plugin]
				for _, name := range slices.Sorted(maps.Keys(switches)) {
					if want := switches[name]; env[name] != want {
						r.add("env %s must be %q: %s sends telemetry by default", name, want, plugin)
					}
				}
			}
			return r.out
		},
	}
}

// claudeGlob is a claudeMdExcludes pattern as Claude applies it to an
// absolute path: `**` spans directories and `*` stays within one.
func claudeGlob(pattern string) *regexp.Regexp {
	var b strings.Builder
	b.WriteString(`\A`)
	for i := 0; i < len(pattern); {
		switch {
		case strings.HasPrefix(pattern[i:], "**/"):
			b.WriteString(`(?:.*/)?`)
			i += 3
		case strings.HasPrefix(pattern[i:], "**"):
			b.WriteString(`.*`)
			i += 2
		case pattern[i] == '*':
			b.WriteString(`[^/]*`)
			i++
		default:
			_, size := utf8.DecodeRuneInString(pattern[i:])
			b.WriteString(regexp.QuoteMeta(pattern[i : i+size]))
			i += size
		}
	}
	b.WriteString(`\z`)
	return regexp.MustCompile(b.String())
}

// claudeMdExcludes: Claude loads a subdirectory's CLAUDE.md (and AGENTS.md) as
// soon as it reads a file there. The submodules are other projects, and their
// instruction files are data, not instructions, so claudeMdExcludes covers
// every one; it never hides an instruction file this repository tracks.
func claudeMdExcludes() Rule {
	const id = "claude-md-excludes-third-party-only"
	inputs := []Input{{Path: gitmodules, Format: Text}, {Path: claudeProject, Format: JSON}}
	for _, glob := range instructionGlobs {
		inputs = append(inputs, Input{Path: glob, Format: Text, Glob: true})
	}
	return Rule{
		ID:     id,
		Why:    "claudeMdExcludes hides the instruction files of every submodule and none that this repository tracks",
		Inputs: inputs,
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: claudeProject}
			var patterns []*regexp.Regexp
			for _, p := range strs(in[claudeProject], "claudeMdExcludes") {
				patterns = append(patterns, claudeGlob(p))
			}
			excluded := func(repoPath string) bool {
				absolute := "/checkout/dotfiles/" + repoPath
				return slices.ContainsFunc(patterns, func(re *regexp.Regexp) bool { return re.MatchString(absolute) })
			}
			text, _ := in[gitmodules].(string)
			submodules := submodulePath.FindAllStringSubmatch(text, -1)
			if len(submodules) == 0 {
				r.addAt(gitmodules, ".gitmodules lists no submodule")
			}
			for _, m := range submodules {
				if !excluded(m[1] + "/CLAUDE.md") {
					r.add("add a claudeMdExcludes pattern for the submodule %s: its instruction files are data, not instructions", m[1])
				}
			}
			tracked := map[string]bool{}
			for _, glob := range instructionGlobs {
				files, _ := in[glob].(map[string]any)
				for p := range files {
					tracked[p] = true
				}
			}
			if !tracked["CLAUDE.md"] {
				r.add("expected the repository's own CLAUDE.md among the tracked instruction files")
			}
			for _, p := range slices.Sorted(maps.Keys(tracked)) {
				if excluded(p) {
					r.add("claudeMdExcludes hides %s, an instruction file this repository tracks", p)
				}
			}
			return r.out
		},
	}
}

// fragments is every settings fragment of the two glob inputs, by path.
func fragments(in Inputs) map[string]any {
	out := map[string]any{}
	for _, glob := range []string{settingsShared, settingsProfiles} {
		files, _ := in[glob].(map[string]any)
		maps.Copy(out, files)
	}
	return out
}

// settingsLeavePluginKeys: the plugin CLI owns enabledPlugins and
// extraKnownMarketplaces (ADR 0037, ADR 0048); a fragment that set them would
// replace what claude_plugins.py installed on every sync.
func settingsLeavePluginKeys() Rule {
	const id = "claude-settings-leave-plugins-to-the-cli"
	return Rule{
		ID:     id,
		Why:    "no settings fragment sets enabledPlugins or extraKnownMarketplaces; the plugin CLI owns them (ADR 0037, ADR 0048)",
		Inputs: []Input{{Path: settingsShared, Format: JSON, Glob: true}, {Path: settingsProfiles, Format: JSON, Glob: true}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id}
			all := fragments(in)
			for _, p := range slices.Sorted(maps.Keys(all)) {
				inner, _ := table(all[p], "settings")
				for _, section := range []any{all[p], inner} {
					for _, key := range []string{"enabledPlugins", "extraKnownMarketplaces"} {
						if _, ok := at(section, key); ok {
							r.addAt(p, "%s belongs to the plugin CLI; a fragment that sets it replaces what claude_plugins.py installed", key)
						}
					}
				}
			}
			return r.out
		},
	}
}

// overrideNames is the skill names a skillOverrides value lists: a map's keys,
// or a list's items.
func overrideNames(v any) []string {
	switch overrides := v.(type) {
	case map[string]any:
		return slices.Sorted(maps.Keys(overrides))
	case []any:
		names := make([]string, 0, len(overrides))
		for _, item := range overrides {
			names = append(names, fmt.Sprint(item))
		}
		return names
	}
	return nil
}

// skillOverrides: every skill is Claude Code's default "on". The shared layer
// keeps an explicit {}, because sync only adds or updates top-level keys and
// removing it would leave each home's old map in place. A skill dropped from
// skill-lock.json leaves the stores, so an override naming it tunes nothing;
// plugin skills (`plugin:skill`) come from marketplaces this repository does
// not pin, so only bare names are checked.
func skillOverrides() Rule {
	const id = "claude-skill-overrides-cleared"
	return Rule{
		ID:  id,
		Why: "the shared layer clears skillOverrides with an explicit {}, no other layer adds one, and every bare override names a declared skill",
		Inputs: []Input{
			{Path: settingsShared, Format: JSON, Glob: true},
			{Path: settingsProfiles, Format: JSON, Glob: true},
			{Path: skillLock, Format: JSON},
		},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id}
			declared := map[string]bool{}
			for _, skill := range tables(in[skillLock], "skills") {
				if dir, ok := str(skill, "installed_dir"); ok {
					declared[dir] = true
				}
			}
			all := fragments(in)
			if shared, ok := table(all[claudeShared], "settings", "skillOverrides"); !ok || len(shared) != 0 {
				r.addAt(claudeShared, "settings.skillOverrides must be an explicit {}, so sync clears each home's old overrides")
			}
			for _, p := range slices.Sorted(maps.Keys(all)) {
				raw, set := at(all[p], "settings", "skillOverrides")
				if empty, isMap := raw.(map[string]any); p != claudeShared && set && (!isMap || len(empty) > 0) {
					r.addAt(p, "%s sets skillOverrides; only the shared layer holds them, and it holds none", p)
				}
				for _, name := range overrideNames(raw) {
					if !strings.Contains(name, ":") && !declared[name] {
						r.addAt(p, "skillOverrides names %s, which dump/harness/skill-lock.json does not declare", name)
					}
				}
			}
			return r.out
		},
	}
}
