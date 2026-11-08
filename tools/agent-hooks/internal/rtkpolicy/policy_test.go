package rtkpolicy_test

import (
	"strings"
	"testing"

	"github.com/goccy/go-json/jsontext"
	json "github.com/goccy/go-json/v2"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/rtkpolicy"
)

// The Python tests these mirror: tests/unit/test_rtk_hook_respond.py and
// tests/unit/test_rtk_hook_codex.py. Each case names its Python test, which
// tests/unit/test_tool_hooks_corpus.py looks for here.

const (
	plain    = "/home/u/repo"
	worktree = "/home/u/repo/.claude/worktrees/agent-1"
	miseRTK  = "C:/Users/u/AppData/Local/mise/installs/rtk/0.50.0/rtk.exe"
	realRTK  = miseRTK
)

// answer is rtk's hook answer for a rewrite, as rtk 1.1.0 gives it.
func answer(command string) jsontext.Value {
	return jsontext.Value(`{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow",` +
		`"permissionDecisionReason":"RTK auto-rewrite","updatedInput":{"command":` + quote(command) + `}}}`)
}

func quote(s string) string {
	b, err := json.Marshal(s)
	if err != nil {
		panic(err)
	}
	return string(b)
}

// canonical is the RFC 8785 form of a JSON text: equal for equal values.
func canonical(t *testing.T, text string) string {
	t.Helper()
	v := jsontext.Value(text)
	if err := v.Canonicalize(); err != nil {
		t.Fatalf("canonicalize %s: %v", text, err)
	}
	return string(v)
}

// stripped is what the Claude script prints for a rewrite: rtk's
// hookEventName and updatedInput, nothing else.
func stripped(command string) string {
	return `{"hookSpecificOutput":{"hookEventName":"PreToolUse","updatedInput":{"command":` + quote(command) + `}}}`
}

