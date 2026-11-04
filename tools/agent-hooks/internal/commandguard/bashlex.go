package commandguard

// fixed-command-split: the guard reads a text as bash does. This is a port of
// the lexer that the fix's edit puts into the Python guard
// (scripts/fixed_command_split.py), checked against it on the corpus. It
// splits words and operators where bash does, finds heredocs at real <<
// operators, and returns what bash runs as code: the bodies of command and
// process substitutions, and the heredoc bodies fed to an interpreter.
//
// It scans bytes: every character bash treats specially is ASCII, and no
// byte of a multi-byte UTF-8 character is ASCII. Where the Python takes "the
// next character" (after a backslash, in \cX), this takes a whole rune.

import (
	"regexp"
	"strconv"
	"strings"
	"unicode/utf8"
)

// token is a word, after quote removal, or an operator. A word written
// with a quote, an escape, or an expansion is quoted: bash never reads it
// as a reserved word ("case" is a command's name).
type token struct {
	text   string
	op     bool
	quoted bool
}

// lexed is what the lexer read: the tokens, what bash runs as code, and where
// the heredoc bodies are (byte ranges), so that the text without them can be
// read by the raw patterns.
type lexed struct {
	tokens        []token
	substitutions []string
	codeBodies    []string
	removed       [][2]int
	end           int
}

// cleaned is the text without its heredoc bodies.
func (l *lexed) cleaned(text string) string {
	ranges := append([][2]int(nil), l.removed...)
	sortRanges(ranges)
	var kept strings.Builder
	at := 0
	for _, r := range ranges {
		kept.WriteString(text[at:max(at, r[0])])
		at = max(at, r[1])
	}
	kept.WriteString(text[at:])
	return kept.String()
}

func sortRanges(ranges [][2]int) {
	for i := 1; i < len(ranges); i++ {
		for j := i; j > 0 && (ranges[j][0] < ranges[j-1][0] ||
			(ranges[j][0] == ranges[j-1][0] && ranges[j][1] < ranges[j-1][1])); j-- {
			ranges[j], ranges[j-1] = ranges[j-1], ranges[j]
		}
	}
}

// unterminatedError is a quote or substitution that does not end. lineStart
// is where its line begins (a byte index), after the last top-level newline
// before it: the lines before it are complete, and bash runs them.
type unterminatedError struct{ lineStart int }

func (e *unterminatedError) Error() string { return "a quote or substitution does not end" }

// bash's operators, longest first, so that each is read by longest match.
var bashOperators = []string{
	";;&", "<<<", "<<-", "&>>",
	"&&", "||", ";;", ";&", "|&", "<<", "<&", "<>", ">>", ">&", ">|", "&>",
	"&", ";", "|", "(", ")", "<", ">",
}

var (
	redirections      = words("<<<", "<<-", "&>>", "<<", "<&", "<>", ">>", ">&", ">|", "&>", "<", ">")
	controlOperators  = words("\n", ";", "&", "&&", "||", "|", "|&", "(", ")", ";;", ";&", ";;&")
	keepsCommandStart = words("!", "{", "if", "then", "elif", "else", "do", "while", "until", "time")
	arrayOpen         = regexp.MustCompile(`^[A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]*\])?\+?=$`)
	descriptor        = regexp.MustCompile(`^(?:[0-9]+|\{[A-Za-z_][A-Za-z0-9_]*\})$`)
)

// heredoc is a heredoc opened on the current line.
type heredoc struct {
	delimiter string
	tabs      bool // <<-
	code      bool // its line names an interpreter
	expands   bool // its delimiter is not quoted
}

// lexer reads one text; lineStart is where its current top-level line begins.
type lexer struct {
	text      string
	lineStart int
}

// unterminated is what a lexer panics with; bashLex recovers it.
type unterminated struct{ lineStart int }

func (l *lexer) fail() { panic(unterminated{l.lineStart}) }

// bashLex lexes a whole text.
func bashLex(text string) (result *lexed, err error) {
	l := &lexer{text: text}
	defer func() {
		if r := recover(); r != nil {
			u, ok := r.(unterminated)
			if !ok {
				panic(r)
			}
			result, err = nil, &unterminatedError{lineStart: u.lineStart}
		}
	}()
	return l.lex(0, false), nil
}

