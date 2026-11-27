package rules

import (
	"regexp"
	"strings"
	"unicode"
	"unicode/utf8"
)

// The fact rules port Python tests; these read text the way those tests'
// Python did, where Go's own functions read it differently.

// pyCodeLines is the lines of Python's str.splitlines() that do not start
// with "#" after str.lstrip().
func pyCodeLines(text string) []string {
	var out []string
	for _, line := range pySplitlines(text) {
		if !strings.HasPrefix(strings.TrimLeftFunc(line, pyIsSpace), "#") {
			out = append(out, line)
		}
	}
	return out
}

// pySplitlines is str.splitlines(): it breaks at \n, \r, \r\n, \v, \f,
// \x1c-\x1e, \x85, U+2028 and U+2029, and keeps no empty last line.
func pySplitlines(text string) []string {
	var lines []string
	start := 0
	for i := 0; i < len(text); {
		r, size := utf8.DecodeRuneInString(text[i:])
		switch r {
		case '\n', '\r', '\v', '\f', 0x1c, 0x1d, 0x1e, 0x85, 0x2028, 0x2029:
			lines = append(lines, text[start:i])
			i += size
			if r == '\r' && i < len(text) && text[i] == '\n' {
				i++
			}
			start = i
		default:
			i += size
		}
	}
	if start < len(text) {
		lines = append(lines, text[start:])
	}
	return lines
}

// pyIsSpace is str.isspace() for one character.
func pyIsSpace(r rune) bool {
	return unicode.IsSpace(r) || r >= 0x1c && r <= 0x1f
}

// pySliceFrom is the test's text[i+offset:], where i is the character index
// of the byte offset at (Python's find, -1 when missing): Python counts
// characters, and reads a negative start from the end.
func pySliceFrom(text string, at, offset int) string {
	runes := []rune(text)
	i := -1
	if at >= 0 {
		i = utf8.RuneCountInString(text[:at])
	}
	start := i + offset
	if start < 0 {
		start = max(len(runes)+start, 0)
	}
	return string(runes[min(start, len(runes)):])
}

// pyHasWord is re.search(rf"\b{word}\b", text) with Python's Unicode word
// characters (Go's \b knows only ASCII ones).
func pyHasWord(text, word string) bool {
	for from := 0; ; {
		i := strings.Index(text[from:], word)
		if i < 0 {
			return false
		}
		start, end := from+i, from+i+len(word)
		before, _ := utf8.DecodeLastRuneInString(text[:start])
		after, _ := utf8.DecodeRuneInString(text[end:])
		if (start == 0 || !pyWordRune(before)) && (end == len(text) || !pyWordRune(after)) {
			return true
		}
		from = start + 1
	}
}

// pyWordRune is a character of Python's \w for str patterns.
func pyWordRune(r rune) bool {
	return r == '_' || unicode.IsLetter(r) || unicode.IsNumber(r)
}

// pyBoundaryAt is Python's \b at byte offset p of text: a word character on
// exactly one side.
func pyBoundaryAt(text string, p int) bool {
	before, after := false, false
	if p > 0 {
		r, _ := utf8.DecodeLastRuneInString(text[:p])
		before = pyWordRune(r)
	}
	if p < len(text) {
		r, _ := utf8.DecodeRuneInString(text[p:])
		after = pyWordRune(r)
	}
	return before != after
}

// pyLeadingBoundary is re.search(r"\b" + pattern, text): a match of re (the
// pattern without its leading \b) that starts at a Python word boundary.
func pyLeadingBoundary(re *regexp.Regexp, text string) bool {
	for from := 0; from <= len(text); {
		loc := re.FindStringIndex(text[from:])
		if loc == nil {
			return false
		}
		if pyBoundaryAt(text, from+loc[0]) {
			return true
		}
		_, size := utf8.DecodeRuneInString(text[from+loc[0]:])
		from += loc[0] + max(size, 1)
	}
	return false
}

// pyStrip is str.strip().
func pyStrip(s string) string {
	return strings.TrimFunc(s, pyIsSpace)
}

// pyDigitsThenBoundary: the text at i starts with Python \d+ followed by a
// word boundary (re's r"\d+\b" there).
func pyDigitsThenBoundary(text string, i int) bool {
	j := i
	for j < len(text) {
		r, size := utf8.DecodeRuneInString(text[j:])
		if !unicode.IsDigit(r) {
			break
		}
		j += size
	}
	return j > i && pyBoundaryAt(text, j)
}
