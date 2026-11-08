// Package latency defines the hook cases and summarizes their wall times.
package latency

import (
	"fmt"
	"slices"
	"strings"
	"text/tabwriter"
	"time"
)

// Percentile returns the nearest-rank percentile of nonempty samples.
// It leaves the caller's samples in their original order.
func Percentile(samples []time.Duration, percent int) time.Duration {
	ordered := slices.Clone(samples)
	slices.Sort(ordered)
	return ordered[(len(ordered)*percent+99)/100-1]
}

// WithinBudget includes a binary p95 exactly at the allowed increase.
func WithinBudget(old, binary, budget time.Duration) bool {
	return binary-old <= budget
}

// Row holds the timed samples for one case, without its warm-ups.
type Row struct {
	Name        string
	Old, Binary []time.Duration
}

// Table renders milliseconds and the machine on which they were measured.
func Table(rows []Row, budget time.Duration, goos, goarch, version string, runs int) string {
	var text strings.Builder
	columns := tabwriter.NewWriter(&text, 0, 4, 2, ' ', 0)
	fmt.Fprintln(columns, "case\truns\told-p50\told-p95\tbinary-p50\tbinary-p95\tΔp95\tok")
	for _, row := range rows {
		old95, binary95 := Percentile(row.Old, 95), Percentile(row.Binary, 95)
		fmt.Fprintf(columns, "%s\t%d\t%.1f\t%.1f\t%.1f\t%.1f\t%.1f\t%t\n",
			row.Name, len(row.Old), milliseconds(Percentile(row.Old, 50)), milliseconds(old95),
			milliseconds(Percentile(row.Binary, 50)), milliseconds(binary95), milliseconds(binary95-old95),
			WithinBudget(old95, binary95, budget))
	}
	// The only destination is a strings.Builder, which cannot fail.
	_ = columns.Flush()
	fmt.Fprintf(&text, "%s/%s %s N=%d\n", goos, goarch, version, runs)
	return text.String()
}

func milliseconds(duration time.Duration) float64 {
	return float64(duration) / float64(time.Millisecond)
}