// list is the state of lexing one command list: the whole text, or one
// nested in $( ), <( ), >( ), or NAME=( ).
type list struct {
	l               *lexer
	nested          bool
	out             *lexed
	i               int
	word            strings.Builder
	written         strings.Builder // the word as written, its line continuations gone
	inWord          bool
	wordStart       int
	depth           int    // nested: the ( ) opened inside the list
	heredocOperator string // a << waiting for its delimiter word
	marks           [3]int // what had been read when that << came
	heredocs        []heredoc
	caseStates      []string // nested: each open case, and where it stands
	commandStart    bool     // nested: whether a command may start here
}

// lex lexes from i to the end of the text or, nested, to the ) that closes a
// command list opened just before i; end is the index after what was read.
func (l *lexer) lex(i int, nested bool) *lexed {
	s := &list{l: l, nested: nested, out: &lexed{}, i: i, commandStart: true}
	for s.i < len(l.text) {
		if s.step(l.text[s.i]) {
			return s.out
		}
	}
	if nested {
		l.fail()
	}
	s.endWord()
	l.readHeredocBodies(len(l.text), s.heredocs, s.out)
	s.out.end = len(l.text)
	return s.out
}

// step reads what starts at s.i, whose first byte is c. It reports whether
// that was the ) that closes a nested list.
func (s *list) step(c byte) bool {
	text, n := s.l.text, len(s.l.text)
	switch {
	case c == '\\' && s.i+1 < n && text[s.i+1] == '\n':
		s.i += 2 // a line continuation: bash removes it
	case c == ' ' || c == '\t':
		s.endWord()
		s.i++
	case c == '\n':
		s.newline()
	case c == '#' && !s.inWord:
		if k := strings.IndexByte(text[s.i:], '\n'); k >= 0 {
			s.i += k
		} else {
			s.i = n
		}
	case (c == '<' || c == '>') && s.i+1 < n && text[s.i+1] == '(':
		// a process substitution, also inside a word (x<(true))
		s.openWord()
		inner := s.l.lex(s.i+2, true)
		s.out.substitutions = append(s.out.substitutions, text[s.i+2:inner.end-1])
		s.out.removed = append(s.out.removed, inner.removed...)
		s.word.WriteString(text[s.i:inner.end])
		s.written.WriteString(text[s.i:inner.end])
		s.i = inner.end
	case c == '(' && s.inWord && arrayOpen.MatchString(s.written.String()):
		// NAME=(...): an array, one word
		inner := s.l.lex(s.i+1, true)
		s.out.substitutions = append(s.out.substitutions, inner.substitutions...)
		s.out.codeBodies = append(s.out.codeBodies, inner.codeBodies...)
		s.out.removed = append(s.out.removed, inner.removed...)
		s.word.WriteString(text[s.i:inner.end])
		s.written.WriteString(text[s.i:inner.end])
		s.i = inner.end
	case strings.IndexByte("|&;()<>", c) >= 0:
		return s.operator(c)
	default:
		s.openWord()
		start := s.i
		s.i = s.l.wordPart(s.i, &s.word, s.out)
		s.written.WriteString(text[start:s.i])
	}
	return false
}

func (s *list) openWord() {
	if !s.inWord {
		s.inWord, s.wordStart = true, s.i
	}
}

// newline ends a command, and reads the bodies of the heredocs opened on the
// line it ends.
func (s *list) newline() {
	s.endWord()
	s.commandStart = true
	s.out.tokens = append(s.out.tokens, token{text: "\n", op: true})
	s.i = s.l.readHeredocBodies(s.i+1, s.heredocs, s.out)
	s.heredocs = s.heredocs[:0]
	if !s.nested {
		s.l.lineStart = s.i
	}
}

// operator reads the operator at s.i, whose first byte is c. It reports
// whether that was the ) that closes a nested list.
func (s *list) operator(c byte) bool {
	text := s.l.text
	if (c == '<' || c == '>') && s.inWord && descriptor.MatchString(s.written.String()) {
		s.word.Reset() // the file descriptor of the redirection
		s.written.Reset()
		s.inWord = false
	}
	s.endWord()
	operator, after := operatorAt(text, s.i)
	if s.closes(operator) {
		s.out.end = s.i + 1
		return true
	}
	s.commandStart = controlOperators[operator]
	if operator == "<<" || operator == "<<-" {
		s.heredocOperator = operator
		s.marks = [3]int{len(s.out.substitutions), len(s.out.codeBodies), len(s.out.removed)}
	}
	s.out.tokens = append(s.out.tokens, token{text: operator, op: true})
	s.i = after
	return false
}

