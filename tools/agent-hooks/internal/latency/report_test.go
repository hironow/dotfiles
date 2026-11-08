package latency_test

import (
	"slices"
	"strings"
	"testing"
	"time"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/latency"
)

func TestPercentileUsesNearestRankWithoutChangingSamples(t *testing.T) {
	for _, test := range []struct {
		name    string
		samples []time.Duration
		p50     time.Duration
		p95     time.Duration
	}{
		{"one", []time.Duration{7}, 7, 7},
		{"odd", []time.Duration{9, 1, 5, 3, 7}, 5, 9},
		{"even", []time.Duration{20, 1, 19, 2, 18, 3, 17, 4, 16, 5, 15, 6, 14, 7, 13, 8, 12, 9, 11, 10}, 10, 19},
	} {
		t.Run(test.name, func(t *testing.T) {
			before := slices.Clone(test.samples)
			if got := latency.Percentile(test.samples, 50); got != test.p50 {
				t.Errorf("p50 = %v, want %v", got, test.p50)
			}
			if got := latency.Percentile(test.samples, 95); got != test.p95 {
				t.Errorf("p95 = %v, want %v", got, test.p95)
			}
			if !slices.Equal(test.samples, before) {
				t.Error("calculating percentiles changed the samples")
			}
		})
	}
}

func TestBudgetIncludesItsBoundary(t *testing.T) {
	old := 10 * time.Millisecond
	budget := 15 * time.Millisecond
	if !latency.WithinBudget(old, old+budget, budget) {
		t.Error("exactly at the budget must pass")
	}
	if latency.WithinBudget(old, old+budget+time.Nanosecond, budget) {
		t.Error("one nanosecond over the budget must fail")
	}
}

func TestTableReportsMillisecondsAndMachine(t *testing.T) {
	rows := []latency.Row{{
		Name:   "claude/pre/command-guard/pass",
		Old:    []time.Duration{time.Millisecond, 2 * time.Millisecond, 3 * time.Millisecond},
		Binary: []time.Duration{2 * time.Millisecond, 3 * time.Millisecond, 4 * time.Millisecond},
	}}
	got := latency.Table(rows, 15*time.Millisecond, "darwin", "arm64", "go1.27.3", 3)
	lines := strings.Split(strings.TrimSpace(got), "\n")
	if want := []string{"case", "runs", "old-p50", "old-p95", "binary-p50", "binary-p95", "Δp95", "ok"}; !slices.Equal(strings.Fields(lines[0]), want) {
		t.Fatalf("columns = %q, want %q", lines[0], want)
	}
	if want := []string{rows[0].Name, "3", "2.0", "3.0", "3.0", "4.0", "1.0", "true"}; !slices.Equal(strings.Fields(lines[1]), want) {
		t.Errorf("row = %q, want %q", lines[1], want)
	}
	if lines[2] != "darwin/arm64 go1.27.3 N=3" {
		t.Errorf("machine line = %q", lines[2])
	}
}
