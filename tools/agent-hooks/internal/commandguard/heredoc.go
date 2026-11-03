package commandguard

import "strings"

// interpreters run a heredoc fed to them as code (Python's INTERPRETERS).
var interpreters = []string{
	"bash", "bun", "dash", "deno", "ksh", "node", "npx", "perl",
	"python", "python3", "ruby", "sh", "uv", "uvx", "zsh",
}

// splitHeredocs is Python's split_heredocs. It drops every heredoc body from
// the text, and returns the bodies fed to an interpreter, which the guard
// reads as code. Only the first heredoc opened on a line counts; a body ends
// at the line that, stripped, equals the delimiter, or at the end of the text.
func splitHeredocs(text string) (cleaned string, codeBodies []string) {
	var kept, body []string
	var delimiter string
	inBody, isCode := false, false
	for line := range strings.SplitSeq(text, "\n") {
		if inBody {
			if stripPython(line) == delimiter {
				if isCode {
					codeBodies = append(codeBodies, strings.Join(body, "\n"))
				}
				body, inBody = nil, false
				continue
			}
			if isCode {
				body = append(body, line)
			}
			continue
		}
		kept = append(kept, line)
		if d, ok := heredocDelimiter(line); ok {
			delimiter, isCode, inBody = d, mentionsInterpreter(line), true
		}
	}
	if inBody && isCode {
		codeBodies = append(codeBodies, strings.Join(body, "\n"))
	}
	return strings.Join(kept, "\n"), codeBodies
}

// heredocDelimiter is Python's HEREDOC_OPEN_RE.search(line).group(2) for
// `<<-?\s*(['"]?)([A-Za-z_][A-Za-z0-9_]*)\1`: the delimiter of the first
// `<<` that opens a heredoc. Go's regexp has no backreference, so the match is
// spelled out; as in Python, `<<<` (a here-string) also opens one, at its
// second `<`.
func heredocDelimiter(line string) (string, bool) {
	runes := []rune(line)
	for i := 0; i+1 < len(runes); i++ {
		if runes[i] == '<' && runes[i+1] == '<' {
			if delimiter, ok := delimiterAfter(runes, i+2); ok {
				return delimiter, true
			}
		}
	}
	return "", false
}

// delimiterAfter matches what follows `<<` at runes[i]: an optional `-`, Python
// spaces, and a name, bare or between matching quotes. Python's regexp only
// succeeds when it takes the `-`, every space, the quote, and the longest name,
// so this takes each greedily and never backtracks.
func delimiterAfter(runes []rune, i int) (string, bool) {
	if i < len(runes) && runes[i] == '-' {
		i++
	}
	for i < len(runes) && isPythonSpace(runes[i]) {
		i++
	}
	var quote rune
	if i < len(runes) && (runes[i] == '\'' || runes[i] == '"') {
		quote = runes[i]
		i++
	}
	if i == len(runes) || !isNameStart(runes[i]) {
		return "", false
	}
	start := i
	for i < len(runes) && (isNameStart(runes[i]) || (runes[i] >= '0' && runes[i] <= '9')) {
		i++
	}
	if quote != 0 && (i == len(runes) || runes[i] != quote) {
		return "", false
	}
	return string(runes[start:i]), true
}

// isNameStart is [A-Za-z_].
func isNameStart(r rune) bool {
	return r == '_' || (r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z')
}

// mentionsInterpreter is Python's INTERPRETER_WORD_RE.search(line) for
// `(^|[\s;&|(])(<interpreter>)\b`, with Python's Unicode \s and \b (Go's \b is
// ASCII only).
func mentionsInterpreter(line string) bool {
	return containsName([]rune(line), interpreters,
		func(r rune) bool { return isPythonSpace(r) || strings.ContainsRune(";&|(", r) },
		func(r rune) bool { return !isPythonWord(r) })
}
