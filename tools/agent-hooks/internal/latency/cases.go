package latency

import (
	"fmt"
	"path/filepath"
	"strings"

	json "github.com/goccy/go-json/v2"
)

// Case describes one payload and the commands that must answer it alike.
// Reset restores FileName to Content before either formatter is timed.
type Case struct {
	Name, Harness, Event, Hook string
	Script, Argument           string
	Command, FileName, Content string
	Reset                      bool
	// Want, Changes, and Stderr say what the answer must show, so that a
	// case times what it is named for: a guard that passes or blocks, rtk's
	// rewrite (not a missing rtk, which every side passes), and a formatter
	// that changes its file (not a missing gofmt) and reports what ruff
	// still finds.
	Want    Want
	Changes bool   // the formatter must change FileName
	Stderr  string // a text stderr must hold
}

// Want is the kind of answer a case must show.
type Want int

const (
	// WantPass is exit 0 and nothing on stdout.
	WantPass Want = iota
	// WantBlock is Claude's block (exit 2, the reason on stderr) or Codex's
	// (exit 0, a deny on stdout, as guard-codex.sh writes it).
	WantBlock
	// WantRewrite is exit 0 and stdout naming the command rtk runs instead.
	WantRewrite
)

// Answer is what a hook command answered.
type Answer struct {
	Exit           int
	Stdout, Stderr string
}

// Shows reports how the answer is not the one the case must show, or nil.
func (c Case) Shows(a Answer) error {
	switch c.Want {
	case WantPass:
		if a.Exit != 0 || a.Stdout != "" {
			return fmt.Errorf("want a pass (exit 0, no stdout), got exit %d and stdout %q", a.Exit, a.Stdout)
		}
	case WantBlock:
		if c.Harness == "codex" {
			if a.Exit != 0 || !strings.Contains(a.Stdout, `"permissionDecision":"deny"`) {
				return fmt.Errorf("want Codex's block (exit 0, a deny on stdout), got exit %d and stdout %q", a.Exit, a.Stdout)
			}
		} else if a.Exit != 2 || a.Stderr == "" {
			return fmt.Errorf("want Claude's block (exit 2, a reason), got exit %d and stderr %q", a.Exit, a.Stderr)
		}
	case WantRewrite:
		if a.Exit != 0 || !strings.Contains(a.Stdout, "rtk "+c.Command) {
			return fmt.Errorf("want rtk's rewrite of %q (is rtk on PATH?), got exit %d and stdout %q", c.Command, a.Exit, a.Stdout)
		}
	}
	if !strings.Contains(a.Stderr, c.Stderr) {
		return fmt.Errorf("want %q on stderr, got %q", c.Stderr, a.Stderr)
	}
	return nil
}

// Cases covers the guards, rtk, and each formatter path on both harnesses.
func Cases() []Case {
	// Build the credential-shaped test value at run time. No credential is used.
	key := strings.Join([]string{"AK", "IA", strings.Repeat("Q", 16)}, "")
	var cases []Case
	for _, harness := range []string{"claude", "codex"} {
		pre := []Case{
			{Hook: "command-guard", Name: "pass", Command: "ls -la"},
			{Hook: "command-guard", Name: "block", Command: "npm ci", Want: WantBlock},
			{Hook: "files-guard", Name: "pass", FileName: "notes.md", Content: "hello\n"},
			{Hook: "files-guard", Name: "block", FileName: "x.yml", Content: "hello\n", Want: WantBlock},
			{Hook: "secrets-guard", Name: "pass", FileName: "notes.md", Content: "hello"},
			{Hook: "secrets-guard", Name: "block", FileName: "notes.md", Content: key, Want: WantBlock},
			{Hook: "rtk", Name: "git-status", Command: "git status", Want: WantRewrite},
		}
		for _, c := range pre {
			c.Harness, c.Event = harness, "pre"
			c.Name = harness + "/pre/" + c.Hook + "/" + c.Name
			c.Script = script(c.Hook)
			if c.Hook == "rtk" {
				c.Script = "rtk-hook-" + harness + ".sh"
			} else if harness == "codex" {
				c.Argument, c.Script = c.Script, "guard-codex.sh"
			}
			cases = append(cases, c)
		}
		for _, file := range []struct {
			extension, name, content, stderr string
			changes                          bool
		}{
			{"md", "notes.md", "hello\n", "", false},
			{"py", "x.py", "x=  [1,2]\nprint(undefined_name)\n", "ruff still reports issues in", true},
			{"go", "x.go", "package main\nfunc main(){println(1)}\n", "", true},
		} {
			cases = append(cases, Case{
				Name: harness + "/post/formatter/" + file.extension, Harness: harness, Event: "post", Hook: "formatter",
				Script: "format-after-edit.sh", FileName: file.name, Content: file.content, Reset: true,
				Changes: file.changes, Stderr: file.stderr,
			})
		}
	}
	return cases
}

func script(hook string) string {
	switch hook {
	case "command-guard":
		return "block-prohibited-commands.sh"
	case "files-guard":
		return "block-prohibited-files.sh"
	case "secrets-guard":
		return "block-secrets.sh"
	default:
		return ""
	}
}

// OldCommand matches the command registered for this harness on this Mac.
func (c Case) OldCommand(claudeHooks, codexHooks string) string {
	dir := claudeHooks
	if c.Harness == "codex" {
		dir = codexHooks
	}
	command := "bash " + quote(filepath.Join(dir, c.Script))
	if c.Argument != "" {
		command += " " + c.Argument
	}
	return command
}

// BinaryCommand selects the same hook through the binary's CLI.
func (c Case) BinaryCommand(binary string) string {
	return quote(binary) + " " + c.Harness + " " + c.Event + " --hook " + c.Hook
}

// quote preserves a path as one literal argument in /bin/sh.
func quote(path string) string {
	return `"` + strings.NewReplacer(`\`, `\\`, `"`, `\"`, "$", `\$`, "`", "\\`").Replace(path) + `"`
}

// Payload uses absolute temporary paths, including in Codex's patches.
func (c Case) Payload(project, files string) ([]byte, error) {
	tool := "Bash"
	input := map[string]any{"command": c.Command}
	path := filepath.Join(files, c.FileName)
	if c.FileName != "" {
		tool = "Write"
		input = map[string]any{"file_path": path, "content": c.Content}
		if c.Harness == "codex" {
			tool = "apply_patch"
			lines := strings.ReplaceAll(strings.TrimSuffix(c.Content, "\n"), "\n", "\n+")
			input = map[string]any{"command": "*** Begin Patch\n*** Add File: " + path + "\n+" + lines + "\n*** End Patch\n"}
		}
	}
	event := "PreToolUse"
	if c.Event == "post" {
		event = "PostToolUse"
	}
	payload := map[string]any{
		"session_id": "latency-session", "transcript_path": filepath.Join(files, "transcript.jsonl"),
		"cwd": project, "hook_event_name": event, "permission_mode": "default",
		"tool_name": tool, "tool_input": input, "tool_use_id": "latency-call",
	}
	if c.Harness == "claude" {
		payload["prompt_id"] = "latency-prompt"
	} else {
		payload["turn_id"], payload["model"] = "latency-turn", "latency-model"
	}
	if c.Event == "post" {
		payload["tool_response"] = map[string]any{"type": "create", "filePath": path, "content": c.Content}
		if c.Harness == "codex" {
			payload["tool_response"] = "Success. Updated the following files:\nA " + path + "\n"
		}
	}
	return json.Marshal(payload)
}