// operatorAt is the longest operator at i, and the index after it. bash
// removes a line continuation before it reads an operator, also inside one
// (<<\ newline -EOF is <<-, and && may be written &\ newline &).
func operatorAt(text string, i int) (string, int) {
	var seen []byte
	var ends []int
	for j := i; j < len(text) && len(seen) < 3; {
		if strings.HasPrefix(text[j:], "\\\n") {
			j += 2
			continue
		}
		seen = append(seen, text[j])
		j++
		ends = append(ends, j)
	}
	for _, o := range bashOperators {
		if strings.HasPrefix(string(seen), o) {
			return o, ends[len(o)-1]
		}
	}
	return "", i + 1 // unreachable: a byte of |&;()<> is an operator
}

// closes follows the case states and the nesting through one operator. It
// reports whether the operator is the ) that closes a nested list.
func (s *list) closes(operator string) bool {
	top := ""
	if len(s.caseStates) > 0 {
		top = s.caseStates[len(s.caseStates)-1]
	}
	switch {
	case top == "pattern" && (operator == "(" || operator == ")" || operator == "|"):
		if operator == ")" {
			s.caseStates[len(s.caseStates)-1] = "body"
		}
	case top == "body" && (operator == ";;" || operator == ";&" || operator == ";;&"):
		s.caseStates[len(s.caseStates)-1] = "pattern"
	case s.nested && operator == ")":
		if s.depth == 0 {
			return true
		}
		s.depth--
	case s.nested && operator == "(":
		s.depth++
	}
	return false
}

// endWord ends the open word, if there is one: a token, the delimiter of a
// pending <<, and, nested, a step of the case states.
func (s *list) endWord() {
	if !s.inWord {
		return
	}
	value, raw := s.word.String(), s.written.String()
	if s.heredocOperator != "" {
		s.openHeredoc(value, raw)
	}
	quoted := strings.ContainsAny(raw, "'\"\\$`")
	if s.nested {
		reserved := value
		if quoted {
			reserved = ""
		}
		s.commandStart = followCase(&s.caseStates, reserved, s.commandStart)
	}
	s.out.tokens = append(s.out.tokens, token{text: value, quoted: quoted})
	s.word.Reset()
	s.written.Reset()
	s.inWord = false
}

// openHeredoc takes a word as the delimiter of the pending <<. bash does not
// expand a delimiter word, so what was read in it is dropped.
func (s *list) openHeredoc(value, raw string) {
	text := s.l.text
	s.out.substitutions = s.out.substitutions[:s.marks[0]]
	s.out.codeBodies = s.out.codeBodies[:s.marks[1]]
	s.out.removed = s.out.removed[:s.marks[2]]
	lineBegin := strings.LastIndexByte(text[:s.wordStart], '\n') + 1
	lineEnd := len(text)
	if k := strings.IndexByte(text[s.wordStart:], '\n'); k >= 0 {
		lineEnd = s.wordStart + k
	}
	s.heredocs = append(s.heredocs, heredoc{
		delimiter: value,
		tabs:      s.heredocOperator == "<<-",
		code:      mentionsInterpreter(text[lineBegin:lineEnd]),
		expands:   !strings.ContainsAny(raw, "'\"\\"),
	})
	s.heredocOperator = ""
}

// wordPart reads one part of a word at i into word: an escaped character, a
// quoted string, an expansion, or a plain character. It returns the index
// after it.
func (l *lexer) wordPart(i int, word *strings.Builder, out *lexed) int {
	text, n := l.text, len(l.text)
	c := text[i]
	switch {
	case c == '\\':
		if i+1 == n {
			word.WriteByte('\\') // a backslash at the very end is itself
			return i + 1
		}
		_, size := utf8.DecodeRuneInString(text[i+1:])
		word.WriteString(text[i+1 : i+1+size])
		return i + 1 + size
	case c == '\'':
		k := strings.IndexByte(text[i+1:], '\'')
		if k < 0 {
			l.fail()
		}
		word.WriteString(text[i+1 : i+1+k])
		return i + 2 + k
	case c == '"':
		return l.doubleQuoted(i+1, word, out)
	case c == '$' && i+1 < n && text[i+1] == '\'':
		return l.ansiC(i+2, word)
	case c == '$' && i+1 < n && text[i+1] == '"':
		return l.doubleQuoted(i+2, word, out)
	case expansionStarts(text, i):
		end := l.expansionEnd(i, out, false)
		word.WriteString(text[i:end])
		return end
	default:
		word.WriteByte(c)
		return i + 1
	}
}