func TestClaudeForwardsWhatTheClaudeScriptPrints(t *testing.T) {
	cases := []struct {
		python  string // the Python test this mirrors
		answer  jsontext.Value
		cwd     string
		offPath string
		want    string // "" when nothing is printed
	}{
		{"test_a_rewrite_is_forwarded_without_the_approval", answer("rtk git status"), plain, "", stripped("rtk git status")},
		{"test_git_is_vetoed_in_an_isolation_worktree", answer("rtk git status"), worktree, "", ""},
		{"test_git_is_vetoed_in_an_isolation_worktree", answer("cd x && rtk git log"), worktree, "", ""},
		{"test_other_commands_keep_rtk_in_a_worktree", answer("rtk ls"), worktree, "", stripped("rtk ls")},
		{"test_mises_rtk_is_named_in_a_plain_rewrite", answer("rtk read a.txt"), plain, miseRTK, stripped(miseRTK + " read a.txt")},
		{"test_mises_rtk_drops_any_other_rewrite", answer("rtk ls && rtk git status"), plain, miseRTK, ""},
		{"test_an_answer_without_a_rewrite_prints_nothing", jsontext.Value(`{}`), plain, "", ""},
		{"test_an_answer_without_a_rewrite_prints_nothing", jsontext.Value(`{"hookSpecificOutput":"x"}`), plain, "", ""},
		{
			"test_an_answer_without_a_rewrite_prints_nothing",
			jsontext.Value(`{"hookSpecificOutput":{"hookEventName":"PreToolUse"}}`), plain, "", "",
		},
		// The veto comes before mise's launcher and reads rtk's own rewrite.
		{"veto before the launcher", answer("rtk git status"), worktree, miseRTK, ""},
		{"a launcher that needs quoting", answer("rtk ls"), plain, "/opt/my tools/rtk", stripped("'/opt/my tools/rtk' ls")},
		{
			"everything but hookEventName and updatedInput is dropped, whatever rtk adds",
			jsontext.Value(`{"continue":true,"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny",` +
				`"additionalContext":"x","updatedInput":{"command":"rtk ls","timeout":5,"description":"d"}}}`),
			plain, "",
			`{"hookSpecificOutput":{"hookEventName":"PreToolUse","updatedInput":{"command":"rtk ls","timeout":5,"description":"d"}}}`,
		},
		{
			"rtk's hookEventName is kept, whatever it is",
			jsontext.Value(`{"hookSpecificOutput":{"hookEventName":null,"updatedInput":{"command":"rtk ls"}}}`),
			plain, "", `{"hookSpecificOutput":{"hookEventName":null,"updatedInput":{"command":"rtk ls"}}}`,
		},
		{
			"an absent hookEventName is PreToolUse",
			jsontext.Value(`{"hookSpecificOutput":{"updatedInput":{"command":"rtk ls"}}}`),
			plain, "", stripped("rtk ls"),
		},
		{
			// The script prints an updatedInput without a string command as it is.
			"an updatedInput without a command is forwarded",
			jsontext.Value(`{"hookSpecificOutput":{"updatedInput":{"description":"x"}}}`),
			worktree, miseRTK, `{"hookSpecificOutput":{"hookEventName":"PreToolUse","updatedInput":{"description":"x"}}}`,
		},
		{
			"a command that is not a string is not vetoed or named",
			jsontext.Value(`{"hookSpecificOutput":{"updatedInput":{"command":["rtk git status"]}}}`),
			worktree, miseRTK, `{"hookSpecificOutput":{"hookEventName":"PreToolUse","updatedInput":{"command":["rtk git status"]}}}`,
		},
		{"an updatedInput that is not an object", jsontext.Value(`{"hookSpecificOutput":{"updatedInput":"rtk ls"}}`), plain, "", ""},
		{"an answer that is not an object", jsontext.Value(`[1]`), plain, "", ""},
	}
	for _, c := range cases {
		got, ok := rtkpolicy.Claude(c.answer, c.cwd, c.offPath)
		switch {
		case c.want == "" && ok:
			t.Errorf("%s: Claude printed %s, want nothing", c.python, got)
		case c.want != "" && !ok:
			t.Errorf("%s: Claude printed nothing, want %s", c.python, c.want)
		case c.want != "" && canonical(t, string(got)) != canonical(t, c.want):
			t.Errorf("%s: Claude = %s, want %s", c.python, got, c.want)
		}
	}
}

func TestTheVetoFindsRTKBeforeGitAnywhere(t *testing.T) {
	// Each case was checked against the script's _is_vetoed_rewrite.
	cases := []struct {
		rewrite string
		vetoed  bool
	}{
		{"rtk git status", true},
		{"cd x && rtk git log", true},
		{"FOO=1 rtk git status", true},
		{"rtk --ultra-compact git status", true},
		{"rtk -u -v git status", true},
		{"/opt/rtk/bin/rtk git status", true},
		// shlex reads the backslashes as escapes: the word is C:toolsrtk.
		{`C:\tools\rtk git status`, false},
		{"rtk /usr/bin/git status", true},
		{"rtk ls && git status", false},
		{"rtk ls git", false},
		{"rtk read git", false},
		{"echo rtk git", true},
		{"rtk;git status", false},
		{"rtk #c\ngit status", false},
		{"rtk 'git' status", true},
		{"rtk \"unbalanced git", true},
		{"rtk \"unbalanced ls", false},
		{"rtk ls \\", false},
		{"git status", false},
		{"rtkgit status", false},
	}
	for _, c := range cases {
		if _, ok := rtkpolicy.Claude(answer(c.rewrite), worktree, ""); ok == c.vetoed {
			t.Errorf("rewrite %q in a worktree: printed %v, want vetoed %v", c.rewrite, ok, c.vetoed)
		}
	}
}

