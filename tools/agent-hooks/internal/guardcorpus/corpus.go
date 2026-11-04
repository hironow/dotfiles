// Package guardcorpus holds the guard corpora: what each old guard (the
// reference until the old scripts are removed) does with each of its inputs.
// The Go tests check the ports against them.
//
//   - command-guard.jsonl: the Python command guard
//     (ROOT_AGENTS_hooks_block-prohibited-commands.py), written by
//     `just command-guard-corpus` and checked by
//     tests/unit/test_command_guard_corpus.py.
//   - files-guard.jsonl and secrets-guard.jsonl: the shell guards
//     ROOT_AGENTS_hooks_block-prohibited-files.sh and
//     ROOT_AGENTS_hooks_block-secrets.sh, written by `just file-guards-corpus`
//     and checked by tests/unit/test_file_guards_corpus.py.
package guardcorpus

import (
	_ "embed"
	"strings"
	"testing"

	json "github.com/goccy/go-json/v2"
)

//go:embed command-guard.jsonl
var corpus string

//go:embed files-guard.jsonl
var filesGuardCorpus string

//go:embed secrets-guard.jsonl
var secretsGuardCorpus string

// Entry is what the Python guard made of one input.
type Entry struct {
	Line       int      `json:"-"`          // its line in command-guard.jsonl
	Input      string   `json:"input"`      // the command text
	Tokens     []string `json:"tokens"`     // Python shlex's words; nil when it failed
	TokenError *string  `json:"tokenError"` // shlex's ValueError message when it failed
	Cleaned    string   `json:"cleaned"`    // the input without its heredoc bodies
	CodeBodies []string `json:"codeBodies"` // the heredoc bodies fed to an interpreter
	Reason     *string  `json:"reason"`     // why the guard blocks; nil when it passes
}

// Entries returns every entry, and fails the test when a line does not decode.
func Entries(tb testing.TB) []Entry {
	tb.Helper()
	return decodeLines(tb, "command-guard.jsonl", corpus, func(e *Entry, line int) { e.Line = line })
}

// ShellGuardResult is what a shell guard did with one input.
type ShellGuardResult struct {
	Exit   int     `json:"exit"`   // 0 passes, 2 blocks; 1 fails, which no harness blocks on
	Reason *string `json:"reason"` // why it blocks; nil unless Exit is 2
	// Difference names the fixes of the old guard's bugs that change this
	// answer (scripts/old_script_fixes.py), as "fixed-<name>" joined by "+";
	// empty when the port answers as the old guard did.
	Difference string `json:"difference"`
}

// FilesGuardEntry is what the files guard did with one input, handed over as
// Claude Code does (FilePath) or as Codex does (Patch), under BSD's and under
// GNU's basename(1), and, where that differs, what the guard with its bugs
// fixed does (Fixed).
type FilesGuardEntry struct {
	Line         int              `json:"-"`            // its line in files-guard.jsonl
	FilePath     *string          `json:"filePath"`     // tool_input.file_path
	Patch        *string          `json:"patch"`        // tool_input.command of Codex's apply_patch
	FilePathRuns []Run            `json:"filePathRuns"` // a long FilePath, as stored
	PatchRuns    []Run            `json:"patchRuns"`    // a long Patch, as stored
	BSD          ShellGuardResult `json:"bsd"`
	GNU          ShellGuardResult `json:"gnu"`
	// Fixed is the fixed guard's answer, present when it differs from a
	// flavor's. It needs no basename(1), so one answer serves both.
	Fixed *ShellGuardResult `json:"fixed"`
}

// Frame is the frame a test puts the entry in: "parity" when the port
// answers as the old guard did under both flavors, else the fixes it needs.
func (e FilesGuardEntry) Frame() string {
	switch {
	case e.BSD.Difference == "" && e.GNU.Difference == "":
		return "parity"
	case e.BSD.Difference == "" || e.BSD.Difference == e.GNU.Difference:
		return e.GNU.Difference
	case e.GNU.Difference == "":
		return e.BSD.Difference
	default:
		return e.BSD.Difference + "+" + e.GNU.Difference
	}
}

// Expected is the port's answer: the fixed guard's where the entry holds it,
// else the old guard's, which must then be the same under both flavors.
func (e FilesGuardEntry) Expected(tb testing.TB) ShellGuardResult {
	tb.Helper()
	if e.Fixed != nil {
		return *e.Fixed
	}
	if (e.BSD.Exit == 2) != (e.GNU.Exit == 2) || (e.BSD.Exit == 2 && *e.BSD.Reason != *e.GNU.Reason) {
		tb.Fatalf("files-guard.jsonl:%d: the flavors disagree, and the entry holds no fixed answer", e.Line)
	}
	return e.BSD
}

// SecretsGuardEntry is what the secrets guard did with one input, handed over
// as Claude Code does (Content) or as Codex does (Patch).
type SecretsGuardEntry struct {
	Line        int     `json:"-"`           // its line in secrets-guard.jsonl
	Content     *string `json:"content"`     // tool_input.content
	Patch       *string `json:"patch"`       // tool_input.command of Codex's apply_patch
	ContentRuns []Run   `json:"contentRuns"` // a long Content, as stored
	PatchRuns   []Run   `json:"patchRuns"`   // a long Patch, as stored
	Exit        int     `json:"exit"`        // as in ShellGuardResult
	Reason      *string `json:"reason"`      // as in ShellGuardResult
}

// Run is Count copies of Char. The corpora store an input longer than 1024
// characters as its runs, so that a 1 MiB test input takes one short line;
// the readers join the runs back into the input.
type Run struct {
	Char  string `json:"char"`
	Count int    `json:"count"`
}

// joinRuns sets *text to the input runs hold, when it is stored as runs.
func joinRuns(text **string, runs []Run) {
	if runs == nil {
		return
	}
	var b strings.Builder
	for _, r := range runs {
		b.WriteString(strings.Repeat(r.Char, r.Count))
	}
	joined := b.String()
	*text = &joined
}

// FilesGuardEntries returns every entry of files-guard.jsonl.
func FilesGuardEntries(tb testing.TB) []FilesGuardEntry {
	tb.Helper()
	return decodeLines(tb, "files-guard.jsonl", filesGuardCorpus, func(e *FilesGuardEntry, line int) {
		e.Line = line
		joinRuns(&e.FilePath, e.FilePathRuns)
		joinRuns(&e.Patch, e.PatchRuns)
	})
}

// SecretsGuardEntries returns every entry of secrets-guard.jsonl.
func SecretsGuardEntries(tb testing.TB) []SecretsGuardEntry {
	tb.Helper()
	return decodeLines(tb, "secrets-guard.jsonl", secretsGuardCorpus, func(e *SecretsGuardEntry, line int) {
		e.Line = line
		joinRuns(&e.Content, e.ContentRuns)
		joinRuns(&e.Patch, e.PatchRuns)
	})
}

// decodeLines decodes one JSON object per line of text into a T, rejecting
// members T does not have, and records each entry's line with at.
func decodeLines[T any](tb testing.TB, name, text string, at func(*T, int)) []T {
	tb.Helper()
	lines := strings.Split(strings.TrimSuffix(text, "\n"), "\n")
	entries := make([]T, 0, len(lines))
	for i, line := range lines {
		var entry T
		if err := json.Unmarshal([]byte(line), &entry, json.RejectUnknownMembers(true)); err != nil {
			tb.Fatalf("%s:%d: %v", name, i+1, err)
		}
		at(&entry, i+1)
		entries = append(entries, entry)
	}
	return entries
}