// followCase follows case ... esac through one word of a nested command
// list, so that a pattern's ) does not end the list (bash reads $(case x in
// a) ...;; esac)). The word is "" when it was quoted, since a quoted word is
// never a reserved word. It returns whether a command may start after it.
func followCase(states *[]string, word string, commandStart bool) bool {
	s := *states
	top := ""
	if len(s) > 0 {
		top = s[len(s)-1]
	}
	switch {
	case top == "subject":
		s[len(s)-1] = "in"
	case top == "in":
		if word == "in" {
			s[len(s)-1] = "pattern"
		}
	case top == "pattern":
		if word == "esac" {
			*states = s[:len(s)-1]
		}
	case commandStart && word == "case":
		*states = append(*states, "subject")
	case top == "body" && commandStart && word == "esac":
		*states = s[:len(s)-1]
	}
	return keepsCommandStart[word]
}

// readHeredocBodies reads the bodies of the heredocs opened on the line
// before i, in order. Where the delimiter is not quoted, bash first joins a
// line that ends in an unescaped backslash to the next. Then <<- strips the
// leading tabs, the body's too, and a body ends at the line that is its
// delimiter, or at the end. It returns the index after the last body.
func (l *lexer) readHeredocBodies(i int, heredocs []heredoc, out *lexed) int {
	text, n := l.text, len(l.text)
	for _, h := range heredocs {
		start := i
		var lines []string
		for i < n {
			var line string
			line, i = physicalLine(text, i)
			for h.expands && endsInBackslash(line) && i < n {
				var following string
				following, i = physicalLine(text, i)
				line = line[:len(line)-1] + following
			}
			if h.tabs {
				line = strings.TrimLeft(line, "\t")
			}
			if line == h.delimiter {
				break
			}
			lines = append(lines, line)
		}
		out.removed = append(out.removed, [2]int{start, i})
		body := strings.Join(lines, "\n")
		switch {
		case h.code:
			out.codeBodies = append(out.codeBodies, body)
		case h.expands:
			out.substitutions = append(out.substitutions, heredocSubstitutions(body)...)
		}
	}
	return i
}

// physicalLine is the line at i without its newline, and the index after it.
func physicalLine(text string, i int) (string, int) {
	if k := strings.IndexByte(text[i:], '\n'); k >= 0 {
		return text[i : i+k], i + k + 1
	}
	return text[i:], len(text)
}

// endsInBackslash reports whether a line ends in a backslash that no
// backslash escapes.
func endsInBackslash(line string) bool {
	return (len(line)-len(strings.TrimRight(line, "\\")))%2 == 1
}

// heredocSubstitutions is what bash expands in a heredoc body whose delimiter
// is not quoted: its command substitutions. Quotes are plain characters
// there, and a backslash escapes $, backquote, and itself. One that does not
// end runs to the end of the body.
func heredocSubstitutions(body string) (found []string) {
	l := &lexer{text: body}
	out := &lexed{}
	for i := 0; i < len(body); {
		if body[i] == '\\' {
			i = skipEscaped(body, i)
			continue
		}
		if !expansionStarts(body, i) {
			i++
			continue
		}
		end, ok := l.tryExpansionEnd(i, out)
		if !ok {
			skip := 2
			if body[i] == '`' {
				skip = 1
			}
			return append(out.substitutions, body[i+skip:])
		}
		i = end
	}
	return out.substitutions
}

// tryExpansionEnd is expansionEnd, reporting an expansion that does not end
// as false.
func (l *lexer) tryExpansionEnd(i int, out *lexed) (end int, ok bool) {
	defer func() {
		if r := recover(); r != nil {
			if _, isUnterminated := r.(unterminated); !isUnterminated {
				panic(r)
			}
			end, ok = 0, false
		}
	}()
	return l.expansionEnd(i, out, false), true
}

// skipEscaped is the index after a backslash at i and the character it escapes.
func skipEscaped(text string, i int) int {
	if i+1 >= len(text) {
		return i + 2
	}
	_, size := utf8.DecodeRuneInString(text[i+1:])
	return i + 1 + size
}

