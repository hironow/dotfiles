package registration

import (
	"errors"
	"regexp"
	"slices"
	"strings"
)

// ownedPath is sync's _STABLE_PATH and _AGENT_HOOK_PATH
// (scripts/sync_agents.py), by the registration's layouts: a home's stable
// link, or a release, below a dotfiles/ directory named by whole segments.
// Both sides must accept exactly the same paths; the render corpus holds
// them to it.
func ownedPath(layouts []string) string {
	var alternatives []string
	for _, layout := range layouts {
		switch layout {
		case "stable":
			alternatives = append(alternatives, `current/[a-z0-9-]+`)
		case "release":
			alternatives = append(alternatives, `releases/[0-9a-f]{12,}`)
		}
	}
	return `/(?:[^/]+/)*dotfiles/agent-hooks/(?:` + strings.Join(alternatives, "|") + `)/agent-hook`
}

var drivePath = regexp.MustCompile(`^[A-Za-z]:[/\\]`)

func checkPath(binary, os, shell string, layouts []string) error {
	for _, char := range binary {
		if char <= 0x1f || char == 0x7f {
			return errors.New("binary path contains a control character")
		}
	}
	owned := ownedPath(layouts)
	path, layout := binary, regexp.MustCompile(`^`+owned+`$`)
	if os == "windows" {
		if !drivePath.MatchString(path) {
			return errors.New("windows binary path must be absolute with a drive letter; UNC paths are refused")
		}
		if !strings.HasSuffix(path, ".exe") {
			return errors.New("windows binary path must end in .exe")
		}
		// A Windows path reads `\` as `/`; on POSIX `\` is a filename character.
		path, layout = strings.ReplaceAll(path, `\`, "/"), regexp.MustCompile(`^[A-Za-z]:`+owned+`\.exe$`)
	} else {
		if !strings.HasPrefix(path, "/") {
			return errors.New("POSIX binary path must be absolute")
		}
		if strings.HasSuffix(path, ".exe") {
			return errors.New("POSIX binary path must not end in .exe")
		}
	}
	switch shell {
	case "exec":
		if strings.Contains(binary, "${") {
			return errors.New("exec binary path contains a Claude placeholder (${)")
		}
	case "cmd":
		if strings.ContainsAny(binary, "%!\"") {
			return errors.New("cmd binary path contains %, !, or a double quote")
		}
	case "powershell":
		if strings.ContainsAny(binary, "‘’‚‛*?[]") {
			return errors.New("PowerShell binary path contains a smart quote or wildcard")
		}
	}
	if !layout.MatchString(path) {
		if slices.Contains(layouts, "release") {
			return errors.New("binary path must use dotfiles/agent-hooks/releases/<12+ lowercase hex>/agent-hook or current/<home>/agent-hook (suffix by OS)")
		}
		return errors.New("binary path must use dotfiles/agent-hooks/current/<home>/agent-hook (suffix by OS), the home's stable link")
	}
	return nil
}
