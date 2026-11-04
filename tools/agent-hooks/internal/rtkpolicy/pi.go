package rtkpolicy

import (
	"strings"
	"unicode/utf8"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
)

// PiCommand is the command Pi's rtk asks `rtk rewrite` about, decided as the
// vendored config/pi/extensions/rtk.ts decides on a bash tool_call: a string
// command that JavaScript's trim does not leave empty, that does not start
// with "rtk " (a space after it), while RTK_DISABLED is not exactly "1".
// A command that holds a NUL passes too: Node's spawn refuses such an
// argument (ERR_INVALID_ARG_VALUE), and rtk.ts's handler catches the error
// and passes. disabled is RTK_DISABLED's value, "" when it is not set (rtk.ts compares
// it with "1" too). ok is false for a pass; the command is returned as
// given, untrimmed.
func PiCommand(command ir.Value, disabled string) (string, bool) {
	if !command.IsString || jsTrim(command.Text) == "" {
		return "", false
	}
	if strings.HasPrefix(command.Text, "rtk ") || disabled == "1" || strings.ContainsRune(command.Text, 0) {
		return "", false
	}
	return command.Text, true
}

// PiRun is how `rtk rewrite` ended, as the shell saw it.
type PiRun struct {
	// Ended is false when rtk did not start, or was killed at the timeout.
	Ended bool
	// Signaled is true when a signal ended rtk.
	Signaled bool
	// Exit is rtk's exit code, when no signal ended it.
	Exit int
	// Stdout is all rtk wrote on stdout, read whole.
	Stdout []byte
}

// PiRewrite is the command rtk.ts sets from `rtk rewrite`'s result: on exit
// 0 (a rewrite) or 3 (an advisory one), stdout as JavaScript trims it, when
// that is not empty and is not the command. ok is false for a pass.
//
// Where it differs from rtk.ts, it passes:
//   - rtk-signal: rtk.ts reads a signal death as code 0 (Node's `code ?? 0`),
//     and would run what a dying rtk printed;
//   - rtk-answer-invalid-utf8: rtk.ts would run U+FFFD in place of bytes that
//     are not UTF-8.
//
// The shell reads stdout whole, so a character that a pipe chunk splits
// stays whole (rtk-split-utf8), and output a descendant writes after rtk
// exits is kept (rtk-late-output); rtk.ts loses both.
func PiRewrite(command string, run PiRun) (string, bool) {
	if !run.Ended || run.Signaled || (run.Exit != 0 && run.Exit != 3) || !utf8.Valid(run.Stdout) {
		return "", false
	}
	rewritten := jsTrim(string(run.Stdout))
	if rewritten == "" || rewritten == command {
		return "", false
	}
	return rewritten, true
}

// jsTrim is ECMAScript's String.prototype.trim.
func jsTrim(text string) string {
	return strings.TrimFunc(text, isJSWhitespace)
}

// isJSWhitespace reports whether trim removes a character: ECMAScript's
// WhiteSpace (TAB, VT, FF, SP, NBSP, ZWNBSP, and the Zs category) and
// LineTerminator (LF, CR, LS, PS).
func isJSWhitespace(r rune) bool {
	switch r {
	case '\t', '\v', '\f', ' ', '\u00a0', '\ufeff', '\u1680', '\u202f', '\u205f', '\u3000',
		'\n', '\r', '\u2028', '\u2029':
		return true
	default:
		return r >= '\u2000' && r <= '\u200a'
	}
}
