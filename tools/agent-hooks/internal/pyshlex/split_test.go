package pyshlex_test

import (
	"fmt"
	"slices"
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/guardcorpus"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/pyshlex"
)

// pythonMessages are the ValueError messages Python's shlex raises.
var pythonMessages = map[error]string{
	pyshlex.ErrNoClosingQuotation: "No closing quotation",
	pyshlex.ErrNoEscapedCharacter: "No escaped character",
}

func TestSplitAgreesWithPythonShlexOnTheCorpus(t *testing.T) {
	for _, entry := range guardcorpus.Entries(t) {
		t.Run(fmt.Sprintf("line-%d", entry.Line), func(t *testing.T) {
			// given an input of the corpus, when it is split
			words, err := pyshlex.Split(entry.Input)
			// then Python's shlex gave the same words, or failed the same way
			if entry.TokenError != nil {
				if pythonMessages[err] != *entry.TokenError {
					t.Fatalf("Split(%q) error = %v, Python raised %q", entry.Input, err, *entry.TokenError)
				}
				return
			}
			if err != nil || !slices.Equal(words, entry.Tokens) {
				t.Fatalf("Split(%q) = %q, %v; Python gave %q", entry.Input, words, err, entry.Tokens)
			}
		})
	}
}

// These are the places where Python's shlex is not a shell, spelled out.
func TestSplitKeepsPythonShlexQuirks(t *testing.T) {
	cases := []struct {
		name  string
		input string
		words []string
	}{
		{"a # inside a word starts a comment", "npm#x make", []string{"npm"}},
		{"a comment ends at the newline", "ls #npm i\nmake", []string{"ls", "make"}},
		{"a backslash keeps the newline after it", "a\\\nb", []string{"a\nb"}},
		{"a run of punctuation is one word", "ls |& npm", []string{"ls", "|&", "npm"}},
		{"quotes vanish, so a quoted ; looks like an operator", `echo ";" npm`, []string{"echo", ";", "npm"}},
		{"empty quotes are an empty word", "''", []string{""}},
		{"only ASCII spaces split words", "a\u00a0b c", []string{"a\u00a0b", "c"}},
		{"double quotes keep a backslash before other characters", `"a\b"`, []string{`a\b`}},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			words, err := pyshlex.Split(c.input)
			if err != nil || !slices.Equal(words, c.words) {
				t.Fatalf("Split(%q) = %q, %v; want %q", c.input, words, err, c.words)
			}
		})
	}
}
