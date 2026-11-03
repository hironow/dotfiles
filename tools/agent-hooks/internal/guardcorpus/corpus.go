// Package guardcorpus holds the command guard corpus: what the Python command
// guard (ROOT_AGENTS_hooks_block-prohibited-commands.py, the reference until
// the old scripts are removed) does with each of its inputs. The Go tests
// check the port against it.
//
// `just command-guard-corpus` writes command-guard.jsonl from the reference,
// and tests/unit/test_command_guard_corpus.py fails when the file is stale.
package guardcorpus

import (
	_ "embed"
	"strings"
	"testing"

	json "github.com/goccy/go-json/v2"
)

//go:embed command-guard.jsonl
var corpus string

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
	lines := strings.Split(strings.TrimSuffix(corpus, "\n"), "\n")
	entries := make([]Entry, 0, len(lines))
	for i, line := range lines {
		entry := Entry{Line: i + 1}
		err := json.Unmarshal([]byte(line), &entry, json.RejectUnknownMembers(true))
		if err != nil {
			tb.Fatalf("command-guard.jsonl:%d: %v", entry.Line, err)
		}
		entries = append(entries, entry)
	}
	return entries
}