// expansionStarts reports whether $(, ${, or a backquote starts at i.
func expansionStarts(text string, i int) bool {
	return text[i] == '`' || strings.HasPrefix(text[i:], "$(") || strings.HasPrefix(text[i:], "${")
}

// expansionEnd is the index after the $(...), $((...)), ${...}, or backquote
// at i; the bodies of the command substitutions go to out.
func (l *lexer) expansionEnd(i int, out *lexed, inDouble bool) int {
	text := l.text
	switch {
	case text[i] == '`':
		end, body := l.backquote(i + 1)
		out.substitutions = append(out.substitutions, body)
		return end
	case strings.HasPrefix(text[i:], "$((") && l.isArithmetic(i+3):
		end, _ := l.arithmeticEnd(i+3, out)
		return end
	case strings.HasPrefix(text[i:], "$("):
		inner := l.lex(i+2, true)
		out.substitutions = append(out.substitutions, text[i+2:inner.end-1])
		out.removed = append(out.removed, inner.removed...)
		return inner.end
	default:
		return l.braceEnd(i+2, out, inDouble)
	}
}

// doubleQuoted reads "..." from after its opening quote into word, and
// returns the index after it. A backslash escapes $, backquote, ", itself,
// and a newline.
func (l *lexer) doubleQuoted(i int, word *strings.Builder, out *lexed) int {
	text, n := l.text, len(l.text)
	for i < n {
		c := text[i]
		switch {
		case c == '"':
			return i + 1
		case c == '\\' && i+1 < n:
			switch following := text[i+1]; {
			case following == '\n':
				i += 2
			case strings.IndexByte("$`\"\\", following) >= 0:
				word.WriteByte(following)
				i += 2
			default:
				word.WriteByte('\\')
				i++
			}
		case expansionStarts(text, i):
			end := l.expansionEnd(i, out, true)
			word.WriteString(text[i:end])
			i = end
		default:
			word.WriteByte(c)
			i++
		}
	}
	l.fail()
	return 0
}

// ansiCSimple are the one-letter escapes of $'...'.
var ansiCSimple = map[byte]string{
	'a': "\a", 'b': "\b", 'e': "\x1b", 'E': "\x1b", 'f': "\f", 'n': "\n",
	'r': "\r", 't': "\t", 'v': "\v", '\\': "\\", '\'': "'", '"': "\"", '?': "?",
}

// ansiCHex is how many hex digits each of \x, \u, and \U takes at most.
var ansiCHex = map[byte]int{'x': 2, 'u': 4, 'U': 8}

// ansiC reads $'...' from after its opening quote into word, decoding its
// escapes as bash does: the simple ones, \nnn (octal), \xHH, \uHHHH,
// \UHHHHHHHH, and \cX. Others stay as written, and a NUL ends the value. It
// returns the index after the closing quote.
//

func (l *lexer) ansiC(i int, word *strings.Builder) int {
	text, n := l.text, len(l.text)
	var value strings.Builder
	ended := false // past a NUL: the rest is read, then dropped
	for i < n {
		c := text[i]
		if c == '\'' {
			word.WriteString(value.String())
			return i + 1
		}
		if c != '\\' || i+1 == n {
			if !ended {
				value.WriteByte(c)
			}
			i++
			continue
		}
		following := text[i+1]
		var decoded string
		switch digits, isHex := ansiCHex[following]; {
		case ansiCSimple[following] != "":
			decoded, i = ansiCSimple[following], i+2
		case following >= '0' && following <= '7':
			j := i + 1
			for j < min(n, i+4) && text[j] >= '0' && text[j] <= '7' {
				j++
			}
			code, _ := strconv.ParseUint(text[i+1:j], 8, 32)
			decoded, i = string(rune(code&0xFF)), j
		case isHex:
			j := i + 2
			for j < min(n, i+2+digits) && isHexDigit(text[j]) {
				j++
			}
			if j == i+2 {
				decoded, i = "\\"+string(following), i+2
				break
			}
			code, _ := strconv.ParseUint(text[i+2:j], 16, 32)
			if code <= 0x10FFFF && (code < 0xD800 || code > 0xDFFF) {
				decoded = string(rune(code))
			} else {
				decoded = text[i:j]
			}
			i = j
		case following == 'c' && strings.HasPrefix(text[i+2:], "\\\\"):
			decoded, i = "\x1c", i+4 // \c and an escaped backslash: FS
		case following == 'c' && i+2 < n:
			r, size := utf8.DecodeRuneInString(text[i+2:])
			decoded, i = control(r), i+2+size
		default:
			_, size := utf8.DecodeRuneInString(text[i+1:])
			decoded, i = text[i:i+1+size], i+1+size
		}
		if !ended {
			head, _, found := strings.Cut(decoded, "\x00")
			value.WriteString(head)
			ended = found
		}
	}
	l.fail()
	return 0
}

