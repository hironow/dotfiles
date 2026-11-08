package launch_test

import (
	"strings"
	"testing"
	"time"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/fake"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/process"
)

const toolTimeout = 10 * time.Second

// rtkGitStatus is rtk's answer rewriting `git status`, as rtk 1.1.0 gives it.
const rtkGitStatus = `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecisionReason":"RTK auto-rewrite",` +
	`"updatedInput":{"command":"rtk git status"},"permissionDecision":"allow"}}`

const bashPayload = `{"tool_name":"Bash","tool_input":{"command":"git status"},"cwd":"/w"}`

func checkReplay(t *testing.T, m *fake.Machine) {
	t.Helper()
	for _, problem := range m.Done() {
		t.Error(problem)
	}
}

func TestRunRejectsAHookOnAnotherEvent(t *testing.T) {
	for _, args := range [][]string{
		{"claude", "post", "--hook", "command-guard"},
		{"claude", "pre", "--hook", "formatter"},
		{"codex", "post", "--hook", "rtk"},
	} {
		got := run(t, &fake.Machine{}, `{}`, args...)
		if got.exit != 64 || !strings.Contains(got.stderr, "usage: agent-hook") {
			t.Errorf("Run(%q) = %+v, want exit 64 with the usage", args, got)
		}
	}
}

func TestAnOpenHookLetsUnreadableInputGoOnAndRunsNothing(t *testing.T) {
	for _, args := range [][]string{
		{"claude", "pre", "--hook", "rtk"},
		{"codex", "pre", "--hook", "rtk"},
		{"claude", "post", "--hook", "formatter"},
		{"codex", "post", "--hook", "formatter"},
	} {
		m := &fake.Machine{Programs: map[string]process.Program{"rtk": {Path: "/b/rtk"}, "uv": {Path: "/b/uv"}}}
		if got := run(t, m, `{"tool_input":{"file_path":"a.py"}} x`, args...); got != (result{}) {
			t.Errorf("Run(%q) = %+v, want a silent pass", args, got)
		}
		checkReplay(t, m)
	}
}

func TestClaudeRTKForwardsTheStrippedAnswerOfTheRTKOnPATH(t *testing.T) {
	m := &fake.Machine{
		Programs: map[string]process.Program{"rtk": {Path: "/b/rtk"}},
		Cwd:      "/w",
		Replay: []fake.Invocation{{
			Command: process.Command{Path: "/b/rtk", Args: []string{"/b/rtk", "hook", "claude"}, Stdin: []byte(bashPayload), Timeout: toolTimeout},
			Result:  process.Result{Stdout: []byte(rtkGitStatus + "\n")},
		}},
	}
	got := run(t, m, bashPayload, "claude", "pre", "--hook", "rtk")
	want := `{"hookSpecificOutput":{"hookEventName":"PreToolUse","updatedInput":{"command":"rtk git status"}}}` + "\n"
	if got != (result{stdout: want}) {
		t.Errorf("Run = %+v, want stdout %s", got, want)
	}
	checkReplay(t, m)
}

func TestClaudeRTKFindsRTKThroughMiseAndNamesIt(t *testing.T) {
	const found = "/m/installs/rtk/rtk"
	m := &fake.Machine{
		Programs:   map[string]process.Program{"mise": {Path: "/b/mise"}},
		Executable: map[string]bool{found: true},
		Cwd:        "/w",
		Replay: []fake.Invocation{
			{
				Command: process.Command{Path: "/b/mise", Args: []string{"mise", "which", "rtk"}, Timeout: toolTimeout},
				Result:  process.Result{Stdout: []byte(found + "\n")},
			},
			{
				Command: process.Command{Path: found, Args: []string{found, "hook", "claude"}, Stdin: []byte(bashPayload), Timeout: toolTimeout},
				Result:  process.Result{Stdout: []byte(rtkGitStatus)},
			},
		},
	}
	got := run(t, m, bashPayload, "claude", "pre", "--hook", "rtk")
	want := `{"hookSpecificOutput":{"hookEventName":"PreToolUse","updatedInput":{"command":"` + found + ` git status"}}}` + "\n"
	if got != (result{stdout: want}) {
		t.Errorf("Run = %+v, want stdout %s", got, want)
	}
	checkReplay(t, m)
}

