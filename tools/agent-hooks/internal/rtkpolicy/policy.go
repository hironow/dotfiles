// Package rtkpolicy decides what the rtk hook prints of rtk's own hook
// answer, the way the old scripts decide it: Claude's
// (ROOT_AGENTS_hooks_rtk-hook-claude.py) and Codex's
// (ROOT_AGENTS_hooks_rtk-hook-codex.py). On Claude and Codex the hook is a
// delegate: rtk's adapter for the harness reads the native payload and writes
// the native answer, and this package edits that answer exactly as the
// scripts do, never reinterpreting it. It is pure: rtk's answer and the facts
// the shell found go in, and the answer to print, or nothing, comes out.
//
// rtk decides which commands it rewrites, and stays the single source of
// truth for that: the hook only reads rtk's rewritten command.
//
// Answers are edited at the JSON-value level: every value the hook does not
// touch keeps its text.
package rtkpolicy

import (
	"errors"
	"strconv"
	"strings"

	"github.com/goccy/go-json/jsontext"
	json "github.com/goccy/go-json/v2"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/pyshlex"
)

const (
	launcher       = "rtk"
	vetoedCommand  = "git"
	worktreeMarker = "/.claude/worktrees/"
)

// object is one JSON object of an answer, its members as written.
type object map[string]jsontext.Value

// Claude returns what the Claude hook prints for rtk's answer to `rtk hook
// claude`, or ok=false to print nothing.
//
// cwd is the tool call's working directory (VetoCwd). miseLauncher is the
// rtk that mise found when PATH had none (AsPosix of mise's answer, or
// AsPosixWindows on Windows), else "".
// In order: the worktree git veto, mise's launcher, then the strip (ADR
// 0047): only rtk's hookEventName ("PreToolUse" when absent) and updatedInput
// are printed, so no permission decision of rtk's reaches Claude Code. An
// updatedInput without a string command is printed as it is, as the script
// does.
func Claude(answer jsontext.Value, cwd, miseLauncher string) (jsontext.Value, bool) {
	root, ok := objectOf(answer)
	if !ok {
		return nil, false
	}
	output, ok := objectOf(root["hookSpecificOutput"])
	if !ok {
		return nil, false
	}
	updatedValue, hasUpdated := output["updatedInput"]
	updated, updatedIsObject := objectOf(updatedValue)
	command, isRewrite := "", false
	if updatedIsObject {
		command, isRewrite = stringOf(updated["command"])
	}
	if isRewrite && inIsolationWorktree(cwd) && isVetoedRewrite(command) {
		return nil, false // the plain command runs
	}
	if miseLauncher != "" && isRewrite {
		rest, ok := plainRewrite(command)
		if !ok {
			return nil, false // the typed command runs
		}
		updated["command"] = stringValue(Quote(miseLauncher) + rest)
	}
	if !hasUpdated || !updatedIsObject {
		return nil, false
	}
	event, ok := output["hookEventName"]
	if !ok {
		event = stringValue("PreToolUse")
	}
	return marshal(object{"hookSpecificOutput": mustMarshal(object{"hookEventName": event, "updatedInput": mustMarshal(updated)})})
}

// Codex returns rtk's answer to `rtk hook codex` with the rewrite naming
// launcher, rtk's real binary (CodexLauncher), or ok=false to print nothing.
// Everything else in rtk's answer stays as rtk wrote it, its permission
// decision included: a deny stays a deny. Only a rewrite of the plain shape
// `rtk <args>` is kept, and only when the launcher's path needs no quoting:
// Codex runs commands through pwsh on Windows.
func Codex(answer jsontext.Value, launcher string) (jsontext.Value, bool) {
	root, ok := objectOf(answer)
	if !ok {
		return nil, false
	}
	output, ok := objectOf(root["hookSpecificOutput"])
	if !ok {
		return nil, false
	}
	updated, ok := objectOf(output["updatedInput"])
	if !ok {
		return nil, false
	}
	command, ok := stringOf(updated["command"])
	if !ok {
		return nil, false
	}
	rest, ok := plainRewrite(command)
	if !ok {
		return nil, false
	}
	path := windowsPathWithSlashes(launcher)
	if !isUnquotedPath(path) {
		return nil, false
	}
	updated["command"] = stringValue(path + rest)
	output["updatedInput"] = mustMarshal(updated)
	root["hookSpecificOutput"] = mustMarshal(output)
	return marshal(root)
}

// CodexLauncher is rtk's real binary for Codex: mise's answer to `mise which
// rtk`, else the rtk on PATH unless it is a shim (in a directory named shims,
// in any case), else "". A shim needs mise's config, which Codex's sandbox
// cannot read.
func CodexLauncher(miseAnswer, onPath string) string {
	if miseAnswer != "" {
		return miseAnswer
	}
	if onPath == "" {
		return ""
	}
	parts := strings.Split(windowsPathWithSlashes(onPath), "/")
	if len(parts) >= 2 && strings.EqualFold(parts[len(parts)-2], "shims") {
		return ""
	}
	return onPath
}

// objectOf reads a JSON value as an object, or ok=false.
func objectOf(value jsontext.Value) (object, bool) {
	if value.Kind() != '{' {
		return nil, false
	}
	var members object
	if err := json.Unmarshal(value, &members); err != nil {
		return nil, false
	}
	return members, true
}

// stringOf reads a JSON value as a string, or ok=false.
func stringOf(value jsontext.Value) (string, bool) {
	if value.Kind() != '"' {
		return "", false
	}
	var text string
	if err := json.Unmarshal(value, &text); err != nil {
		return "", false
	}
	return text, true
}

