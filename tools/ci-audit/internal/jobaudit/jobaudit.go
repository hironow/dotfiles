// Package jobaudit measures where the time of a CI job goes: waiting for a
// runner, setup, running the job's recipe, and what comes after.
//
// The definitions are the ones in docs/agents/ci-speed.md:
//
//   - waiting is the job's started time minus its created time. A job with
//     `needs` is created when its needs finish, so their run time is not
//     counted as waiting;
//   - setup is the steps before the recipe step;
//   - running is the recipe step: the longest step that is the job's own work,
//     which excludes the steps GitHub adds ("Set up job", "Post ...",
//     "Complete job") and the steps that run a published action
//     ("Run owner/repo@<sha>"). A run of the audit data showed why: setup-uv took
//     3 s and the recipe 1 s, so "the longest step" named the wrong one;
//   - after is the steps behind it (cleanup, upload, post steps).
//
// The package is a pure core over values; the GitHub REST calls live elsewhere.
package jobaudit

import (
	"fmt"
	"regexp"
	"slices"
	"strings"
	"time"
)

// Step is one step of a job.
type Step struct {
	Name      string
	Started   time.Time
	Completed time.Time
}

// Job is one job of one run attempt.
type Job struct {
	Name       string
	RunID      int64
	Attempt    int
	Conclusion string
	Created    time.Time
	Started    time.Time
	Completed  time.Time
	Steps      []Step
}

// Parts is how long each phase of one job took, in seconds.
type Parts struct {
	Waiting float64
	Setup   float64
	Running float64
	After   float64
	// Wall is the job's completed time minus its started time: what a runner is
	// paid for. It is more than Setup+Running+After, because GitHub reports no
	// step for the moments between steps.
	Wall float64
}

// Total is the seconds from the job's start to its end.
func (p Parts) Total() float64 { return p.Wall }

// Split cuts one job into its phases.
func Split(j Job) Parts {
	p := Parts{Waiting: seconds(j.Created, j.Started), Wall: seconds(j.Started, j.Completed)}
	recipe := recipeStep(j.Steps)
	if recipe < 0 {
		// Nothing in the job is its own work: the whole body is setup.
		for _, s := range j.Steps {
			p.Setup += seconds(s.Started, s.Completed)
		}
		return p
	}
	for i, s := range j.Steps {
		d := seconds(s.Started, s.Completed)
		switch {
		case i < recipe:
			p.Setup += d
		case i == recipe:
			p.Running += d
		default:
			p.After += d
		}
	}
	return p
}

// recipeStep returns the index of the job's own work: the longest step that is
// neither added by GitHub nor a published action. It returns -1 when there is none.
func recipeStep(steps []Step) int {
	best, bestLen := -1, time.Duration(-1)
	for i, s := range steps {
		if s.Started.IsZero() || s.Completed.IsZero() || isPlatformStep(s.Name) {
			continue
		}
		if d := s.Completed.Sub(s.Started); d > bestLen {
			best, bestLen = i, d
		}
	}
	return best
}

var publishedAction = regexp.MustCompile(`^Run [\w.-]+/[\w./-]+@\S+`)

// isPlatformStep reports whether GitHub added the step or it runs a published action.
func isPlatformStep(name string) bool {
	switch {
	case name == "Set up job", name == "Complete job":
		return true
	case strings.HasPrefix(name, "Post "):
		return true
	}
	return publishedAction.MatchString(name)
}

func seconds(from, to time.Time) float64 {
	if from.IsZero() || to.IsZero() || to.Before(from) {
		return 0
	}
	return to.Sub(from).Seconds()
}

// Percentile is the nearest-rank percentile (p in 1..100) of values.
func Percentile(values []float64, p float64) float64 {
	if len(values) == 0 {
		return 0
	}
	sorted := slices.Clone(values)
	slices.Sort(sorted)
	rank := int(float64(len(sorted))*p/100 + 0.999999999)
	rank = max(rank, 1)
	rank = min(rank, len(sorted))
	return sorted[rank-1]
}

// Row is one job's summary over many runs.
type Row struct {
	Job     string
	Samples int
	Waiting [2]float64 // p50, p95
	Setup   [2]float64
	Running [2]float64
	After   [2]float64
	Total   [2]float64
	// RunnerSeconds is the sum of Total over all samples.
	RunnerSeconds float64
}

// Summarize groups jobs by name and reports p50 and p95 per phase. Only jobs
// that succeeded or failed count: a skipped or cancelled job measured nothing.
// Each run attempt is its own sample.
func Summarize(jobs []Job) []Row {
	groups := map[string][]Parts{}
	var order []string
	for _, j := range jobs {
		if j.Conclusion != "success" && j.Conclusion != "failure" {
			continue
		}
		if _, ok := groups[j.Name]; !ok {
			order = append(order, j.Name)
		}
		groups[j.Name] = append(groups[j.Name], Split(j))
	}
	rows := make([]Row, 0, len(order))
	for _, name := range order {
		parts := groups[name]
		row := Row{Job: name, Samples: len(parts)}
		pick := func(f func(Parts) float64) [2]float64 {
			values := make([]float64, len(parts))
			for i, p := range parts {
				values[i] = f(p)
			}
			return [2]float64{Percentile(values, 50), Percentile(values, 95)}
		}
		row.Waiting = pick(func(p Parts) float64 { return p.Waiting })
		row.Setup = pick(func(p Parts) float64 { return p.Setup })
		row.Running = pick(func(p Parts) float64 { return p.Running })
		row.After = pick(func(p Parts) float64 { return p.After })
		row.Total = pick(Parts.Total)
		for _, p := range parts {
			row.RunnerSeconds += p.Total()
		}
		rows = append(rows, row)
	}
	slices.SortStableFunc(rows, func(a, b Row) int {
		switch {
		case a.Total[1] > b.Total[1]:
			return -1
		case a.Total[1] < b.Total[1]:
			return 1
		}
		return strings.Compare(a.Job, b.Job)
	})
	return rows
}

// Render prints the rows as text, slowest p95 first.
func Render(rows []Row) string {
	var b strings.Builder
	for _, r := range rows {
		fmt.Fprintf(&b, "%s\n  n=%d  waiting %s  setup %s  running %s  after %s  total %s  runner seconds %.0f\n",
			r.Job, r.Samples, pair(r.Waiting), pair(r.Setup), pair(r.Running), pair(r.After), pair(r.Total), r.RunnerSeconds)
	}
	return b.String()
}

func pair(v [2]float64) string { return fmt.Sprintf("%.0f/%.0fs", v[0], v[1]) }
