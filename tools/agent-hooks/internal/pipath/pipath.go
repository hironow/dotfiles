// Package pipath resolves a tool's path the way Pi 1.4.0's write and edit
// tools do before they touch the file (resolveToCwd), on POSIX. The hooks
// judge the file Pi writes, not the text the model gave: @docker-compose.yaml
// writes docker-compose.yaml, and a relative path is under the call's cwd.
// corpus.jsonl holds Pi's own answers (package pioracle), which the tests
// check the port against.
package pipath

import (
	"net/url"
	"path"
	"regexp"
	"strings"
	"unicode/utf8"
)

// Home is the home directory as Node's os.homedir() finds it, which is how
// Pi expands ~: Dir is $HOME when it is set, even to "", else the password
// entry's. Known is false when neither names one.
type Home struct {
	Dir   string
	Known bool
}

// Resolve returns the file Pi resolves a path to, against cwd, and whether
// it could tell. It refuses (ok false) where it cannot match Pi exactly: ~
// when the home is unknown; a file: URL outside its plain form (the host
// empty or localhost, the path only unreserved characters, / and %XX
// escapes that decode to valid UTF-8, with no NUL, no encoded /, and no
// empty segment); and a cwd that is not absolute.
func Resolve(input, cwd string, home Home) (string, bool) {
	if !path.IsAbs(cwd) {
		return "", false
	}
	normalized := strings.TrimPrefix(strings.Map(normalizeSpace, input), "@")
	switch {
	case normalized == "~", strings.HasPrefix(normalized, "~/"):
		if !home.Known {
			return "", false
		}
		if normalized == "~" {
			normalized = home.Dir
		} else {
			normalized = path.Join(home.Dir, normalized[2:])
		}
	case strings.HasPrefix(normalized, "file://"):
		var ok bool
		normalized, ok = plainFilePath(normalized)
		if !ok {
			return "", false
		}
	}
	if path.IsAbs(normalized) {
		return path.Clean(normalized), true
	}
	return path.Join(cwd, normalized), true
}

// normalizeSpace is Pi's UNICODE_SPACES rule: each of those spaces becomes
// a plain space.
func normalizeSpace(r rune) rune {
	if r == '\u00a0' || r >= '\u2000' && r <= '\u200a' || r == '\u202f' || r == '\u205f' || r == '\u3000' {
		return ' '
	}
	return r
}

// plainFileURL is the plain form of a file: URL, the one form the port
// resolves: Node's URL parser and fileURLToPath read it as its decoded path.
// An empty segment (//) is not plain: the URL parser keeps it as a segment,
// so a later .. removes it (file:///a//../x is /a/x), where path.Clean drops
// it first (/x).
var plainFileURL = regexp.MustCompile(`^file://(?:localhost)?(/[A-Za-z0-9._~/%-]*)$`)

// plainFilePath is the path a plain file: URL names, or false for any other
// URL.
func plainFilePath(input string) (string, bool) {
	match := plainFileURL.FindStringSubmatch(input)
	if match == nil || strings.Contains(match[1], "//") || strings.Contains(input, "%2F") || strings.Contains(input, "%2f") {
		return "", false
	}
	decoded, err := url.PathUnescape(match[1])
	if err != nil || !utf8.ValidString(decoded) || strings.ContainsRune(decoded, '\x00') {
		return "", false
	}
	return decoded, true
}
