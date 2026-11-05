package registration

import (
	"errors"
	"regexp"
	"strings"
)

// ownedPath is sync's _AGENT_HOOK_PATH (scripts/sync_agents.py): a release, or
// a home's stable link, below a dotfiles/ directory named by whole segments.
// Both must accept exactly the same paths; the render corpus holds them to it.
const ownedPath = `/(?:[^/]+/)*dotfiles/agent-hooks/(?:releases/[0-9a-f]{12,}|current/[a-z0-9-]+)/agent-hook`

var (
	drivePath     = regexp.MustCompile(`^[A-Za-z]:[/\\]`)
	posixLayout   = regexp.MustCompile(`^` + ownedPath + `$`)
	windowsLayout = regexp.MustCompile(`^[A-Za-z]:` + ownedPath + `\.exe$`)
)

func checkPath(binary, os, shell string) error {
	for _, char := range binary {
		if char <= 0x1f || char == 0x7f {
			return errors.New("binary path contains a control character")
		}
	}
	path, layout := binary, posixLayout
	if os == "windows" {
		if !drivePath.MatchString(path) {
			return errors.New("windows binary path must be absolute with a drive letter; UNC paths are refused")
		}
		if !strings.HasSuffix(path, ".exe") {
			return errors.New("windows binary path must end in .exe")
		}
		// A Windows path reads `\` as `/`; on POSIX `\` is a filename character.
		path, layout = strings.ReplaceAll(path, `\`, "/"), windowsLayout
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
		return errors.New("binary path must use dotfiles/agent-hooks/releases/<12+ lowercase hex>/agent-hook or current/<home>/agent-hook (suffix by OS)")
	}
	return nil
}
