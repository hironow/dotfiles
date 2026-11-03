// Package pyshlex splits text into words exactly as Python's shlex does with
// posix=True, punctuation_chars=True and whitespace_split=True (CPython 3.14,
// Lib/shlex.py), which is how the Python command guard tokenizes a command.
//
// It is not a shell parser, and it keeps the places where that shlex is not a
// shell: `#` starts a comment even inside a word, a backslash keeps the
// newline after it, quotes vanish from the words (so a quoted `;` becomes the
// word `;`), only ASCII spaces, tabs and line breaks separate words, and a run
// of the characters `();<>|&` is one word.
package pyshlex

import "errors"

// The errors Python's shlex raises (as ValueError) for text it cannot split.
var (
	ErrNoClosingQuotation = errors.New("no closing quotation")
	ErrNoEscapedCharacter = errors.New("no escaped character")
)

// Split returns the words of text, or the error Python's shlex raises for it.
func Split(text string) ([]string, error) {
	l := lexer{input: []rune(text), state: stateSpace}
	var words []string
	for {
		word, ok, err := l.readToken()
		if err != nil {
			return nil, err
		}
		if !ok {
			return words, nil
		}
		words = append(words, word)
	}
}

// state is where the lexer is, named after Python's shlex.state values.
type state int

const (
	stateSpace       state = iota // ' ': between words
	stateWord                     // 'a': in a word
	statePunctuation              // 'c': in a run of punctuation characters
	stateSingleQuote              // "'": inside single quotes
	stateDoubleQuote              // '"': inside double quotes
	stateEscape                   // '\\': after a backslash
	stateEnd                      // None: past the end of the text
)

// lexer is Python's shlex object, reduced to what this configuration uses.
type lexer struct {
	input    []rune
	pos      int
	pushback []rune // Python's _pushback_chars: read back from the end
	state    state
}

// token is the word being read: the locals of Python's read_token.
type token struct {
	runes       []rune
	quoted      bool  // a quote was read, so an empty word still counts
	escapedFrom state // Python's escapedstate: where an escape returns to
}

// readToken is Python's read_token: the next word, or ok=false at the end.
func (l *lexer) readToken() (string, bool, error) {
	t := token{escapedFrom: stateSpace}
	for done := false; !done; {
		c, ok := l.read()
		var err error
		switch l.state {
		case stateEnd:
			t.runes = nil
			done = true
		case stateSpace:
			done = l.betweenWords(&t, c, ok)
		case stateSingleQuote, stateDoubleQuote:
			err = l.inQuotes(&t, c, ok)
		case stateEscape:
			err = l.afterBackslash(&t, c, ok)
		case stateWord, statePunctuation:
			done = l.inWord(&t, c, ok)
		}
		if err != nil {
			return "", false, err
		}
	}
	if !t.quoted && len(t.runes) == 0 {
		return "", false, nil
	}
	return string(t.runes), true, nil
}

// read returns the next character, from the pushback first; ok=false at the end.
func (l *lexer) read() (rune, bool) {
	if n := len(l.pushback); n > 0 {
		c := l.pushback[n-1]
		l.pushback = l.pushback[:n-1]
		return c, true
	}
	if l.pos == len(l.input) {
		return 0, false
	}
	c := l.input[l.pos]
	l.pos++
	return c, true
}

// skipLine consumes the rest of the line, its newline included, as Python's
// instream.readline() does for a comment.
func (l *lexer) skipLine() {
	for l.pos < len(l.input) {
		c := l.input[l.pos]
		l.pos++
		if c == '\n' {
			return
		}
	}
}

// betweenWords handles one character in state ' '. It reports whether the
// word is complete.
func (l *lexer) betweenWords(t *token, c rune, ok bool) bool {
	switch {
	case !ok:
		l.state = stateEnd
		return true
	case isWhitespace(c):
		return t.complete()
	case c == '#':
		l.skipLine()
	case c == '\\':
		t.escapedFrom = stateWord
		l.state = stateEscape
	case isPunctuation(c):
		t.runes = []rune{c}
		l.state = statePunctuation
	case c == '\'':
		l.state = stateSingleQuote
	case c == '"':
		l.state = stateDoubleQuote
	default: // a word character, or anything else (whitespace_split)
		t.runes = []rune{c}
		l.state = stateWord
	}
	return false
}

// inQuotes handles one character inside quotes.
func (l *lexer) inQuotes(t *token, c rune, ok bool) error {
	t.quoted = true
	if !ok {
		return ErrNoClosingQuotation
	}
	switch {
	case c == quoteOf(l.state):
		l.state = stateWord
	case c == '\\' && l.state == stateDoubleQuote:
		t.escapedFrom = l.state
		l.state = stateEscape
	default:
		t.runes = append(t.runes, c)
	}
	return nil
}

// afterBackslash handles the character after a backslash. Inside double
// quotes the backslash stays unless it escapes a backslash or the quote.
func (l *lexer) afterBackslash(t *token, c rune, ok bool) error {
	if !ok {
		return ErrNoEscapedCharacter
	}
	quote := quoteOf(t.escapedFrom)
	if quote != 0 && c != '\\' && c != quote {
		t.runes = append(t.runes, '\\')
	}
	t.runes = append(t.runes, c)
	l.state = t.escapedFrom
	return nil
}

// inWord handles one character in a word or a run of punctuation. It reports
// whether the word is complete.
func (l *lexer) inWord(t *token, c rune, ok bool) bool {
	switch {
	case !ok:
		l.state = stateEnd
		return true
	case isWhitespace(c):
		l.state = stateSpace
		return t.complete()
	case c == '#':
		l.skipLine()
		l.state = stateSpace
		return t.complete()
	case l.state == statePunctuation:
		if isPunctuation(c) {
			t.runes = append(t.runes, c)
			return false
		}
		l.pushback = append(l.pushback, c)
		l.state = stateSpace
		return true
	case c == '\'':
		l.state = stateSingleQuote
	case c == '"':
		l.state = stateDoubleQuote
	case c == '\\':
		t.escapedFrom = stateWord
		l.state = stateEscape
	case !isPunctuation(c):
		t.runes = append(t.runes, c)
	default: // punctuation ends the word and starts the next one
		l.pushback = append(l.pushback, c)
		l.state = stateSpace
		return t.complete()
	}
	return false
}

// complete is Python's `self.token or (self.posix and quoted)`.
func (t *token) complete() bool {
	return len(t.runes) > 0 || t.quoted
}

// quoteOf returns the quote character of a quote state, or 0.
func quoteOf(s state) rune {
	switch s {
	case stateSingleQuote:
		return '\''
	case stateDoubleQuote:
		return '"'
	default:
		return 0
	}
}

// isWhitespace is Python shlex's whitespace: ' \t\r\n', not Unicode spaces.
func isWhitespace(c rune) bool {
	return c == ' ' || c == '\t' || c == '\r' || c == '\n'
}

// isPunctuation is Python shlex's punctuation_chars=True: '();<>|&'.
func isPunctuation(c rune) bool {
	switch c {
	case '(', ')', ';', '<', '>', '|', '&':
		return true
	default:
		return false
	}
}