func TestOnlyAnIsolationWorktreeVetoes(t *testing.T) {
	cases := []struct {
		cwd    string
		vetoed bool
	}{
		{worktree, true},
		{"/home/u/repo/.claude/worktrees", true},
		{"/home/u/repo/.claude/worktrees/", true},
		{`C:\repo\.claude\worktrees\a`, true},
		{"/home/u/repo/.claude/worktreesX", false},
		{"/home/u/repo/claude/worktrees/a", false},
		{"", false},
		{plain, false},
	}
	for _, c := range cases {
		if _, ok := rtkpolicy.Claude(answer("rtk git status"), c.cwd, ""); ok == c.vetoed {
			t.Errorf("cwd %q: printed %v, want vetoed %v", c.cwd, ok, c.vetoed)
		}
	}
}

func TestCodexForwardsRTKsAnswerNamingTheRealBinary(t *testing.T) {
	cases := []struct {
		python   string
		command  string
		launcher string
		named    string // "" when nothing is printed
	}{
		{"test_only_a_plain_rewrite_with_an_unquoted_path_is_named", "rtk ls -la", realRTK, realRTK + " ls -la"},
		{"test_only_a_plain_rewrite_with_an_unquoted_path_is_named", "rtk git status", `C:\Users\u\rtk.exe`, "C:/Users/u/rtk.exe git status"},
		{"test_only_a_plain_rewrite_with_an_unquoted_path_is_named", "rtk ls && rtk git status", realRTK, ""},
		{"test_only_a_plain_rewrite_with_an_unquoted_path_is_named", "FOO=1 rtk git log", realRTK, ""},
		{"test_only_a_plain_rewrite_with_an_unquoted_path_is_named", "rtk ls", "C:/Users/John Doe/rtk.exe", ""},
		{"test_only_a_plain_rewrite_with_an_unquoted_path_is_named", "rtk ls", `/opt/tools\local/bin/rtk`, ""},
		{"test_the_answer_keeps_codexs_allow_and_names_the_binary", "rtk ls -la", realRTK, realRTK + " ls -la"},
		{"test_anything_else_forwards_nothing", "rtk ls && rtk git status", realRTK, ""},
	}
	for _, c := range cases {
		got, ok := rtkpolicy.Codex(answer(c.command), c.launcher)
		if c.named == "" {
			if ok {
				t.Errorf("%s: Codex(%q, %q) printed %s, want nothing", c.python, c.command, c.launcher, got)
			}
			continue
		}
		if !ok || canonical(t, string(got)) != canonical(t, string(answer(c.named))) {
			t.Errorf("%s: Codex(%q, %q) = %s, %v; want rtk's answer naming %q", c.python, c.command, c.launcher, got, ok, c.named)
		}
	}
	for _, malformed := range []string{`{}`, `{"hookSpecificOutput":"x"}`, `{"hookSpecificOutput":{"updatedInput":{}}}`, `[1]`} {
		if got, ok := rtkpolicy.Codex(jsontext.Value(malformed), realRTK); ok {
			t.Errorf("test_anything_else_forwards_nothing: Codex(%s) printed %s", malformed, got)
		}
	}
}

func TestCodexKeepsRTKsDecisionAndEverythingElse(t *testing.T) {
	// A deny stays a deny: only the command changes.
	for _, decision := range []string{`"allow"`, `"deny"`, `"ask"`, `null`} {
		in := `{"continue":true,"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":` + decision +
			`,"permissionDecisionReason":"x","additionalContext":"y","updatedInput":{"command":"rtk ls","timeout":5}}}`
		want := `{"continue":true,"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":` + decision +
			`,"permissionDecisionReason":"x","additionalContext":"y","updatedInput":{"command":"/r/rtk ls","timeout":5}}}`
		got, ok := rtkpolicy.Codex(jsontext.Value(in), "/r/rtk")
		if !ok || canonical(t, string(got)) != canonical(t, want) {
			t.Errorf("decision %s: Codex = %s, %v; want %s", decision, got, ok, want)
		}
	}
}

