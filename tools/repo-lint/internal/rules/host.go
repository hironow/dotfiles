package rules

import (
	"regexp"
	"slices"
	"strings"
)

const (
	codexAgyScript    = "scripts/codex_agy_plugins.py"
	repoClaudeMd      = "CLAUDE.md"
	repoAgentsMd      = "AGENTS.md"
	wslConf           = "config/wsl/wsl.conf"
	wslconfigTemplate = "config/wsl/wslconfig"
	antigravityTool   = "github:google-antigravity/antigravity-cli"
)

var (
	antigravityNames = regexp.MustCompile(`(?m)^ANTIGRAVITY_NAMES = \(\s*"([^"]+)"`)
	justFmtLine      = regexp.MustCompile(`(?m)^JUST_FMT := "([^"]*)"$`)
)

// codexAgyNamesFollowMise: deploy looks for the Antigravity CLI by the name
// mise installs it as. #604 looked only for `agy` while mise named the
// executable `antigravity`, so deploy skipped Antigravity on every machine
// without saying so.
func codexAgyNamesFollowMise() Rule {
	const id = "codex-agy-names-follow-mise"
	return Rule{
		ID:     id,
		Why:    "deploy searches first for the executable name mise gives the Antigravity CLI (#604)",
		Inputs: []Input{{Path: codexAgyScript, Format: Text}, {Path: hostConfig, Format: TOML}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: codexAgyScript}
			text, _ := in[codexAgyScript].(string)
			m := antigravityNames.FindStringSubmatch(text)
			if m == nil {
				r.add("ANTIGRAVITY_NAMES must be a tuple of strings")
				return r.out
			}
			exe, ok := str(in[hostConfig], "tools", antigravityTool, "rename_exe")
			if !ok {
				r.addAt(hostConfig, "[tools] must declare %s with rename_exe", antigravityTool)
				return r.out
			}
			if m[1] != exe {
				r.add("ANTIGRAVITY_NAMES starts with %q, but mise installs the CLI as %q", m[1], exe)
			}
			return r.out
		},
	}
}

// justFmtPinned: `just fmt` and the gate's format check run the just the image
// pins, so a local format and CI's check agree on one formatter.
func justFmtPinned() Rule {
	const id = "just-fmt-pinned"
	return Rule{
		ID:     id,
		Why:    "JUST_FMT runs the just version config/mise/image-tools.toml pins",
		Inputs: []Input{{Path: justfilePath, Format: Text}, {Path: imageConfig, Format: TOML}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: justfilePath}
			text, _ := in[justfilePath].(string)
			pinned, _ := str(in[imageConfig], "tools", "just")
			want := "mise x just@" + pinned + " -- just"
			m := justFmtLine.FindStringSubmatch(text)
			switch {
			case m == nil:
				r.add("the justfile must declare JUST_FMT := %q", want)
			case m[1] != want:
				r.add("JUST_FMT is %q; it must be %q, the pinned just", m[1], want)
			}
			return r.out
		},
	}
}

// repoClaudeMdImportsAgents: Claude Code reads CLAUDE.md, and the repository's
// rules live in AGENTS.md, which CLAUDE.md imports on a line of its own.
func repoClaudeMdImportsAgents() Rule {
	const id = "repo-claude-md-imports-agents"
	return Rule{
		ID:     id,
		Why:    "CLAUDE.md imports AGENTS.md, where this repository's rules live",
		Inputs: []Input{{Path: repoClaudeMd, Format: Text}, {Path: repoAgentsMd, Format: Text}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: repoClaudeMd}
			text, _ := in[repoClaudeMd].(string)
			if !slices.Contains(strings.Split(text, "\n"), "@AGENTS.md") {
				r.add("CLAUDE.md must import the repository rules with a line `@AGENTS.md`")
			}
			return r.out
		},
	}
}

// iniKeys is each active `key=value` of an INI file, by key; a commented line
// is not active.
func iniKeys(text string) map[string]string {
	out := map[string]string{}
	for line := range strings.SplitSeq(text, "\n") {
		line = strings.TrimSpace(line)
		if line == "" || line[0] == '#' || line[0] == ';' || line[0] == '[' {
			continue
		}
		if k, v, ok := strings.Cut(line, "="); ok {
			out[strings.TrimSpace(k)] = strings.TrimSpace(v)
		}
	}
	return out
}

// wslConfHardens: the distro template keeps the Windows PATH out of Linux and
// keeps systemd on for the native Podman service.
func wslConfHardens() Rule {
	const id = "wsl-conf-hardens"
	return Rule{
		ID:     id,
		Why:    "the WSL distro template sets appendWindowsPath=false (no Windows PATH leak) and systemd=true",
		Inputs: []Input{{Path: wslConf, Format: Text}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: wslConf}
			text, _ := in[wslConf].(string)
			keys := iniKeys(text)
			if keys["appendWindowsPath"] != "false" {
				r.add("set appendWindowsPath=false: the Windows PATH must not leak into the distro")
			}
			if keys["systemd"] != "true" {
				r.add("set systemd=true: native Podman and the services need a service manager")
			}
			return r.out
		},
	}
}

// wslconfigRejected are keys the shared Windows template never sets:
// sparseVhd (this repository does not turn sparse on, ADR 0035), vmIdleTimeout
// (tested live: it does not govern distro lifetime), per-machine limits, and
// the networking keys that are an explicit local opt-in.
var wslconfigRejected = []string{
	"sparseVhd", "vmIdleTimeout", "memory", "processors", "networkingMode", "dnsTunneling", "autoProxy",
}

// wslconfigSafeSubset: the shared .wslconfig template carries only the safe
// subset every machine can take.
func wslconfigSafeSubset() Rule {
	const id = "wslconfig-template-safe-subset"
	return Rule{
		ID:     id,
		Why:    "the shared .wslconfig template sets autoMemoryReclaim=gradual and none of the rejected or per-machine keys",
		Inputs: []Input{{Path: wslconfigTemplate, Format: Text}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: wslconfigTemplate}
			text, _ := in[wslconfigTemplate].(string)
			keys := iniKeys(text)
			if keys["autoMemoryReclaim"] != "gradual" {
				r.add("set autoMemoryReclaim=gradual")
			}
			for _, k := range wslconfigRejected {
				if _, ok := keys[k]; ok {
					r.add("%s must not be set in the shared template; it is rejected or a per-machine opt-in", k)
				}
			}
			return r.out
		},
	}
}
