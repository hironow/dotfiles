// ci-audit measures CI the way docs/agents/ci-speed.md asks. Run it through
// `just ci-audit` and `just ci-shard-check`.
//
//	ci-audit jobs --repo OWNER/REPO [--runs N] [--branch B] [--event E] [--recipe-step JOB=STEP...] WORKFLOW...
//	    where each job's time goes (waiting, setup, running, after), at p50 and p95,
//	    over the last N completed runs of each workflow file, every attempt; and
//	    per push, when the pull request had its result and the runner seconds.
//
//	ci-audit shards --junit FILE... --collected FILE... [--max-imbalance X] [--durations-out FILE]
//	    proves that the shards together ran every collected test once. Give
//	    --collected once, or once per shard in --junit order; each shard's list
//	    is compared with the first by its ids.
package main

import (
	"context"
	"flag"
	"fmt"
	"io"
	"os"
	"regexp"
	"strings"
	"time"

	"github.com/goccy/go-json"

	"github.com/hironow/dotfiles/tools/ci-audit/internal/ghrest"
	"github.com/hironow/dotfiles/tools/ci-audit/internal/jobaudit"
	"github.com/hironow/dotfiles/tools/ci-audit/internal/shardcheck"
)

func main() {
	os.Exit(run(context.Background(), os.Args[1:], os.Stdout, os.Stderr, ghrest.GH{}))
}

func run(ctx context.Context, args []string, stdout, stderr io.Writer, api ghrest.Runs) int {
	if len(args) == 0 {
		fmt.Fprintln(stderr, "usage: ci-audit jobs|shards ...")
		return 2
	}
	switch args[0] {
	case "jobs":
		return runJobs(ctx, args[1:], stdout, stderr, api)
	case "shards":
		return runShards(args[1:], stdout, stderr)
	}
	fmt.Fprintf(stderr, "ci-audit: unknown command %q\n", args[0])
	return 2
}

func runJobs(ctx context.Context, args []string, stdout, stderr io.Writer, api ghrest.Runs) int {
	flags := flag.NewFlagSet("jobs", flag.ContinueOnError)
	flags.SetOutput(stderr)
	repo := flags.String("repo", "", "OWNER/REPO")
	runs := flags.Int("runs", 150, "how many completed runs of each workflow to read")
	branch := flags.String("branch", "", "read only the runs of this branch")
	event := flags.String("event", "", "read only the runs this event started (push, pull_request, ...)")
	var recipeSteps listFlag
	flags.Var(&recipeSteps, "recipe-step", "JOB=STEP: count STEP as JOB's running step; repeat for a job with several, and running is the span from the first to the last")
	if err := flags.Parse(args); err != nil || *repo == "" || flags.NArg() == 0 || *runs < 1 {
		fmt.Fprintln(stderr, "usage: ci-audit jobs --repo OWNER/REPO [--runs N] [--branch B] [--event E] [--recipe-step JOB=STEP...] WORKFLOW.yaml...")
		return 2
	}
	opt := jobaudit.Options{RecipeSteps: map[string][]string{}}
	for _, pair := range recipeSteps {
		job, step, ok := strings.Cut(pair, "=")
		if !ok || job == "" || step == "" {
			fmt.Fprintf(stderr, "ci-audit: --recipe-step %q is not JOB=STEP\n", pair)
			return 2
		}
		opt.RecipeSteps[job] = append(opt.RecipeSteps[job], step)
	}
	filter := ghrest.Filter{Limit: *runs, Branch: *branch, Event: *event}
	var all []jobaudit.Job
	// The pushes are measured only where every workflow's window reaches.
	var windowStart time.Time
	var unfinished []jobaudit.Commit
	for _, workflow := range flags.Args() {
		w, err := ghrest.FetchWindow(ctx, api, *repo, workflow, filter)
		if err != nil {
			fmt.Fprintln(stderr, "ci-audit:", err)
			return 1
		}
		all = append(all, w.Jobs...)
		unfinished = append(unfinished, w.Unfinished...)
		if w.WindowStart.After(windowStart) {
			windowStart = w.WindowStart
		}
	}
	pushes, err := measurePushes(ctx, api, *repo, flags.Args(), all, jobaudit.PushOptions{WindowStart: windowStart, Unfinished: unfinished})
	if err != nil {
		fmt.Fprintln(stderr, "ci-audit:", err)
		return 1
	}
	rows := jobaudit.Summarize(all, opt)
	if len(rows) == 0 {
		fmt.Fprintln(stderr, "ci-audit: no completed job was found")
		return 1
	}
	fmt.Fprintf(stdout, "Seconds as p50/p95 over the completed runs (each run attempt is its own sample).\n"+
		"waiting = started minus created; setup = steps before the recipe; running = the recipe step;\n"+
		"after = steps behind it; total = completed minus started.\n\n%s", jobaudit.Render(rows))
	fmt.Fprintf(stdout, "\nPer push: result = first run created to the last job of the first attempts done;\n"+
		"runner seconds = every job of every attempt.\n%s", jobaudit.RenderPushes(pushes))
	return 0
}

type listFlag []string

func (l *listFlag) String() string     { return strings.Join(*l, ",") }
func (l *listFlag) Set(v string) error { *l = append(*l, v); return nil }