func TestEditedAnswersKeepEveryOtherValueAsWritten(t *testing.T) {
	// Values the hook does not touch keep their text: no float rounding.
	in := `{"hookSpecificOutput":{"updatedInput":{"command":"rtk ls","n":12345678901234567890,"f":1e2}},"x":1.50}`
	got, ok := rtkpolicy.Codex(jsontext.Value(in), "/r/rtk")
	if !ok {
		t.Fatal("no answer")
	}
	for _, text := range []string{"12345678901234567890", "1e2", "1.50"} {
		if !strings.Contains(string(got), text) {
			t.Errorf("Codex = %s, lost %s", got, text)
		}
	}
}

func TestCodexAndClaudeKeepTheSameRewrites(t *testing.T) {
	// test_codex_and_claude_keep_the_same_rewrites: one rule in two hooks.
	for _, command := range []string{"rtk ls -la", "rtk read a.txt", "rtk ls && rtk git status", "cat rtk", "rtk"} {
		_, keptByCodex := rtkpolicy.Codex(answer(command), realRTK)
		_, keptByClaude := rtkpolicy.Claude(answer(command), plain, realRTK)
		if keptByCodex != keptByClaude {
			t.Errorf("%q: kept by Codex %v, by Claude %v", command, keptByCodex, keptByClaude)
		}
	}
}

func TestCodexLauncherPrefersTheRealBinaryAndNeverAShim(t *testing.T) {
	// test_the_real_binary_is_preferred_and_a_shim_never_used
	cases := []struct {
		miseAnswer, onPath, want string
	}{
		{realRTK, "C:/Users/u/AppData/Local/mise/shims/rtk.exe", realRTK},
		{"", "/home/u/.local/bin/rtk", "/home/u/.local/bin/rtk"},
		{"", "C:/Users/u/AppData/Local/mise/shims/rtk.exe", ""},
		{"", `C:\Users\u\AppData\Local\mise\SHIMS\rtk.exe`, ""},
		{"", "", ""},
		{"", "/home/u/shims/rtk", ""},
		{"", "/home/u/Shims/rtk", ""},
		{"", "rtk", "rtk"},
		{"", `/home/u\shims/rtk`, `/home/u\shims/rtk`},
	}
	for _, c := range cases {
		if got := rtkpolicy.CodexLauncher(c.miseAnswer, c.onPath); got != c.want {
			t.Errorf("CodexLauncher(%q, %q) = %q, want %q", c.miseAnswer, c.onPath, got, c.want)
		}
	}
}

func TestQuoteIsPythonsShlexQuote(t *testing.T) {
	// Python 3.14's answers.
	cases := map[string]string{
		"":                       "''",
		"a":                      "a",
		"a b":                    "'a b'",
		"a'b":                    `'a'"'"'b'`,
		"/x/y-z_1.2:3,4@5%6+7=8": "/x/y-z_1.2:3,4@5%6+7=8",
		"é":                      "'é'",
		"\t":                     "'\t'",
		"a\nb":                   "'a\nb'",
		"-x":                     "-x",
		"a~b":                    "'a~b'",
		"a*b":                    "'a*b'",
	}
	for in, want := range cases {
		if got := rtkpolicy.Quote(in); got != want {
			t.Errorf("Quote(%q) = %q, want %q", in, got, want)
		}
	}
}

func TestAsPosixIsPurePosixPath(t *testing.T) {
	// Python 3.14's PurePosixPath(s).as_posix().
	cases := map[string]string{
		"/a//b/./c/": "/a/b/c",
		"//a/b":      "//a/b",
		"///a":       "/a",
		"a/./b":      "a/b",
		"./a":        "a",
		".":          ".",
		"a/..//b":    "a/../b",
		"/":          "/",
		"//":         "//",
		"///":        "/",
		"a/":         "a",
		`C:\x\rtk`:   `C:\x\rtk`,
		"/a/.":       "/a",
		"/./a":       "/a",
		"//./a":      "//a",
		"a//":        "a",
	}
	for in, want := range cases {
		if got := rtkpolicy.AsPosix(in); got != want {
			t.Errorf("AsPosix(%q) = %q, want %q", in, got, want)
		}
	}
}

