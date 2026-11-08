// Package project picks the directory a hook's program runs in on a harness
// that runs its hooks outside the session's directory (agy runs them where
// its hooks.json is). The shell finds the candidates, each as a real path or
// a failed lookup; this package only chooses among them. Paths are POSIX.
package project

import (
	"path"
	"strings"
)

// Candidates are what the shell found for one file. Every path is real:
// absolute, clean, and with no symlink in it.
type Candidates struct {
	File string // the file's real path
	// Workspaces are the session's workspaces, each resolved; one that did
	// not resolve is left out.
	Workspaces []string
	// GitRoot is the nearest ancestor of the file's directory that holds a
	// .git entry.
	GitRoot Lookup
}

// Lookup is the result of a lookup that can fail: what it found, if
// anything, or that it could not finish.
type Lookup struct {
	Path   string // "" when nothing was found
	Failed bool   // the lookup could not finish, so Path is not to be used
}

// Directory picks the directory for the file: the longest workspace that
// holds it, else its git root, else its own directory.
func Directory(c Candidates) string {
	best := ""
	for _, workspace := range c.Workspaces {
		if holds(workspace, c.File) && len(workspace) > len(best) {
			best = workspace
		}
	}
	switch {
	case best != "":
		return best
	case !c.GitRoot.Failed && c.GitRoot.Path != "":
		return c.GitRoot.Path
	default:
		return path.Dir(c.File)
	}
}

// holds reports whether the directory dir holds the file: the file's path
// goes on past dir with a "/". A path that only starts with the same letters
// (/ws and /ws2/a.py) is not held.
func holds(dir, file string) bool {
	rest, ok := strings.CutPrefix(file, strings.TrimSuffix(dir, "/"))
	return ok && len(rest) > 1 && rest[0] == '/'
}
