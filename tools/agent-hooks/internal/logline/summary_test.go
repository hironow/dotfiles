package logline_test

import (
	"reflect"
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/logline"
)

func TestSummarizeCountsEachKnownCodeAndOtherForTheRest(t *testing.T) {
	// given lines with known codes, values outside the fixed sets (a log file
	// is untrusted input), and lines with no error or mismatch
	lines := []logline.Line{
		{Error: "hook.timeout"},
		{Error: "hook.timeout", Mismatch: "input"},
		{Error: "weird.code", Mismatch: "odd\x01"},
		{Mismatch: "envelope"},
		{},
	}
	// when they are summarized
	got := logline.Summarize(3, lines, 2)
	// then known codes count by name, others as "other", and empty values not at all
	want := logline.Summary{
		Days:       3,
		Lines:      5,
		Unreadable: 2,
		Errors:     map[string]int{"hook.timeout": 2, "other": 1},
		Mismatches: map[string]int{"input": 1, "other": 1, "envelope": 1},
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("Summarize = %+v, want %+v", got, want)
	}
}

func TestSummarizeOfNothingHasEmptyCounts(t *testing.T) {
	got := logline.Summarize(1, nil, 0)
	if got.Lines != 0 || got.Unreadable != 0 || got.Errors == nil || len(got.Errors) != 0 || got.Mismatches == nil || len(got.Mismatches) != 0 {
		t.Fatalf("Summarize of nothing = %+v, want zero counts and empty, non-nil maps", got)
	}
}
