package rules

import (
	"fmt"
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

// Python's str classes, for the patterns of the ported tests: Go's \s, \d,
// \w and \b know only ASCII.
const (
	pySpaceClass = `\t\n\v\f\r\x{1c}-\x{1f} \x{85}\p{Zs}\x{2028}\x{2029}`
	pyWordClass  = `\p{L}\p{N}_`
)

// pyPattern is a Python re pattern (str semantics) compiled for Go: \s, \S,
// \d, \D, \w and \W become their Unicode classes, and a \b at the start or
// the end is checked against Python's word characters. A \b elsewhere, or a
// class shorthand inside brackets other than [\s\S], is not supported: write
// the check in code.
type pyPattern struct {
	re          *regexp.Regexp
	lead, trail bool
}

func pyCompile(pattern string) pyPattern {
	p := pyPattern{}
	if rest, ok := strings.CutPrefix(pattern, `\b`); ok {
		p.lead, pattern = true, rest
	}
	if rest, ok := strings.CutSuffix(pattern, `\b`); ok && !strings.HasSuffix(rest, `\`) {
		p.trail, pattern = true, rest
	}
	var b strings.Builder
	inClass := false
	for i := 0; i < len(pattern); i++ {
		c := pattern[i]
		if !inClass && strings.HasPrefix(pattern[i:], `[\s\S]`) {
			b.WriteString(`[\s\S]`) // any character, in Go as in Python
			i += len(`[\s\S]`) - 1
			continue
		}
		if c == '\\' && i+1 < len(pattern) {
			next := pattern[i+1]
			i++
			if inClass && strings.ContainsRune("sSdDwWb", rune(next)) {
				panic("pyCompile: a class shorthand inside brackets: " + pattern)
			}
			switch next {
			case 's':
				b.WriteString("[" + pySpaceClass + "]")
			case 'S':
				b.WriteString("[^" + pySpaceClass + "]")
			case 'd':
				b.WriteString(`\p{Nd}`)
			case 'D':
				b.WriteString(`\P{Nd}`)
			case 'w':
				b.WriteString("[" + pyWordClass + "]")
			case 'W':
				b.WriteString("[^" + pyWordClass + "]")
			case 'b':
				panic(`pyCompile: \b inside the pattern: ` + pattern)
			default:
				b.WriteByte('\\')
				b.WriteByte(next)
			}
			continue
		}
		switch c {
		case '[':
			inClass = true
		case ']':
			inClass = false
		}
		b.WriteByte(c)
	}
	p.re = regexp.MustCompile(b.String())
	return p
}

// Search is re.search: a match whose \b ends sit at Python word boundaries.
func (p pyPattern) Search(text string) bool {
	for from := 0; from <= len(text); {
		loc := p.re.FindStringIndex(text[from:])
		if loc == nil {
			return false
		}
		start, end := from+loc[0], from+loc[1]
		if (!p.lead || pyBoundaryAt(text, start)) && (!p.trail || pyBoundaryAt(text, end)) {
			return true
		}
		_, size := utf8.DecodeRuneInString(text[start:])
		from = start + max(size, 1)
	}
	return false
}

// pyMatches: re.search of each pattern over the file finds a match.
func pyMatches(path string, patterns ...string) factCheck {
	compiled := make([]pyPattern, 0, len(patterns))
	for _, p := range patterns {
		compiled = append(compiled, pyCompile(p))
	}
	return func(files map[string]string) []string {
		var out []string
		for i, p := range compiled {
			if !p.Search(files[path]) {
				out = append(out, fmt.Sprintf("%s must match %s", path, patterns[i]))
			}
		}
		return out
	}
}

// pyNoMatch: re.search of each pattern over the file finds nothing.
func pyNoMatch(path string, patterns ...string) factCheck {
	compiled := make([]pyPattern, 0, len(patterns))
	for _, p := range patterns {
		compiled = append(compiled, pyCompile(p))
	}
	return func(files map[string]string) []string {
		var out []string
		for i, p := range compiled {
			if p.Search(files[path]) {
				out = append(out, fmt.Sprintf("%s must not match %s", path, patterns[i]))
			}
		}
		return out
	}
}

// pyLower is str.lower(): Go's strings.ToLower plus Python's full mappings,
// the dotted capital I (U+0130 -> "i̇") and the final sigma (a capital
// sigma after a cased letter and not before one becomes U+03C2).
func pyLower(s string) string {
	runes := []rune(s)
	var b strings.Builder
	for i, r := range runes {
		switch {
		case r == 'İ':
			b.WriteString("i̇")
		case r == 'Σ' && pyFinalSigma(runes, i):
			b.WriteRune('ς')
		default:
			b.WriteRune(unicode.ToLower(r))
		}
	}
	return b.String()
}

// pyFinalSigma is Unicode's Final_Sigma context as Python reads it: a cased
// letter before i and none after, skipping case-ignorable characters.
func pyFinalSigma(runes []rune, i int) bool {
	cased := func(r rune) bool { return unicode.IsUpper(r) || unicode.IsLower(r) || unicode.IsTitle(r) }
	ignorable := func(r rune) bool {
		return unicode.In(r, unicode.Mn, unicode.Me, unicode.Cf, unicode.Lm, unicode.Sk) || strings.ContainsRune("'.:^`·‘’․‧", r)
	}
	j := i - 1
	for j >= 0 && ignorable(runes[j]) {
		j--
	}
	if j < 0 || !cased(runes[j]) {
		return false
	}
	k := i + 1
	for k < len(runes) && ignorable(runes[k]) {
		k++
	}
	return k == len(runes) || !cased(runes[k])
}
