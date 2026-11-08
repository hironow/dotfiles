package selftest

import (
	"strings"
	"time"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/fake"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/process"
)

// Case is one payload the binary must answer exactly so, on its own
// in-memory machine.
type Case struct {
	Name    string
	Args    []string // the binary's arguments: harness, event, --hook, id
	Payload string
	// Machine is a fresh in-memory machine for one run: the programs the hook
	// finds, and what each answers (replayed, never run).
	Machine func() *fake.Machine
}

// answer is what the binary writes for a case.
type answer struct {
	exit           int
	stdout, stderr string
}

// rtkTimeout is the rtk hook's timeout for rtk itself (launch's rtkTimeout).
const rtkTimeout = 10 * time.Second

// rtkGitStatus is rtk's answer rewriting `git status`, as rtk 1.1.0 gives it.
const rtkGitStatus = `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecisionReason":"RTK auto-rewrite",` +
	`"updatedInput":{"command":"rtk git status"},"permissionDecision":"allow"}}`

// key is a credential-shaped text, built from parts so that no credential
// shape appears in the source.
func key() string { return "AK" + "IA" + strings.Repeat("Q", 16) }

func claudePre(tool, input string) string {
	return `{"session_id":"s","transcript_path":"/t.jsonl","cwd":"/w","permission_mode":"default",` +
		`"hook_event_name":"PreToolUse","tool_name":"` + tool + `","tool_input":` + input + `,"tool_use_id":"c"}`
}

func claudePost(tool, input string) string {
	return `{"session_id":"s","transcript_path":"/t.jsonl","cwd":"/w","permission_mode":"default",` +
		`"hook_event_name":"PostToolUse","tool_name":"` + tool + `","tool_input":` + input +
		`,"tool_response":{},"tool_use_id":"c"}`
}

func codexPre(tool, input string) string {
	return `{"session_id":"s","turn_id":"t","transcript_path":null,"cwd":"/w","hook_event_name":"PreToolUse",` +
		`"model":"m","permission_mode":"default","tool_name":"` + tool + `","tool_input":` + input + `,"tool_use_id":"c"}`
}

func codexPost(tool, input string) string {
	return `{"session_id":"s","turn_id":"t","transcript_path":null,"cwd":"/w","hook_event_name":"PostToolUse",` +
		`"model":"m","permission_mode":"default","tool_name":"` + tool + `","tool_input":` + input +
		`,"tool_response":"ok","tool_use_id":"c"}`
}

func patch(path, line string) string {
	return `{"command":"*** Begin Patch\n*** Add File: ` + path + `\n+` + line + `\n*** End Patch\n"}`
}

// noProgram is a machine on which no program is found.
func noProgram() *fake.Machine { return &fake.Machine{Cwd: "/w"} }

// rtkOnPath answers `rtk hook <harness>` with rtk's rewrite of git status.
func rtkOnPath(harness, payload string) func() *fake.Machine {
	return func() *fake.Machine {
		program := "/b/rtk"
		args := []string{program, "hook", harness}
		return &fake.Machine{
			Programs: map[string]process.Program{"rtk": {Path: program}},
			Cwd:      "/w",
			Replay: []fake.Invocation{{
				Command: process.Command{Path: program, Args: args, Stdin: []byte(payload), Timeout: rtkTimeout},
				Result:  process.Result{Stdout: []byte(rtkGitStatus + "\n")},
			}},
		}
	}
}

// ruffReports answers the formatter's three ruff runs on path, the last
// still finding an undefined name.
func ruffReports(path string) func() *fake.Machine {
	return func() *fake.Machine {
		uv := func(args ...string) []string {
			return append([]string{"uv", "run", "--frozen", "--only-group", "lint", "ruff"}, args...)
		}
		return &fake.Machine{
			Programs: map[string]process.Program{"uv": {Path: "/b/uv"}},
			Files:    map[string]bool{path: true},
			Cwd:      "/w",
			Replay: []fake.Invocation{
				{Command: process.Command{Path: "/b/uv", Args: uv("format", path)}},
				{Command: process.Command{Path: "/b/uv", Args: uv("check", "--fix", path)}},
				{
					Command: process.Command{Path: "/b/uv", Args: uv("check", path), Combined: true},
					Result:  process.Result{Stdout: []byte(path + ":1:7: F821 Undefined name `x`\nFound 1 error.\n"), Exit: 1},
				},
			},
		}
	}
}

