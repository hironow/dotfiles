package logline

import (
	"os"
	"path/filepath"
	"reflect"
	"testing"

	json "github.com/goccy/go-json/v2"
)

// TestEveryCodeSummaryFixtureIsTheSummary keeps testdata/every-code-summary.json
// equal to the summary of lines that carry every error code and mismatch the
// package knows, and one unknown value of each (counted as "other").
// tests/unit/test_agent_hook_doctor.py feeds the same file to doctor, so a
// code added here without doctor, or there without here, fails one side.
func TestEveryCodeSummaryFixtureIsTheSummary(t *testing.T) {
	// given a line for each known code and mismatch, and one unknown of each
	var lines []Line
	for code := range errorCodes {
		lines = append(lines, Line{Error: code})
	}
	lines = append(lines, Line{Error: "not.a.code"})
	for name := range mismatches {
		lines = append(lines, Line{Mismatch: name})
	}
	lines = append(lines, Line{Mismatch: "not-a-mismatch"})
	// when they are summarized
	got := Summarize(1, lines, 0)
	// then the committed fixture is that summary
	data, err := os.ReadFile(filepath.Join("testdata", "every-code-summary.json"))
	if err != nil {
		t.Fatal(err)
	}
	var want Summary
	if err := json.Unmarshal(data, &want); err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(got, want) {
		text, _ := json.Marshal(got)
		t.Fatalf("testdata/every-code-summary.json is not the summary of every code; write it as\n%s", text)
	}
}