func TestClaudeRTKVetoesGitInAnIsolationWorktreeFromTheProcessCwd(t *testing.T) {
	// No cwd in the payload: the process's working directory decides.
	payload := `{"tool_name":"Bash","tool_input":{"command":"git status"}}`
	m := &fake.Machine{
		Programs: map[string]process.Program{"rtk": {Path: "/b/rtk"}},
		Cwd:      "/r/.claude/worktrees/agent-1",
		Replay: []fake.Invocation{{
			Command: process.Command{Path: "/b/rtk", Args: []string{"/b/rtk", "hook", "claude"}, Stdin: []byte(payload), Timeout: toolTimeout},
			Result:  process.Result{Stdout: []byte(rtkGitStatus)},
		}},
	}
	if got := run(t, m, payload, "claude", "pre", "--hook", "rtk"); got != (result{}) {
		t.Errorf("Run = %+v, want nothing printed", got)
	}
	checkReplay(t, m)
}

func TestRTKRunsNothingFoundThroughARelativePATHEntry(t *testing.T) {
	for _, harness := range []string{"claude", "codex"} {
		m := &fake.Machine{Programs: map[string]process.Program{"rtk": {Path: "rtk", Relative: true}}, Cwd: "/w"}
		if got := run(t, m, bashPayload, harness, "pre", "--hook", "rtk"); got != (result{}) {
			t.Errorf("%s: Run = %+v, want a silent pass", harness, got)
		}
		checkReplay(t, m)
		// Not even through mise, in its place.
		m = &fake.Machine{Programs: map[string]process.Program{"mise": {Path: "mise", Relative: true}}, Cwd: "/w"}
		if got := run(t, m, bashPayload, harness, "pre", "--hook", "rtk"); got != (result{}) {
			t.Errorf("%s: Run = %+v, want a silent pass", harness, got)
		}
		checkReplay(t, m)
	}
}

func TestCodexRTKAsksMiseFirstAndNamesItsAnswer(t *testing.T) {
	const found = "/m/installs/rtk/rtk"
	payload := `{"tool_name":"Bash","tool_input":{"command":"git status"}}`
	m := &fake.Machine{
		Programs: map[string]process.Program{"mise": {Path: "/b/mise"}, "rtk": {Path: "/b/rtk"}},
		Replay: []fake.Invocation{
			{
				Command: process.Command{Path: "/b/mise", Args: []string{"/b/mise", "which", "rtk"}, Timeout: toolTimeout},
				Result:  process.Result{Stdout: []byte(found + "\n")},
			},
			{
				Command: process.Command{Path: found, Args: []string{found, "hook", "codex"}, Stdin: []byte(payload), Timeout: toolTimeout},
				Result:  process.Result{Stdout: []byte(rtkGitStatus)},
			},
		},
	}
	got := run(t, m, payload, "codex", "pre", "--hook", "rtk")
	want := `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow",` +
		`"permissionDecisionReason":"RTK auto-rewrite","updatedInput":{"command":"` + found + ` git status"}}}` + "\n"
	if got != (result{stdout: want}) {
		t.Errorf("Run = %+v, want stdout %s", got, want)
	}
	checkReplay(t, m)
}