// Cases are the binary's own cases: on Claude and Codex, each guard on a
// pass and a block, rtk forwarding a rewrite, and the formatter's notice.
func Cases() []Case {
	bash := func(command string) string { return `{"command":"` + command + `"}` }
	write := func(path, content string) string {
		return `{"file_path":"` + path + `","content":"` + content + `"}`
	}
	cases := []Case{
		{Name: "claude/pre/command-guard/pass", Args: args("claude", "pre", "command-guard"), Payload: claudePre("Bash", bash("ls -la")), Machine: noProgram},
		{Name: "claude/pre/command-guard/block", Args: args("claude", "pre", "command-guard"), Payload: claudePre("Bash", bash("npm ci")), Machine: noProgram},
		{Name: "claude/pre/files-guard/pass", Args: args("claude", "pre", "files-guard"), Payload: claudePre("Write", write("/w/notes.md", "hello")), Machine: noProgram},
		{Name: "claude/pre/files-guard/block", Args: args("claude", "pre", "files-guard"), Payload: claudePre("Write", write("/w/x.yml", "a: 1")), Machine: noProgram},
		{Name: "claude/pre/secrets-guard/pass", Args: args("claude", "pre", "secrets-guard"), Payload: claudePre("Write", write("/w/notes.md", "hello")), Machine: noProgram},
		{Name: "claude/pre/secrets-guard/block", Args: args("claude", "pre", "secrets-guard"), Payload: claudePre("Write", write("/w/notes.md", key())), Machine: noProgram},
		{Name: "claude/post/formatter/notice", Args: args("claude", "post", "formatter"), Payload: claudePost("Write", write("/w/a.py", "print(x)")), Machine: ruffReports("/w/a.py")},
		{Name: "codex/pre/command-guard/pass", Args: args("codex", "pre", "command-guard"), Payload: codexPre("Bash", bash("ls -la")), Machine: noProgram},
		{Name: "codex/pre/command-guard/block", Args: args("codex", "pre", "command-guard"), Payload: codexPre("Bash", bash("npm ci")), Machine: noProgram},
		{Name: "codex/pre/files-guard/pass", Args: args("codex", "pre", "files-guard"), Payload: codexPre("apply_patch", patch("notes.md", "hello")), Machine: noProgram},
		{Name: "codex/pre/files-guard/block", Args: args("codex", "pre", "files-guard"), Payload: codexPre("apply_patch", patch("x.yml", "a: 1")), Machine: noProgram},
		{Name: "codex/pre/secrets-guard/pass", Args: args("codex", "pre", "secrets-guard"), Payload: codexPre("apply_patch", patch("notes.md", "hello")), Machine: noProgram},
		{Name: "codex/pre/secrets-guard/block", Args: args("codex", "pre", "secrets-guard"), Payload: codexPre("apply_patch", patch("notes.md", key())), Machine: noProgram},
		{Name: "codex/post/formatter/notice", Args: args("codex", "post", "formatter"), Payload: codexPost("apply_patch", patch("/w/a.py", "print(x)")), Machine: ruffReports("/w/a.py")},
	}
	claudeRTK := claudePre("Bash", bash("git status"))
	codexRTK := codexPre("Bash", bash("git status"))
	cases = append(cases,
		Case{Name: "claude/pre/rtk/forward", Args: args("claude", "pre", "rtk"), Payload: claudeRTK, Machine: rtkOnPath("claude", claudeRTK)},
		Case{Name: "codex/pre/rtk/forward", Args: args("codex", "pre", "rtk"), Payload: codexRTK, Machine: rtkOnPath("codex", codexRTK)},
	)
	return cases
}

func args(harness, event, hook string) []string {
	return []string{harness, event, "--hook", hook}
}
