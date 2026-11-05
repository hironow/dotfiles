package selftest

// answers are what each case must answer: the exit code, stdout, and stderr.
// They are the binary's answers when the cases were written, and each
// guard's reason is the old scripts' own text.
var answers = map[string]answer{
	"claude/pre/command-guard/pass":  {exit: 0, stdout: "", stderr: ""},
	"claude/pre/command-guard/block": {exit: 2, stdout: "", stderr: "BLOCKED: Node package management is 'bun' only. Do not use npm/yarn/pnpm (including 'corepack pnpm').\n"},
	"claude/pre/files-guard/pass":    {exit: 0, stdout: "", stderr: ""},
	"claude/pre/files-guard/block":   {exit: 2, stdout: "", stderr: "BLOCKED: 'x.yml' uses '.yml'. This project uses '.yaml' exclusively. Rename to 'x.yaml'.\n"},
	"claude/pre/secrets-guard/pass":  {exit: 0, stdout: "", stderr: ""},
	"claude/pre/secrets-guard/block": {exit: 2, stdout: "", stderr: "BLOCKED: content looks like a live secret (API key / token / private key). Do not commit secrets; use a secret manager and reference via env var.\n"},
	"claude/post/formatter/notice":   {exit: 0, stdout: "", stderr: "ruff still reports issues in /w/a.py:\n/w/a.py:1:7: F821 Undefined name `x`\nFound 1 error.\n"},
	"codex/pre/command-guard/pass":   {exit: 0, stdout: "", stderr: ""},
	"codex/pre/command-guard/block":  {exit: 0, stdout: "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"BLOCKED: Node package management is 'bun' only. Do not use npm/yarn/pnpm (including 'corepack pnpm').\"}}\n", stderr: ""},
	"codex/pre/files-guard/pass":     {exit: 0, stdout: "", stderr: ""},
	"codex/pre/files-guard/block":    {exit: 0, stdout: "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"BLOCKED: 'x.yml' uses '.yml'. This project uses '.yaml' exclusively. Rename to 'x.yaml'.\"}}\n", stderr: ""},
	"codex/pre/secrets-guard/pass":   {exit: 0, stdout: "", stderr: ""},
	"codex/pre/secrets-guard/block":  {exit: 0, stdout: "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"deny\",\"permissionDecisionReason\":\"BLOCKED: content looks like a live secret (API key / token / private key). Do not commit secrets; use a secret manager and reference via env var.\"}}\n", stderr: ""},
	"codex/post/formatter/notice":    {exit: 0, stdout: "", stderr: "ruff still reports issues in /w/a.py:\n/w/a.py:1:7: F821 Undefined name `x`\nFound 1 error.\n"},
	"claude/pre/rtk/forward":         {exit: 0, stdout: "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"updatedInput\":{\"command\":\"rtk git status\"}}}\n", stderr: ""},
	"codex/pre/rtk/forward":          {exit: 0, stdout: "{\"hookSpecificOutput\":{\"hookEventName\":\"PreToolUse\",\"permissionDecision\":\"allow\",\"permissionDecisionReason\":\"RTK auto-rewrite\",\"updatedInput\":{\"command\":\"/b/rtk git status\"}}}\n", stderr: ""},
}