func runShards(args []string, stdout, stderr io.Writer) int {
	flags := flag.NewFlagSet("shards", flag.ContinueOnError)
	flags.SetOutput(stderr)
	var junit listFlag
	flags.Var(&junit, "junit", "a shard's JUnit report (repeat once per shard)")
	var collected listFlag
	flags.Var(&collected, "collected", "the `pytest --collect-only -q` list of the whole suite (once, or once per shard in --junit order)")
	maxImbalance := flags.Float64("max-imbalance", 1.5, "the largest allowed ratio of the slowest shard to the mean (0 turns it off)")
	durationsOut := flags.String("durations-out", "", "write per-test seconds, keyed by node id, to this file")
	err := flags.Parse(args)
	if err != nil || len(junit) == 0 || (len(collected) != 1 && len(collected) != len(junit)) {
		fmt.Fprintln(stderr, "usage: ci-audit shards --collected FILE [--collected FILE...] --junit FILE [--junit FILE...] [--max-imbalance X] [--durations-out FILE]\n"+
			"  give --collected once, or once per --junit, in the same order")
		return 2
	}
	// Each shard's list is compared by its ids, so pytest's summary line, which
	// holds the collection time, never makes two equal lists differ.
	lists := make([][]string, len(collected))
	for i, path := range collected {
		data, err := os.ReadFile(path)
		if err != nil {
			fmt.Fprintln(stderr, "ci-audit:", err)
			return 1
		}
		lists[i] = shardcheck.ParseCollected(data)
	}
	shards := make([]shardcheck.Shard, 0, len(junit))
	for i, path := range junit {
		ids := lists[0]
		if len(lists) > 1 {
			ids = lists[i]
		}
		data, err := os.ReadFile(path)
		if err != nil {
			fmt.Fprintln(stderr, "ci-audit:", err)
			return 1
		}
		cases, err := shardcheck.ParseJUnit(data)
		if err != nil {
			fmt.Fprintf(stderr, "ci-audit: %s: %v\n", path, err)
			return 1
		}
		shards = append(shards, shardcheck.Shard{Name: fmt.Sprintf("shard-%d (%s)", i+1, path), Collected: ids, Cases: cases})
	}
	report := shardcheck.Check(shards, shardcheck.Options{MaxImbalance: *maxImbalance})
	fmt.Fprintf(stdout, "collected %d tests; %d executed by %d shards; slowest shard is %.2f times the mean\n",
		report.Expected, report.Executed, len(shards), report.Imbalance)
	for _, s := range shards {
		fmt.Fprintf(stdout, "  %-60s %6.0fs\n", s.Name, report.ShardSeconds[s.Name])
	}
	if n := len(report.SkippedModules); n > 0 {
		noun := "modules"
		verb := "skipped themselves"
		if n == 1 {
			noun, verb = "module", "skipped itself"
		}
		fmt.Fprintf(stdout, "%d %s %s at collection: %s\n", n, noun, verb, strings.Join(report.SkippedModules, ", "))
	}
	if *durationsOut != "" {
		data, err := json.MarshalIndent(withoutSecretShapes(report.Durations), "", "  ")
		if err != nil {
			fmt.Fprintln(stderr, "ci-audit:", err)
			return 1
		}
		if err := os.WriteFile(*durationsOut, append(data, '\n'), 0o600); err != nil {
			fmt.Fprintln(stderr, "ci-audit:", err)
			return 1
		}
	}
	if !report.OK() {
		for _, p := range report.Problems {
			fmt.Fprintln(stderr, "FAIL:", p)
		}
		return 1
	}
	fmt.Fprintln(stdout, "OK: every collected test ran once")
	return 0
}

// secretShape matches text that looks like a credential. The cases of a
// secret scanner's own tests carry such text in their ids.
var secretShape = regexp.MustCompile(`(?i)(sk-|sk_live|ghp_|github_pat_|xox[bp]-|AKIA|AIza|-----BEGIN)`)

// withoutSecretShapes drops the ids that hold credential-shaped text. The
// durations file is committed, and GitHub's push protection and the repo's
// private-key hook both reject such text. pytest-split gives a test it has no
// duration for the mean of the others, so leaving a few out costs nothing.
func withoutSecretShapes(durations map[string]float64) map[string]float64 {
	kept := make(map[string]float64, len(durations))
	for id, seconds := range durations {
		if !secretShape.MatchString(id) {
			kept[id] = seconds
		}
	}
	return kept
}

// measurePushes checks each push that the window rule keeps against the runs
// GitHub lists for its commit, and leaves out the ones with a run that was not
// read. It costs one call per push.
func measurePushes(ctx context.Context, api ghrest.Runs, repo string, workflows []string, jobs []jobaudit.Job, opt jobaudit.PushOptions) (jobaudit.PushSummary, error) {
	read := map[int64]bool{}
	for _, j := range jobs {
		read[j.RunID] = true
	}
	audited := map[string]bool{}
	for _, w := range workflows {
		audited[w] = true
	}
	for _, p := range jobaudit.Pushes(jobs, opt).Pushes {
		c := jobaudit.Commit{HeadSHA: p.HeadSHA, Event: p.Event}
		runs, err := ghrest.CommitRuns(ctx, api, repo, c)
		if err != nil {
			return jobaudit.PushSummary{}, err
		}
		if !jobaudit.Complete(read, runs, audited) {
			opt.Incomplete = append(opt.Incomplete, c)
		}
	}
	return jobaudit.Pushes(jobs, opt), nil
}
