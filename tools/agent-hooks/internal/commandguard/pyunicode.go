package commandguard

import (
	"strings"
	"unicode"
)

// pythonSpaceClass is Python's str.isspace() (and re's \s on str patterns) as
// the inside of a regular-expression character class. Go's \s is ASCII only,
// and unicode.IsSpace leaves out U+001C..U+001F, so neither will do.
const pythonSpaceClass = `\t\n\v\f\r\x1c-\x1f \x{85}\x{a0}\x{1680}\x{2000}-\x{200a}` +
	`\x{2028}\x{2029}\x{202f}\x{205f}\x{3000}`

// pythonSpace is Python's \s as a character class.
const pythonSpace = `[` + pythonSpaceClass + `]`

// isPythonSpace is Python's str.isspace() for one character.
func isPythonSpace(r rune) bool {
	switch r {
	case 0x85, 0xa0, 0x1680, 0x2028, 0x2029, 0x202f, 0x205f, 0x3000:
		return true
	default:
		return (r >= '\t' && r <= '\r') || (r >= 0x1c && r <= ' ') || (r >= 0x2000 && r <= 0x200a)
	}
}

// isPythonWord is Python re's \w on str patterns. It reads Python's own table
// (pythonWordTable, written from Python by `just command-guard-corpus`), not
// Go's: Go's tables are a newer Unicode version, and every letter they add
// would hide a name from the guard (fewer word boundaries, fewer blocks).
func isPythonWord(r rune) bool {
	return unicode.Is(pythonWordTable, r)
}

// StripPython is Python's str.strip(): it removes Python spaces at both ends.
func StripPython(s string) string {
	return strings.TrimFunc(s, isPythonSpace)
}

// containsName reports whether text holds one of names where the character
// before it (if any) passes mayPrecede and the character after it (if any)
// passes mayFollow. It is the shape of the Python guard's regular expressions
// `(^|[...])(name|...)(...|$)`, written out because they read Python's \w.
func containsName(text []rune, names []string, mayPrecede, mayFollow func(rune) bool) bool {
	for i := range text {
		if i > 0 && !mayPrecede(text[i-1]) {
			continue
		}
		for _, name := range names {
			end := i + len(name) // the names are ASCII
			if end <= len(text) && string(text[i:end]) == name &&
				(end == len(text) || mayFollow(text[end])) {
				return true
			}
		}
	}
	return false
}