func TestFormatterRunsRuffAndReportsWhatItStillFinds(t *testing.T) {
	uv := func(args ...string) []string {
		return append([]string{"uv", "run", "--frozen", "--only-group", "lint", "ruff"}, args...)
	}
	m := &fake.Machine{
		Programs: map[string]process.Program{"uv": {Path: "/b/uv"}, "gofmt": {Path: "/b/gofmt"}},
		Files:    map[string]bool{"a.py": true, "b.go": true},
		Replay: []fake.Invocation{
			{Command: process.Command{Path: "/b/uv", Args: uv("format", "a.py")}, Result: process.Result{Stdout: []byte("1 file reformatted\n")}},
			{Command: process.Command{Path: "/b/uv", Args: uv("check", "--fix", "a.py")}, Result: process.Result{Exit: 1}},
			{
				Command: process.Command{Path: "/b/uv", Args: uv("check", "a.py"), Combined: true},
				Result:  process.Result{Stdout: []byte("a.py:1:1: F401 unused\x00\nFound 1 error.\n\n"), Exit: 1},
			},
			{Command: process.Command{Path: "/b/gofmt", Args: []string{"gofmt", "-w", "b.go"}}},
		},
	}
	payload := `{"tool_input":{"command":"*** Begin Patch\n*** Update File: a.py\n*** Add File: b.go\n*** Add File: c.go\n*** End Patch\n"}}`
	got := run(t, m, payload, "codex", "post", "--hook", "formatter")
	want := "ruff still reports issues in a.py:\na.py:1:1: F401 unused\nFound 1 error.\n"
	if got != (result{stderr: want}) {
		t.Errorf("Run = %+v, want stderr %q", got, want)
	}
	checkReplay(t, m)
}

func TestNoPostHookRunsAfterAToolCallThatFailed(t *testing.T) {
	// agy reports a failed tool call in error; the formatter then leaves the
	// file alone, and the answer is agy's pass, {}. The machine would let it
	// format the file: the control, with error "", does.
	machine := func(replay []fake.Invocation) *fake.Machine {
		return &fake.Machine{
			Programs:  map[string]process.Program{"uv": {Path: "/b/uv"}},
			Files:     map[string]bool{"/w/a.py": true},
			RealPaths: map[string]string{"/w/a.py": "/w/a.py", "/w": "/w"},
			Replay:    replay,
		}
	}
	payload := func(failure string) string {
		return `{"toolCall":{"name":"write_file","args":{"Path":"/w/a.py","Content":"x = 1\n"}},` +
			`"workspacePaths":["/w"],"error":` + failure + `}`
	}
	control := machine(ruffIn("/w", "/w/a.py", "x\n"))
	if got := run(t, control, payload(`""`), "agy", "post", "--hook", "formatter"); got.stderr == "" {
		t.Errorf(`the control, error "": Run = %+v, want the file formatted`, got)
	}
	checkReplay(t, control)
	for _, failure := range []string{`"write failed"`, `null`} {
		m := machine(nil)
		if got := run(t, m, payload(failure), "agy", "post", "--hook", "formatter"); got != (result{stdout: "{}\n"}) {
			t.Errorf("error %s: Run = %+v, want {} and nothing run", failure, got)
		}
		checkReplay(t, m)
	}
}

// agyWrite is agy's post payload for a write_file of path, with workspaces.
func agyWrite(path string, workspaces ...string) string {
	return `{"toolCall":{"name":"write_file","args":{"Path":"` + path + `","Content":"x = 1\n"}},` +
		`"workspacePaths":["` + strings.Join(workspaces, `","`) + `"],"error":""}`
}

// ruffIn is the formatter's three ruff commands on path, run in dir.
func ruffIn(dir, path string, report string) []fake.Invocation {
	uv := func(args ...string) []string {
		return append([]string{"uv", "run", "--frozen", "--only-group", "lint", "ruff"}, args...)
	}
	return []fake.Invocation{
		{Command: process.Command{Path: "/b/uv", Args: uv("format", path), Dir: dir}},
		{Command: process.Command{Path: "/b/uv", Args: uv("check", "--fix", path), Dir: dir}},
		{
			Command: process.Command{Path: "/b/uv", Args: uv("check", path), Combined: true, Dir: dir},
			Result:  process.Result{Stdout: []byte(report), Exit: 1},
		},
	}
}