func stringValue(text string) jsontext.Value {
	return mustMarshal(text)
}

func mustMarshal(v any) jsontext.Value {
	value, ok := marshal(v)
	if !ok {
		panic("rtkpolicy: cannot write a JSON value") // only maps of JSON values and strings get here
	}
	return value
}

func marshal(v any) (jsontext.Value, bool) {
	data, err := json.Marshal(v, json.Deterministic(true))
	if err != nil {
		return nil, false
	}
	return jsontext.Value(data), true
}

// plainRewrite returns what follows `rtk` in a rewrite of the plain shape
// `rtk <args>`, whose leading launcher is its only "rtk".
func plainRewrite(command string) (string, bool) {
	args, ok := strings.CutPrefix(command, launcher+" ")
	if !ok || strings.Contains(args, launcher) {
		return "", false
	}
	return command[len(launcher):], true
}

// inIsolationWorktree reports whether cwd is inside a Claude Code isolation
// worktree, which the harness creates under .claude/worktrees/.
func inIsolationWorktree(cwd string) bool {
	normalized := strings.TrimRight(strings.ReplaceAll(cwd, `\`, "/"), "/") + "/"
	return strings.Contains(normalized, worktreeMarker)
}

// isVetoedRewrite reports whether `rtk [rtk options] git` appears anywhere in
// the rewrite, the form Claude Code's worktree guard cannot look through. It
// splits as the script does (Python's shlex, no comments); text it cannot
// split is vetoed when "git" appears in it at all.
func isVetoedRewrite(command string) bool {
	words, err := pyshlex.SplitWithoutComments(command)
	if err != nil {
		return strings.Contains(command, vetoedCommand)
	}
	for i, word := range words {
		if baseName(word) != launcher {
			continue
		}
		for _, operand := range words[i+1:] {
			if strings.HasPrefix(operand, "-") {
				continue // rtk's own options, such as --ultra-compact
			}
			if baseName(operand) == vetoedCommand {
				return true
			}
			break
		}
	}
	return false
}

// baseName is the script's _basename: the last part of a path written with
// either separator.
func baseName(word string) string {
	word = strings.ReplaceAll(word, `\`, "/")
	return word[strings.LastIndex(word, "/")+1:]
}

// windowsPathWithSlashes is the Codex script's _posix: a path that starts
// with a drive letter gets forward slashes; any other path stays as it is,
// since a backslash there is part of a name.
func windowsPathWithSlashes(path string) string {
	if len(path) >= 3 && isASCIILetter(path[0]) && path[1] == ':' && (path[2] == '\\' || path[2] == '/') {
		return strings.ReplaceAll(path, `\`, "/")
	}
	return path
}

// isUnquotedPath reports whether pwsh and sh both run the path as a command
// without quoting: [A-Za-z0-9_./:-]+.
func isUnquotedPath(path string) bool {
	if path == "" {
		return false
	}
	for i := range len(path) {
		c := path[i]
		if !isASCIILetter(c) && !isASCIIDigit(c) && !strings.ContainsRune("_./:-", rune(c)) {
			return false
		}
	}
	return true
}

// Quote is Python's shlex.quote (3.14): the text as it is when it is ASCII
// and only `%+,-./0-9:=@A-Z_a-z`, else in single quotes with each `'` as
// `'"'"'`; the empty text is ”.
func Quote(text string) string {
	if text == "" {
		return "''"
	}
	safe := true
	for i := range len(text) {
		c := text[i]
		if !isASCIILetter(c) && !isASCIIDigit(c) && !strings.ContainsRune("%+,-./:=@_", rune(c)) {
			safe = false
			break
		}
	}
	if safe {
		return text
	}
	return "'" + strings.ReplaceAll(text, "'", `'"'"'`) + "'"
}

// AsPosix is Python's PurePosixPath(path).as_posix(): runs of slashes become
// one, except a leading pair, which POSIX lets mean something else; "."
// segments go; a trailing slash goes; an empty result is ".".
func AsPosix(path string) string {
	root := ""
	switch {
	case strings.HasPrefix(path, "//") && !strings.HasPrefix(path, "///"):
		root = "//"
	case strings.HasPrefix(path, "/"):
		root = "/"
	}
	var parts []string
	for part := range strings.SplitSeq(path, "/") {
		if part != "" && part != "." {
			parts = append(parts, part)
		}
	}
	if root == "" && len(parts) == 0 {
		return "."
	}
	return root + strings.Join(parts, "/")
}

// VetoCwd is the working directory the Claude script checks for a worktree:
// `payload.get("cwd") or os.getcwd()`, then "" unless that is a string. A cwd
// that is absent or falsy in Python (null, false, "", zero, [], {}) gives the
// process's cwd; any other value that is not a string gives "".
func VetoCwd(value ir.Value, present bool, processCwd string) string {
	if !present || pythonFalsy(value) {
		return processCwd
	}
	if value.IsString {
		return value.Text
	}
	return ""
}

// pythonFalsy reports whether Python's bool() is false for the JSON value:
// "", a number equal to zero (also one too small to hold, which Python reads
// as 0.0), [], {}, null, false.
func pythonFalsy(value ir.Value) bool {
	if value.IsString {
		return value.Text == ""
	}
	switch value.Text {
	case "null", "false", "[]", "{}":
		return true
	}
	if f, err := strconv.ParseFloat(value.Text, 64); err == nil || errors.Is(err, strconv.ErrRange) {
		return f == 0
	}
	return false
}

func isASCIILetter(c byte) bool { return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') }

func isASCIIDigit(c byte) bool { return c >= '0' && c <= '9' }