func TestVetoCwdReadsTheCwdAsTheClaudeScriptDoes(t *testing.T) {
	// payload.get("cwd") or os.getcwd(); then "" unless it is a string.
	str := func(text string) ir.Value { return ir.Value{Text: text, IsString: true} }
	raw := func(text string) ir.Value { return ir.Value{Text: text} }
	const process = "/proc/cwd"
	cases := []struct {
		name    string
		value   ir.Value
		present bool
		want    string
	}{
		{"a string", str("/a"), true, "/a"},
		{"absent (or null, or false)", ir.Value{}, false, process},
		{"an empty string", str(""), true, process},
		{"zero", raw("0"), true, process},
		{"negative zero", raw("-0"), true, process},
		{"zero as a float", raw("0.0e5"), true, process},
		{"a float that underflows to zero", raw("1e-400"), true, process},
		{"an empty array", raw("[]"), true, process},
		{"an empty object", raw("{}"), true, process},
		{"a number", raw("1"), true, ""},
		{"true", raw("true"), true, ""},
		{"an array", raw(`["/a"]`), true, ""},
		{"an object", raw(`{"a":1}`), true, ""},
		{"a huge number", raw("1e400"), true, ""},
	}
	for _, c := range cases {
		if got := rtkpolicy.VetoCwd(c.value, c.present, process); got != c.want {
			t.Errorf("%s: VetoCwd = %q, want %q", c.name, got, c.want)
		}
	}
}

func TestRTKsAnswerIsNotMutated(t *testing.T) {
	// test_rtks_answer_is_not_mutated: the hook edits a copy.
	for _, edit := range []func(jsontext.Value) (jsontext.Value, bool){
		func(a jsontext.Value) (jsontext.Value, bool) { return rtkpolicy.Claude(a, plain, miseRTK) },
		func(a jsontext.Value) (jsontext.Value, bool) { return rtkpolicy.Codex(a, realRTK) },
	} {
		given := answer("rtk read a.txt")
		before := string(given)
		if _, ok := edit(given); !ok || string(given) != before {
			t.Errorf("rtk's answer changed: %s, want %s", given, before)
		}
	}
}

func TestAsPosixWindowsIsPureWindowsPath(t *testing.T) {
	// Python 3.14's PureWindowsPath(s).as_posix(): what the Claude script's
	// Path(...).as_posix() gives on Windows.
	cases := map[string]string{
		`C:\Users\u\rtk.exe`:       "C:/Users/u/rtk.exe",
		"C:/Users/u/rtk.exe":       "C:/Users/u/rtk.exe",
		`C:\a\.\b\`:                "C:/a/b",
		`C:\a\..\b`:                "C:/a/../b",
		`C:\\a\\\\b`:               "C:/a/b",
		`\\server\share\x\rtk.exe`: "//server/share/x/rtk.exe",
		`\\server\share`:           "//server/share/",
		`C:rtk.exe`:                "C:rtk.exe",
		`\rtk.exe`:                 "/rtk.exe",
		"rtk.exe":                  "rtk.exe",
		`.\rtk.exe`:                "rtk.exe",
		`a\b`:                      "a/b",
		"C:":                       "C:",
		`C:\`:                      "C:/",
		`C:\a/b\c`:                 "C:/a/b/c",
		`\\?\C:\x\rtk.exe`:         "//?/C:/x/rtk.exe",
		"//server/share/x":         "//server/share/x",
		`c:\x\Rtk.EXE`:             "c:/x/Rtk.EXE",
		`C:\x\.`:                   "C:/x",
		".":                        ".",
		`\\?\UNC\server\share\x`:   "//?/UNC/server/share/x",
	}
	for in, want := range cases {
		if got := rtkpolicy.AsPosixWindows(in); got != want {
			t.Errorf("AsPosixWindows(%q) = %q, want %q", in, got, want)
		}
	}
}
