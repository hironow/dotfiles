package rtkpolicy_test

import (
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/rtkpolicy"
)

// jsWhitespace is every character ECMAScript's String.prototype.trim
// removes: WhiteSpace (incl. the Zs category) and LineTerminator.
var jsWhitespace = []rune{
	'\u0009', '\u000b', '\u000c', '\u0020', '\u00a0', '\ufeff', '\u1680',
	'\u2000', '\u2001', '\u2002', '\u2003', '\u2004', '\u2005', '\u2006',
	'\u2007', '\u2008', '\u2009', '\u200a', '\u202f', '\u205f', '\u3000',
	'\u000a', '\u000d', '\u2028', '\u2029',
}

// notJSWhitespace are characters near that set which trim keeps.
var notJSWhitespace = []rune{'\u0085', '\u200b', '\u180e', '\u2060'}

func TestPiCommandPassesWhatRtkTsSkips(t *testing.T) {
	str := func(text string) ir.Value { return ir.Value{Text: text, IsString: true} }
	type commandCase struct {
		name     string
		command  ir.Value
		disabled string
		ok       bool
	}
	tests := []commandCase{
		{"a command", str("git status"), "", true},
		{"not a string", ir.Value{Text: "1"}, "", false},
		{"empty", str(""), "", false},
		{"rtk and a space", str("rtk git status"), "", false},
		{"rtk alone", str("rtk"), "", true},
		{"rtk and a tab", str("rtk\tgit status"), "", true},
		{"a space before rtk", str(" rtk git status"), "", true},
		// Node's spawn refuses an argument that holds a NUL; rtk.ts passes.
		{"a NUL", str("a\x00b"), "", false},
		{"RTK_DISABLED=1", str("git status"), "1", false},
		{"RTK_DISABLED=0", str("git status"), "0", true},
		{"RTK_DISABLED=' 1'", str("git status"), " 1", true},
		{"RTK_DISABLED=true", str("git status"), "true", true},
		{"RTK_DISABLED empty", str("git status"), "", true},
	}
	for _, space := range jsWhitespace {
		tests = append(tests, commandCase{"only " + string(space), str(string(space) + string(space)), "", false})
	}
	for _, kept := range notJSWhitespace {
		tests = append(tests, commandCase{"only kept " + string(kept), str(string(kept)), "", true})
	}
	for _, test := range tests {
		got, ok := rtkpolicy.PiCommand(test.command, test.disabled)
		if ok != test.ok || (ok && got != test.command.Text) {
			t.Errorf("%s: PiCommand = %q, %v; want ok %v and the command as given", test.name, got, ok, test.ok)
		}
	}
}

func TestPiRewriteReadsRtkRewriteAsRtkTsDoes(t *testing.T) {
	ended := func(exit int, stdout string) rtkpolicy.PiRun {
		return rtkpolicy.PiRun{Ended: true, Exit: exit, Stdout: []byte(stdout)}
	}
	tests := []struct {
		name string
		run  rtkpolicy.PiRun
		want string // "" for a pass
	}{
		{"a rewrite", ended(0, "rtk git status\n"), "rtk git status"},
		{"an advisory rewrite", ended(3, "rtk git status"), "rtk git status"},
		{"no rtk equivalent", ended(1, ""), ""},
		{"another exit", ended(2, "rtk x"), ""},
		{"not found", ended(127, "rtk x"), ""},
		{"empty stdout", ended(0, ""), ""},
		{"the command itself", ended(0, "git status\n"), ""},
		{"a multi-line rewrite", ended(0, "\nrtk a\nrtk b\n\n"), "rtk a\nrtk b"},
		{"a timeout or no start", rtkpolicy.PiRun{Stdout: []byte("rtk git status")}, ""},
		// rtk-signal: rtk.ts reads a signal death as code 0.
		{"a signal", rtkpolicy.PiRun{Ended: true, Signaled: true, Stdout: []byte("rtk git status")}, ""},
		// rtk-answer-invalid-utf8: rtk.ts would run U+FFFD in its place.
		{"invalid UTF-8", ended(0, "rtk \xff git"), ""},
		{"a split character, read whole", ended(0, "rtk echo 雪\n"), "rtk echo 雪"},
		// trim keeps a NUL, as rtk.ts does.
		{"a NUL kept", ended(0, "\x00rtk git status\x00"), "\x00rtk git status\x00"},
	}
	for _, space := range jsWhitespace {
		tests = append(tests, struct {
			name string
			run  rtkpolicy.PiRun
			want string
		}{"trims " + string(space), ended(0, string(space)+"rtk git status"+string(space)), "rtk git status"})
	}
	for _, kept := range notJSWhitespace {
		tests = append(tests, struct {
			name string
			run  rtkpolicy.PiRun
			want string
		}{"keeps " + string(kept), ended(0, string(kept)+"rtk git status"+string(kept)), string(kept) + "rtk git status" + string(kept)})
	}
	for _, test := range tests {
		got, ok := rtkpolicy.PiRewrite("git status", test.run)
		if ok != (test.want != "") || got != test.want {
			t.Errorf("%s: PiRewrite = %q, %v; want %q", test.name, got, ok, test.want)
		}
	}
}