func TestAgyFormatterRunsInTheWorkspaceThatHoldsTheFile(t *testing.T) {
	// agy runs a hook where its hooks.json is, so the formatter runs its
	// commands in the project: the longest workspace holding the file.
	m := &fake.Machine{
		Programs:  map[string]process.Program{"uv": {Path: "/b/uv"}},
		Files:     map[string]bool{"/w/sub/a.py": true},
		RealPaths: map[string]string{"/w/sub/a.py": "/w/sub/a.py", "/w": "/w", "/w/sub": "/w/sub", "/v": "/v"},
		Replay:    ruffIn("/w/sub", "/w/sub/a.py", "a.py:1:1: F401 unused\n"),
	}
	got := run(t, m, agyWrite("/w/sub/a.py", "/v", "/w", "/w/sub"), "agy", "post", "--hook", "formatter")
	want := result{stdout: "{}\n", stderr: "ruff still reports issues in /w/sub/a.py:\na.py:1:1: F401 unused\n"}
	if got != want {
		t.Errorf("Run = %+v, want %+v", got, want)
	}
	checkReplay(t, m)
}

func TestAgyFormatterFollowsASymlinkOutOfTheWorkspace(t *testing.T) {
	// /w/link leads to /other/sub, so /w/link/../a.py is /other/a.py: the
	// file is not in /w, and the formatter runs in /other's git root with the
	// real path. The notice names the path as agy gave it.
	m := &fake.Machine{
		Programs:  map[string]process.Program{"uv": {Path: "/b/uv"}},
		Files:     map[string]bool{"/other/a.py": true},
		RealPaths: map[string]string{"/w/link/../a.py": "/other/a.py", "/w": "/w"},
		Entries:   map[string]bool{"/.git": true, "/other/.git": true},
		Replay:    ruffIn("/other", "/other/a.py", "x\n"),
	}
	got := run(t, m, agyWrite("/w/link/../a.py", "/w"), "agy", "post", "--hook", "formatter")
	if want := (result{stdout: "{}\n", stderr: "ruff still reports issues in /w/link/../a.py:\nx\n"}); got != want {
		t.Errorf("Run = %+v, want %+v", got, want)
	}
	checkReplay(t, m)
}

func TestAgyFormatterFallsBackToTheFilesDirectoryWhenTheGitLookupFails(t *testing.T) {
	m := &fake.Machine{
		Programs:      map[string]process.Program{"gofmt": {Path: "/b/gofmt"}},
		Files:         map[string]bool{"/x/y/a.go": true},
		RealPaths:     map[string]string{"/x/y/a.go": "/x/y/a.go", "/w": "/w"},
		Entries:       map[string]bool{"/.git": true},
		BrokenEntries: map[string]bool{"/x/.git": true},
		Replay: []fake.Invocation{
			{Command: process.Command{Path: "/b/gofmt", Args: []string{"gofmt", "-w", "/x/y/a.go"}, Dir: "/x/y"}},
		},
	}
	if got := run(t, m, agyWrite("/x/y/a.go", "/w"), "agy", "post", "--hook", "formatter"); got != (result{stdout: "{}\n"}) {
		t.Errorf("Run = %+v, want {} and gofmt run in /x/y", got)
	}
	checkReplay(t, m)
}

func TestAgyReadsSuccessWhateverElseThePayloadHolds(t *testing.T) {
	// A number no float64 holds, in a member nothing reads, changes nothing:
	// the call succeeded, and the file is formatted as without it.
	base := agyWrite("/w/a.py", "/w")
	for _, extra := range []string{`1e400`, `-1e400`, `1e-400`, `123456789012345678901234567890`, `[1e400,{"y":-1e400}]`} {
		payload := strings.TrimSuffix(base, "}") + `,"x":` + extra + `}`
		m := &fake.Machine{
			Programs:  map[string]process.Program{"uv": {Path: "/b/uv"}},
			Files:     map[string]bool{"/w/a.py": true},
			RealPaths: map[string]string{"/w/a.py": "/w/a.py", "/w": "/w"},
			Replay:    ruffIn("/w", "/w/a.py", "x\n"),
		}
		got := run(t, m, payload, "agy", "post", "--hook", "formatter")
		if want := (result{stdout: "{}\n", stderr: "ruff still reports issues in /w/a.py:\nx\n"}); got != want {
			t.Errorf("x = %s: Run = %+v, want %+v", extra, got, want)
		}
		checkReplay(t, m)
	}
}