// control is bash's \\cX: X's first byte as a control character (\\c? is
// DEL). bash reads bytes, so the later bytes of a multi-byte X stay as they
// are; here each is U+FFFD (bash runs the npm in $'echo \\c\u0100; npm i').
func control(r rune) string {
	if r == '?' {
		return "\x7f"
	}
	encoded := string(r)
	return string(rune(encoded[0]&0x1F)) + strings.Repeat("\uFFFD", len(encoded)-1)
}

func isHexDigit(c byte) bool {
	return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F')
}

// backquote reads `...` from after its opening backquote: the index after it,
// and its body, where a backslash before a backquote, $, or itself is dropped.
func (l *lexer) backquote(i int) (int, string) {
	text, n := l.text, len(l.text)
	var body strings.Builder
	for i < n {
		c := text[i]
		switch {
		case c == '`':
			return i + 1, body.String()
		case c == '\\' && i+1 < n && strings.IndexByte("`\\$", text[i+1]) >= 0:
			body.WriteByte(text[i+1])
			i += 2
		default:
			body.WriteByte(c)
			i++
		}
	}
	l.fail()
	return 0, ""
}

// isArithmetic reports whether the $(( whose inside starts at i is
// arithmetic: bash takes it as one when the ( after $( closes on a ) that
// another ) follows, and else as $( with a subshell first (it runs the npm in
// $((npm i); :)).
func (l *lexer) isArithmetic(i int) bool {
	_, ok := l.arithmeticEnd(i, &lexed{})
	return ok
}

// arithmeticEnd is the index after the )) of a $(( read from i, and whether
// it is arithmetic at all (isArithmetic); the command substitutions inside
// go to out only when it is.
func (l *lexer) arithmeticEnd(i int, out *lexed) (int, bool) {
	text, n := l.text, len(l.text)
	depth := 1
	found := &lexed{}
	for i < n {
		c := text[i]
		switch {
		case c == '\\':
			i = skipEscaped(text, i)
			continue
		// quotes hide a ) (bash runs the npm in $((: '))'; "npm" i) ))
		case c == '\'':
			k := strings.IndexByte(text[i+1:], '\'')
			if k < 0 {
				l.fail()
			}
			i += 2 + k
			continue
		case c == '"':
			var discard strings.Builder
			i = l.doubleQuoted(i+1, &discard, found)
			continue
		case c == '$' && i+1 < n && text[i+1] == '\'':
			var discard strings.Builder
			i = l.ansiC(i+2, &discard)
			continue
		case expansionStarts(text, i):
			i = l.expansionEnd(i, found, false)
			continue
		case c == '(':
			depth++
		case c == ')':
			depth--
			if depth == 0 {
				if i+1 >= n || text[i+1] != ')' {
					return 0, false
				}
				out.substitutions = append(out.substitutions, found.substitutions...)
				out.removed = append(out.removed, found.removed...)
				return i + 2, true
			}
		}
		i++
	}
	l.fail()
	return 0, false
}

// braceEnd is the index after the } of a ${ read from i; the command
// substitutions inside it go to out. A plain { does not nest (${x:-{} is
// "{"); inside "...", a single quote is a plain character there (bash runs
// the $(...) in "${x:-'$(...)'}", and not unquoted).
func (l *lexer) braceEnd(i int, out *lexed, inDouble bool) int {
	text, n := l.text, len(l.text)
	for i < n {
		c := text[i]
		switch {
		case c == '\\':
			i = skipEscaped(text, i)
			continue
		case c == '\'' && !inDouble:
			k := strings.IndexByte(text[i+1:], '\'')
			if k < 0 {
				l.fail()
			}
			i += 2 + k
			continue
		case c == '"':
			var discard strings.Builder
			i = l.doubleQuoted(i+1, &discard, out)
			continue
		case expansionStarts(text, i):
			i = l.expansionEnd(i, out, inDouble)
			continue
		case c == '}':
			return i + 1
		}
		i++
	}
	l.fail()
	return 0
}
