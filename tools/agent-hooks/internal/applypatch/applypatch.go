// Package applypatch reads Codex's apply_patch patches the way the shell
// guards do: the files a patch writes (for the files guard) and the lines it
// adds (for the secrets guard). Codex hands a hook the whole patch as
// tool_input.command. Text without "*** Begin Patch" is not a patch.
//
// Like the shell guards, both functions first drop NUL bytes, which bash drops
// from a command substitution.
package applypatch

import "strings"

const beginPatch = "*** Begin Patch"

const (
	addFile    = "*** Add File: "
	updateFile = "*** Update File: "
	moveTo     = "*** Move to: "
	header     = "*** "
)

// FilePaths is the files guard's reading (its awk program): each Add File
// path, and each Update File path, or, when Move to lines follow it, the last
// Move to path. Any other "*** " line ends an Update File, and a Move to with
// no path drops the file.
func FilePaths(text string) []string {
	text = strings.ReplaceAll(text, "\x00", "")
	if !strings.Contains(text, beginPatch) {
		return nil
	}
	var paths []string
	pending := ""
	flush := func() {
		if pending != "" {
			paths = append(paths, pending)
		}
		pending = ""
	}
	for line := range strings.SplitSeq(text, "\n") {
		if path, ok := strings.CutPrefix(line, addFile); ok {
			flush()
			paths = append(paths, path)
		} else if path, ok := strings.CutPrefix(line, updateFile); ok {
			flush()
			pending = path
		} else if path, ok := strings.CutPrefix(line, moveTo); ok {
			pending = path
		} else if strings.HasPrefix(line, header) {
			flush()
		}
	}
	flush()
	return paths
}

// AddedLines is the secrets guard's reading (sed 's/^+//p'): every line that
// starts with "+", without the "+", joined by newlines. Removed lines are not
// new content, so removing a leaked key stays possible.
func AddedLines(text string) string {
	text = strings.ReplaceAll(text, "\x00", "")
	if !strings.Contains(text, beginPatch) {
		return ""
	}
	var added []string
	for line := range strings.SplitSeq(text, "\n") {
		if rest, ok := strings.CutPrefix(line, "+"); ok {
			added = append(added, rest)
		}
	}
	return strings.Join(added, "\n")
}