func TestAgyFormatterLeavesAFileItCannotPlace(t *testing.T) {
	// agy's payload has no cwd, so a relative path cannot be placed; nor can
	// a path that does not resolve; nor any path on Windows (2d covers macOS
	// and Linux).
	tests := []struct {
		name    string
		path    string
		windows bool
	}{
		{"a relative path", "a.py", false},
		{"a path that does not resolve", "/w/gone.py", false},
		{"Windows", "/w/a.py", true},
	}
	for _, test := range tests {
		m := &fake.Machine{
			Programs: map[string]process.Program{"uv": {Path: "/b/uv"}},
			Files:    map[string]bool{"a.py": true, "/w/gone.py": true, "/w/a.py": true},
			// EvalSymlinks resolves a relative path too, against the process's
			// directory, which on agy is not the project.
			RealPaths: map[string]string{"/w": "/w", "/w/a.py": "/w/a.py", "a.py": "a.py"},
			Windows:   test.windows,
		}
		if got := run(t, m, agyWrite(test.path, "/w"), "agy", "post", "--hook", "formatter"); got != (result{stdout: "{}\n"}) {
			t.Errorf("%s: Run = %+v, want {} and nothing run", test.name, got)
		}
		checkReplay(t, m)
	}
}

func TestFormatterSkipsAFileWhoseFormatterIsMissingOrRelative(t *testing.T) {
	m := &fake.Machine{
		Programs: map[string]process.Program{"uv": {Path: "uv", Relative: true}},
		Files:    map[string]bool{"a.py": true, "b.go": true},
	}
	if got := run(t, m, `{"tool_input":{"file_path":"a.py\nb.go"}}`, "claude", "post", "--hook", "formatter"); got != (result{}) {
		t.Errorf("Run = %+v, want a silent pass", got)
	}
	checkReplay(t, m)
}

func TestOnWindowsMisesRTKIsRunAndNamedAsPythonsPathDoes(t *testing.T) {
	// The Claude script names Path(found).as_posix(): forward slashes on
	// Windows. Codex's names the drive-letter path with forward slashes too.
	const found = `C:\Users\u\AppData\Local\mise\installs\rtk\1.1.0\rtk.exe`
	const named = "C:/Users/u/AppData/Local/mise/installs/rtk/1.1.0/rtk.exe"
	for _, harness := range []string{"claude", "codex"} {
		miseArgs := []string{"mise", "which", "rtk"}
		programs := map[string]process.Program{"mise": {Path: `C:\bin\mise.exe`}}
		if harness == "codex" {
			miseArgs = []string{`C:\bin\mise.exe`, "which", "rtk"}
		}
		m := &fake.Machine{
			Windows:    true,
			Programs:   programs,
			Executable: map[string]bool{found: true},
			Cwd:        `C:\w`,
			Replay: []fake.Invocation{
				{
					Command: process.Command{Path: `C:\bin\mise.exe`, Args: miseArgs, Timeout: toolTimeout},
					Result:  process.Result{Stdout: []byte(found + "\r\n")},
				},
				{
					Command: process.Command{Path: found, Args: []string{found, "hook", harness}, Stdin: []byte(bashPayload), Timeout: toolTimeout},
					Result:  process.Result{Stdout: []byte(rtkGitStatus)},
				},
			},
		}
		got := run(t, m, bashPayload, harness, "pre", "--hook", "rtk")
		if !strings.Contains(got.stdout, `"command":"`+named+` git status"`) {
			t.Errorf("%s: Run = %+v, want the rewrite naming %s", harness, got, named)
		}
		checkReplay(t, m)
	}
}
