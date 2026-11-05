package logline_test

import (
	"slices"
	"strings"
	"testing"
	"time"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/logline"
)

func TestTableAlignsColumnsAndKeepsTheGivenOrder(t *testing.T) {
	first := build(logline.Firing{
		Harness: "claude", Event: "pre", Hook: "command-guard", Duration: 2500 * time.Microsecond,
		Call: &ir.Call{Kind: ir.KindShell, Tool: "Bash", Fields: map[string]ir.Value{ir.FieldCommand: stringValue("git status")}},
	})
	second := logline.Build(logline.Firing{Usage: true}, nil,
		time.Date(2026, 11, 6, 0, 0, 0, 0, time.UTC), [8]byte{}, [16]byte{})
	text := logline.Table([]logline.Line{first, second}, 2)
	rows := strings.Split(strings.TrimSuffix(text, "\n"), "\n")
	want := [][]string{
		{"TIME", "HARNESS", "EVENT", "TOOL", "KIND", "HOOK", "OUTCOME", "RULE", "MS", "PROGRAM", "SUBCOMMAND", "EXTENSION", "PROJECT", "ERROR", "MISMATCH"},
		{first.Time, "claude", "pre", "Bash", "shell", "command-guard", "pass", "-", "2.5", "git", "status", "-", "-", "-", "-"},
		{second.Time, "other", "-", "-", "-", "-", "-", "-", "-", "-", "-", "-", "-", "usage", "-"},
	}
	if len(rows) != 4 || rows[3] != "Skipped 2 unreadable lines." {
		t.Fatalf("table needs a header, two rows, and a final skipped count: %q", text)
	}
	starts := make([]int, len(want[0]))
	for row, words := range want {
		if got := strings.Fields(rows[row]); !slices.Equal(got, words) {
			t.Fatalf("row %d = %q; want %q", row, got, words)
		}
		cursor := 0
		for column, word := range words {
			start := cursor + strings.Index(rows[row][cursor:], word)
			if row == 0 {
				starts[column] = start
			} else if start != starts[column] {
				t.Errorf("row %d column %s starts at %d; want %d", row, want[0][column], start, starts[column])
			}
			cursor = start + len(word)
		}
	}
	if strings.Contains(text, "\t") {
		t.Error("table must align with spaces, not terminal tab stops")
	}
}

func TestTableHandlesEmptyInputAndTheSkippedCount(t *testing.T) {
	if got := logline.Table(nil, 0); got != "" {
		t.Errorf("empty table = %q", got)
	}
	if got := logline.Table(nil, 3); got != "Skipped 3 unreadable lines.\n" {
		t.Errorf("skipped-only table = %q", got)
	}
	if got := logline.Table(nil, -1); got != "Skipped -1 unreadable lines.\n" {
		t.Errorf("nonzero skipped count must be reported: %q", got)
	}
	if got := logline.Table([]logline.Line{build(logline.Firing{})}, 0); strings.Contains(got, "Skipped") {
		t.Errorf("zero skipped count should be omitted: %q", got)
	}
}
