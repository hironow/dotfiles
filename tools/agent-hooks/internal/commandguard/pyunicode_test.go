package commandguard

import (
	"regexp"
	"slices"
	"testing"
	"unicode"
)

// pythonSpaceCodePoints is Python 3.14's
// [c for c in range(0x110000) if chr(c).isspace()], the same set as re's \s.
var pythonSpaceCodePoints = []rune{
	0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x1c, 0x1d, 0x1e, 0x1f, 0x20, 0x85, 0xa0, 0x1680,
	0x2000, 0x2001, 0x2002, 0x2003, 0x2004, 0x2005, 0x2006, 0x2007, 0x2008, 0x2009,
	0x200a, 0x2028, 0x2029, 0x202f, 0x205f, 0x3000,
}

func TestPythonSpacesAreExactlyPythons(t *testing.T) {
	// given the regular-expression class and the function the guard uses for \s
	class := regexp.MustCompile(`^[` + pythonSpaceClass + `]$`)
	var spaces []rune
	for r := rune(0); r <= 0x10ffff; r++ {
		if r >= 0xd800 && r <= 0xdfff {
			continue // surrogates are not characters
		}
		// then they agree with each other on every character
		if isPythonSpace(r) != class.MatchString(string(r)) {
			t.Fatalf("U+%04X: isPythonSpace and pythonSpaceClass disagree", r)
		}
		if isPythonSpace(r) {
			spaces = append(spaces, r)
		}
	}
	// and with Python's own list
	if !slices.Equal(spaces, pythonSpaceCodePoints) {
		t.Fatalf("Python spaces = %U; want %U", spaces, pythonSpaceCodePoints)
	}
}

func TestStripPythonRemovesOnlyPythonSpaces(t *testing.T) {
	cases := map[string]string{
		"\x1c EOF\u3000": "EOF",
		"\u200bEOF":      "\u200bEOF", // a zero-width space is not a space
		"\tE O F \n":     "E O F",
	}
	for in, want := range cases {
		if got := stripPython(in); got != want {
			t.Errorf("stripPython(%q) = %q; want %q", in, got, want)
		}
	}
}

func TestPythonWordReadsPythonsTableNotGos(t *testing.T) {
	// given letters Unicode 17.0 added, which Go 1.27 knows and Python 3.14 does not
	for _, r := range []rune{0x088f, 0xa7ce, 0x16ea0} {
		if !unicode.IsLetter(r) {
			t.Fatalf("U+%04X: Go no longer calls it a letter; pick another Unicode 17.0 letter", r)
		}
		// then the guard does not count them as word characters
		if isPythonWord(r) {
			t.Errorf("isPythonWord(U+%04X) = true; Python (Unicode %s) does not", r, pythonUnicodeVersion)
		}
	}
}

func TestPythonWordTableHoldsOnlyLettersNumbersAndUnderscore(t *testing.T) {
	for r := rune(0); r <= unicode.MaxRune; r++ {
		if isPythonWord(r) && r != '_' && !unicode.IsLetter(r) && !unicode.IsNumber(r) {
			t.Fatalf("isPythonWord(U+%04X) = true, but Go calls it neither a letter nor a number", r)
		}
	}
}
