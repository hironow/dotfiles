package commandguard

import (
	"errors"
	"fmt"
	"slices"
	"testing"
	"unicode/utf8"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/guardcorpus"
)

func TestBashLexAgreesWithTheFixedPythonGuardOnTheCorpus(t *testing.T) {
	// fixed-command-split: the lexer is a port of the one the fix puts into
	// the Python guard (scripts/fixed_command_split.py), and reads every input
	// of the corpus as it does.
	for _, entry := range guardcorpus.Entries(t) {
		t.Run(fmt.Sprintf("line-%d", entry.Line), func(t *testing.T) {
			checkReading(t, entry.Input, entry.Bash)
		})
	}
}

// checkReading compares what bashLex reads in a text with Python's reading.
func checkReading(t *testing.T, text string, want guardcorpus.BashReading) {
	t.Helper()
	read, err := bashLex(text)
	if want.Error != nil {
		var unterminated *unterminatedError
		if !errors.As(err, &unterminated) {
			t.Fatalf("bashLex(%q) = %v; Python found an unterminated quote or substitution", text, err)
		}
		// Python counts code points, Go bytes.
		if got := utf8.RuneCountInString(text[:unterminated.lineStart]); got != *want.Error {
			t.Fatalf("bashLex(%q): its failing line starts at %d, Python's at %d", text, got, *want.Error)
		}
		if want.Before == nil {
			t.Fatalf("the corpus has no reading of the lines before the failing one")
		}
		checkReading(t, text[:unterminated.lineStart], *want.Before)
		return
	}
	if err != nil {
		t.Fatalf("bashLex(%q) = %v; Python read it", text, err)
	}
	tokens := make([][2]string, 0, len(read.tokens))
	for _, tok := range read.tokens {
		kind := "word"
		switch {
		case tok.op:
			kind = "op"
		case tok.quoted:
			kind = "quoted"
		}
		tokens = append(tokens, [2]string{kind, tok.text})
	}
	if !slices.Equal(tokens, want.Tokens) {
		t.Errorf("bashLex(%q) tokens = %q, Python's %q", text, tokens, want.Tokens)
	}
	if !slices.Equal(read.substitutions, want.Substitutions) {
		t.Errorf("bashLex(%q) substitutions = %q, Python's %q", text, read.substitutions, want.Substitutions)
	}
	if !slices.Equal(read.codeBodies, want.CodeBodies) {
		t.Errorf("bashLex(%q) code bodies = %q, Python's %q", text, read.codeBodies, want.CodeBodies)
	}
	if got := read.cleaned(text); got != want.Cleaned {
		t.Errorf("bashLex(%q) cleaned = %q, Python's %q", text, got, want.Cleaned)
	}
}
