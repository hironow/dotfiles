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
	"maps"
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
	Workflow   string // the workflow file, such as "unit-test.yaml"
	RunID      int64
	Attempt    int
	Conclusion string
	HeadSHA    string // the commit the run tested
	Event      string // what started the run: push, pull_request, ...
	RunCreated time.Time
	Created    time.Time
	Started    time.Time
	Completed  time.Time
	Steps      []Step
}

// Options tune the summary.
type Options struct {
	// RecipeSteps names a job's recipe step, by job name, where the longest
	// step is not the recipe (a bootstrap that takes longer than the checks).
	RecipeSteps map[string]string
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

// Split cuts one job into its phases, with the longest step as its recipe.
func Split(j Job) Parts {
	p, _ := split(j, "")
	return p
}

// split cuts one job into its phases. The recipe step is the step named
// recipe, or the longest of the job's own steps when recipe is "". It returns
// the name of the step it counted as running ("" when there is none).
func split(j Job, recipe string) (Parts, string) {
	p := Parts{Waiting: seconds(j.Created, j.Started), Wall: seconds(j.Started, j.Completed)}
	index := recipeStep(j.Steps)
	if recipe != "" {
		index = slices.IndexFunc(j.Steps, func(s Step) bool { return s.Name == recipe })
	}
	if index < 0 {
		// Nothing in the job is its own work: the whole body is setup.
		for _, s := range j.Steps {
			p.Setup += seconds(s.Started, s.Completed)
		}
		return p, ""
	}
	recipe = j.Steps[index].Name
	for i, s := range j.Steps {
		d := seconds(s.Started, s.Completed)
		switch {
		case i < index:
			p.Setup += d
		case i == index:
			p.Running += d
		default:
			p.After += d
		}
	}
	return p, recipe
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
	// RecipeStep is the step counted as running, in most samples. The report
	// prints it, so a wrong guess is visible.
	RecipeStep string
}

// finished reports whether a job measured something: it succeeded, failed, or
// ran into its timeout (the slow tail). A skipped or cancelled job did not.
func finished(conclusion string) bool {
	switch conclusion {
	case "success", "failure", "timed_out":
		return true
	}
	return false
}

// Summarize groups jobs by name and reports p50 and p95 per phase. Only jobs
// that finished count (see finished). Each run attempt is its own sample.
func Summarize(jobs []Job, opt Options) []Row {
	groups := map[string][]Parts{}
	steps := map[string]map[string]int{}
	var order []string
	for _, j := range jobs {
		if !finished(j.Conclusion) {
			continue
		}
		if _, ok := groups[j.Name]; !ok {
			order = append(order, j.Name)
			steps[j.Name] = map[string]int{}
		}
		p, step := split(j, opt.RecipeSteps[j.Name])
		groups[j.Name] = append(groups[j.Name], p)
		steps[j.Name][step]++
	}
	rows := make([]Row, 0, len(order))
	for _, name := range order {
		parts := groups[name]
		row := Row{Job: name, Samples: len(parts), RecipeStep: mostCommon(steps[name])}
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

// mostCommon returns the key with the highest count, the smallest on a tie.
func mostCommon(counts map[string]int) string {
	best, bestCount := "", -1
	for _, k := range slices.Sorted(maps.Keys(counts)) {
		if counts[k] > bestCount {
			best, bestCount = k, counts[k]
		}
	}
	return best
}

// Render prints the rows as text, slowest p95 first.
func Render(rows []Row) string {
	var b strings.Builder
	for _, r := range rows {
		fmt.Fprintf(&b, "%s\n  n=%d  waiting %s  setup %s  running %s  after %s  total %s  runner seconds %.0f  running = %q\n",
			r.Job, r.Samples, pair(r.Waiting), pair(r.Setup), pair(r.Running), pair(r.After), pair(r.Total), r.RunnerSeconds, r.RecipeStep)
	}
	return b.String()
}

// Push is every run one commit started for one event.
type Push struct {
	HeadSHA string
	Event   string
	// Result is the seconds from the first run's creation to the end of the
	// last job of the first attempts: when the pull request had its result.
	Result float64
	// RunnerSeconds is the wall time of every job of every attempt.
	RunnerSeconds float64
}

// PushSummary is Pushes' result.
type PushSummary struct {
	Pushes []Push
	// Partial counts pushes left out because a workflow that ran for that event
	// elsewhere in the window has no run for them.
	Partial       int
	Result        [2]float64 // p50, p95
	RunnerSeconds [2]float64 // p50, p95 per push
}

// Pushes groups jobs by commit and event, and measures each push.
func Pushes(jobs []Job) PushSummary {
	type key struct{ sha, event string }
	type group struct {
		workflows map[string]bool
		first     time.Time
		last      time.Time
		runner    float64
	}
	groups := map[key]*group{}
	eventWorkflows := map[string]map[string]bool{}
	var order []key
	for _, j := range jobs {
		if !finished(j.Conclusion) || j.HeadSHA == "" {
			continue
		}
		k := key{j.HeadSHA, j.Event}
		g, ok := groups[k]
		if !ok {
			g = &group{workflows: map[string]bool{}}
			groups[k] = g
			order = append(order, k)
		}
		if eventWorkflows[j.Event] == nil {
			eventWorkflows[j.Event] = map[string]bool{}
		}
		eventWorkflows[j.Event][j.Workflow] = true
		g.workflows[j.Workflow] = true
		g.runner += seconds(j.Started, j.Completed)
		if j.Attempt != 1 {
			continue
		}
		if g.first.IsZero() || j.RunCreated.Before(g.first) {
			g.first = j.RunCreated
		}
		if j.Completed.After(g.last) {
			g.last = j.Completed
		}
	}
	var out PushSummary
	var results, runner []float64
	for _, k := range order {
		g := groups[k]
		if len(g.workflows) != len(eventWorkflows[k.event]) {
			out.Partial++
			continue
		}
		p := Push{HeadSHA: k.sha, Event: k.event, Result: seconds(g.first, g.last), RunnerSeconds: g.runner}
		out.Pushes = append(out.Pushes, p)
		results = append(results, p.Result)
		runner = append(runner, p.RunnerSeconds)
	}
	out.Result = [2]float64{Percentile(results, 50), Percentile(results, 95)}
	out.RunnerSeconds = [2]float64{Percentile(runner, 50), Percentile(runner, 95)}
	return out
}

// RenderPushes prints the push summary and the commits it counted.
func RenderPushes(s PushSummary) string {
	var b strings.Builder
	fmt.Fprintf(&b, "pushes n=%d (left out, a workflow missing: %d)  result %s  runner seconds per push %s\n",
		len(s.Pushes), s.Partial, pair(s.Result), pair(s.RunnerSeconds))
	for _, p := range s.Pushes {
		sha := p.HeadSHA
		if len(sha) > 12 {
			sha = sha[:12]
		}
		fmt.Fprintf(&b, "  %s %-13s result %4.0fs  runner %5.0fs\n", sha, p.Event, p.Result, p.RunnerSeconds)
	}
	return b.String()
}

func pair(v [2]float64) string { return fmt.Sprintf("%.0f/%.0fs", v[0], v[1]) }
