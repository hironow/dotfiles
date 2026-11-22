package jobaudit_test

import (
	"strings"
	"testing"
	"time"

	"github.com/hironow/dotfiles/tools/ci-audit/internal/jobaudit"
)

var t0 = time.Date(2026, 11, 22, 10, 0, 0, 0, time.UTC)

func at(seconds int) time.Time { return t0.Add(time.Duration(seconds) * time.Second) }

func step(name string, from, to int) jobaudit.Step {
	return jobaudit.Step{Name: name, Started: at(from), Completed: at(to)}
}

// A job shaped like the dev container job: bootstrap, one long recipe step,
// then cleanup and upload.
func devcontainerJob() jobaudit.Job {
	return jobaudit.Job{
		Name: "Required disposable Podman devcontainer build/up/exec", RunID: 1, Attempt: 1, Conclusion: "success",
		Created: at(0), Started: at(2), Completed: at(2 + 1 + 1 + 18 + 1281 + 1 + 1 + 1),
		Steps: []jobaudit.Step{
			step("Set up job", 2, 3),
			step("Checkout", 3, 4),
			step("Bootstrap native Podman and canonical frozen CLI tools", 4, 22),
			step("Run required disposable devcontainer acceptance and sandbox tests", 22, 1303),
			step("Always clean only journal-owned devcontainer resources", 1303, 1304),
			step("Upload test report", 1304, 1305),
			step("Post Checkout", 1305, 1306),
			step("Complete job", 1306, 1307),
		},
	}
}

func TestSplitSeparatesWaitingSetupRunningAndAfter(t *testing.T) {
	got := jobaudit.Split(devcontainerJob())
	if got.Waiting != 2 {
		t.Errorf("waiting = %v, want 2 (started minus created)", got.Waiting)
	}
	if got.Setup != 1+1+18 {
		t.Errorf("setup = %v, want 20 (job set-up, checkout, bootstrap)", got.Setup)
	}
	if got.Running != 1281 {
		t.Errorf("running = %v, want 1281 (the recipe step only)", got.Running)
	}
	if got.After != 1+1+1+1 {
		t.Errorf("after = %v, want 4 (cleanup, upload, post, complete)", got.After)
	}
}

func TestTotalIsTheJobsWallTimeNotTheSumOfItsSteps(t *testing.T) {
	// Steps that leave 1 s between them: the sum is 8 s, the job took 11 s.
	j := jobaudit.Job{
		Name: "gaps", RunID: 1, Attempt: 1, Conclusion: "success",
		Created: at(0), Started: at(0), Completed: at(11),
		Steps: []jobaudit.Step{step("Set up job", 0, 2), step("Run just js-lint", 3, 6), step("Complete job", 9, 11)},
	}
	got := jobaudit.Split(j)
	if got.Total() != 11 {
		t.Fatalf("total = %v, want 11 (completed minus started)", got.Total())
	}
	if got.Setup+got.Running+got.After >= got.Total() {
		t.Fatalf("the step sum %v should be below the wall time %v", got.Setup+got.Running+got.After, got.Total())
	}
}

func TestACleanupStepDoesNotCountAsRunning(t *testing.T) {
	j := devcontainerJob()
	got := jobaudit.Split(j)
	if got.Running > 1300 || got.Running < 1200 {
		t.Fatalf("running = %v: cleanup and upload leaked into it", got.Running)
	}
}

func TestAJobThatNeedsAnotherWaitsFromWhenItWasCreated(t *testing.T) {
	// "Frontend CI": created when the last needed job finished, started 2 s
	// later. Its waiting time is 2, not the 17 s since the run began.
	j := jobaudit.Job{
		Name: "Frontend CI", RunID: 2, Attempt: 1, Conclusion: "success",
		Created: at(17), Started: at(19), Completed: at(23),
		Steps: []jobaudit.Step{step("Set up job", 19, 20), step("Every job passed", 20, 22), step("Complete job", 22, 23)},
	}
	got := jobaudit.Split(j)
	if got.Waiting != 2 {
		t.Fatalf("waiting = %v, want 2", got.Waiting)
	}
	if got.Running != 2 {
		t.Fatalf("running = %v, want 2", got.Running)
	}
}

func TestPercentilesUseTheNearestRank(t *testing.T) {
	values := []float64{1, 2, 3, 4, 5, 6, 7, 8, 9, 10}
	if got := jobaudit.Percentile(values, 50); got != 5 {
		t.Errorf("p50 = %v, want 5", got)
	}
	if got := jobaudit.Percentile(values, 95); got != 10 {
		t.Errorf("p95 = %v, want 10", got)
	}
	if got := jobaudit.Percentile(nil, 50); got != 0 {
		t.Errorf("p50 of nothing = %v, want 0", got)
	}
}

func TestSummarizeGroupsByJobNameAndReadsEachAttemptOnItsOwn(t *testing.T) {
	a := devcontainerJob()
	b := devcontainerJob()
	b.RunID, b.Attempt = 2, 2
	c := devcontainerJob()
	c.Name, c.RunID = "other", 3
	rows := jobaudit.Summarize([]jobaudit.Job{a, b, c}, jobaudit.Options{})
	if len(rows) != 2 {
		t.Fatalf("rows = %d, want 2", len(rows))
	}
	var dev *jobaudit.Row
	for i := range rows {
		if strings.HasPrefix(rows[i].Job, "Required") {
			dev = &rows[i]
		}
	}
	if dev == nil || dev.Samples != 2 {
		t.Fatalf("the dev container row must hold 2 samples (two attempts), got %+v", dev)
	}
}

func TestSummarizeSkipsJobsThatDidNotFinish(t *testing.T) {
	skipped := devcontainerJob()
	skipped.Conclusion = "skipped"
	cancelled := devcontainerJob()
	cancelled.Conclusion = "cancelled"
	if rows := jobaudit.Summarize([]jobaudit.Job{skipped, cancelled}, jobaudit.Options{}); len(rows) != 0 {
		t.Fatalf("skipped and cancelled jobs must not count, got %+v", rows)
	}
}

func TestSummarizeCountsAJobThatRanIntoItsTimeout(t *testing.T) {
	slow := devcontainerJob()
	slow.Conclusion = "timed_out"
	if rows := jobaudit.Summarize([]jobaudit.Job{slow}, jobaudit.Options{}); len(rows) != 1 {
		t.Fatalf("a timed-out job is the slow tail and must count, got %+v", rows)
	}
}

// A job whose setup takes longer than its recipe: the longest step is the
// bootstrap, so the guess names the wrong step. The report shows the step it
// counted, and a named recipe step puts the time back where it belongs.
func setupHeavyJob() jobaudit.Job {
	return jobaudit.Job{
		Name: "just check (no container)", RunID: 1, Attempt: 1, Conclusion: "success",
		Created: at(0), Started: at(0), Completed: at(100),
		Steps: []jobaudit.Step{
			step("Set up job", 0, 1),
			step("Install the frozen tool set", 1, 70),
			step("Run just check", 70, 99),
			step("Complete job", 99, 100),
		},
	}
}

func TestTheReportNamesTheStepItCountedAsRunning(t *testing.T) {
	rows := jobaudit.Summarize([]jobaudit.Job{setupHeavyJob()}, jobaudit.Options{})
	if rows[0].RecipeStep != "Install the frozen tool set" {
		t.Fatalf("recipe step = %q, want the longest step, shown so a wrong guess is visible", rows[0].RecipeStep)
	}
	if out := jobaudit.Render(rows); !strings.Contains(out, `running = "Install the frozen tool set"`) {
		t.Fatalf("render does not name the running step:\n%s", out)
	}
}

// The report says in how many samples the counted step was the one it names,
// so a guess that is wrong in a few samples is visible.
func TestTheReportSaysHowManySamplesCountedTheNamedStep(t *testing.T) {
	normal := setupHeavyJob()
	normal.Steps[1] = step("Install the frozen tool set", 1, 10) // now the checks are longest
	normal.Steps[2] = step("Run just check", 10, 99)
	rows := jobaudit.Summarize([]jobaudit.Job{normal, normal, setupHeavyJob()}, jobaudit.Options{})
	if rows[0].RecipeStep != "Run just check" || rows[0].Agree != 2 {
		t.Fatalf("got step %q agree %d, want Run just check in 2 of 3", rows[0].RecipeStep, rows[0].Agree)
	}
	if out := jobaudit.Render(rows); !strings.Contains(out, `running = "Run just check" (2 of 3)`) {
		t.Fatalf("render does not show the agreement:\n%s", out)
	}
}

// A job with several recipe steps (the unit extras run three): running is the
// span from the first named step to the last.
func TestSeveralNamedStepsMakeOneRunningSpan(t *testing.T) {
	j := jobaudit.Job{
		Name: "extras", RunID: 1, Attempt: 1, Conclusion: "success",
		Created: at(0), Started: at(0), Completed: at(60),
		Steps: []jobaudit.Step{
			step("Set up job", 0, 1), step("Install", 1, 30),
			step("Corpora", 30, 40), step("Run actions/setup-go@x", 40, 45), step("Real Go tests", 45, 58),
			step("Complete job", 58, 60),
		},
	}
	opt := jobaudit.Options{RecipeSteps: map[string][]string{"extras": {"Corpora", "Real Go tests"}}}
	r := jobaudit.Summarize([]jobaudit.Job{j}, opt)[0]
	if r.Setup[0] != 30 || r.Running[0] != 28 || r.After[0] != 2 || r.Missing != 0 {
		t.Fatalf("setup %v running %v after %v missing %d, want 30/28/2/0", r.Setup, r.Running, r.After, r.Missing)
	}
}

// A named step that a job does not have (renamed in the workflow) is reported,
// not silently replaced by the guess.
func TestANamedStepThatIsMissingIsReported(t *testing.T) {
	opt := jobaudit.Options{RecipeSteps: map[string][]string{"just check (no container)": {"Renamed away"}}}
	r := jobaudit.Summarize([]jobaudit.Job{setupHeavyJob()}, opt)[0]
	if r.Missing != 1 {
		t.Fatalf("missing = %d, want 1", r.Missing)
	}
	if out := jobaudit.Render([]jobaudit.Row{r}); !strings.Contains(out, "named step missing in 1 of 1") {
		t.Fatalf("render does not report the missing step:\n%s", out)
	}
}

func TestANamedRecipeStepOverridesTheGuess(t *testing.T) {
	opt := jobaudit.Options{RecipeSteps: map[string][]string{"just check (no container)": {"Run just check"}}}
	rows := jobaudit.Summarize([]jobaudit.Job{setupHeavyJob()}, opt)
	r := rows[0]
	if r.RecipeStep != "Run just check" || r.Running[0] != 29 || r.Setup[0] != 70 || r.After[0] != 1 {
		t.Fatalf("got step %q running %v setup %v after %v, want Run just check 29/70/1", r.RecipeStep, r.Running, r.Setup, r.After)
	}
}

// Two workflows ran for one push. The pull request had its result when the
// last job of the first attempt finished, counted from when the first run was
// created. A re-run adds runner time but does not move that first result.
func TestPushesMeasureFromTheFirstRunToTheLastJobOfTheFirstAttempt(t *testing.T) {
	mk := func(workflow string, attempt int, created, started, completed int) jobaudit.Job {
		return jobaudit.Job{
			Name: workflow + " job", Workflow: workflow, RunID: int64(len(workflow) + attempt), Attempt: attempt,
			Conclusion: "success", HeadSHA: "abc", Event: "pull_request",
			RunCreated: at(created), Created: at(created), Started: at(started), Completed: at(completed),
		}
	}
	jobs := []jobaudit.Job{
		mk("a.yaml", 1, 0, 2, 40),
		mk("b.yaml", 1, 1, 3, 90),
		mk("b.yaml", 2, 200, 202, 230), // a re-run of b later
	}
	p := jobaudit.Pushes(jobs, jobaudit.PushOptions{})
	if len(p.Pushes) != 1 {
		t.Fatalf("pushes = %+v, want 1", p.Pushes)
	}
	got := p.Pushes[0]
	if got.Result != 90 {
		t.Errorf("result = %v, want 90 (run a created at 0, the last first-attempt job done at 90)", got.Result)
	}
	if got.RunnerSeconds != 38+87+28 {
		t.Errorf("runner seconds = %v, want %v (every attempt's wall time)", got.RunnerSeconds, 38+87+28)
	}
}

func pushJob(workflow, sha string, runID int64, created int) jobaudit.Job {
	return jobaudit.Job{
		Name: "j", Workflow: workflow, RunID: runID, Attempt: 1, Conclusion: "success", HeadSHA: sha, Event: "pull_request",
		RunCreated: at(created), Created: at(created), Started: at(created + 1), Completed: at(created + 10),
	}
}

// A workflow with a paths filter runs for some pushes only. A push it skipped
// is complete, and counts.
func TestPushesCountAPushThatAPathFilteredWorkflowSkipped(t *testing.T) {
	p := jobaudit.Pushes([]jobaudit.Job{
		pushJob("a.yaml", "one", 1, 0),
		pushJob("a.yaml", "two", 2, 100),
		pushJob("emulators.yaml", "two", 3, 100), // ran for push two only
	}, jobaudit.PushOptions{})
	if len(p.Pushes) != 2 || p.OutsideWindow != 0 {
		t.Fatalf("pushes = %+v, outside = %d, want both pushes", p.Pushes, p.OutsideWindow)
	}
}

// When a workflow's fetch was cut by the run limit, its older runs are
// unknown: a push that started before that workflow's oldest fetched run may
// be missing a run and would look too fast. It is left out and counted.
func TestPushesLeaveOutAPushThatStartedBeforeTheWindow(t *testing.T) {
	p := jobaudit.Pushes([]jobaudit.Job{
		pushJob("a.yaml", "one", 1, 0),
		pushJob("a.yaml", "two", 2, 100),
		pushJob("b.yaml", "two", 3, 100),
	}, jobaudit.PushOptions{WindowStart: at(100)}) // b.yaml's fetch was cut: its oldest fetched run is at 100
	if len(p.Pushes) != 1 || p.Pushes[0].HeadSHA != "two" || p.OutsideWindow != 1 {
		t.Fatalf("pushes = %+v, outside = %d, want push two only and 1 outside", p.Pushes, p.OutsideWindow)
	}
}

// A pull request closed and reopened on the same commit starts a second run of
// a workflow. Joined, the two would measure from the first run to the second
// one's end. Such a push is left out and counted.
func TestPushesLeaveOutACommitThatOneWorkflowRanTwice(t *testing.T) {
	p := jobaudit.Pushes([]jobaudit.Job{
		pushJob("a.yaml", "one", 1, 0),
		pushJob("a.yaml", "one", 2, 5000), // a second run, not a re-run (attempt 1 again)
		pushJob("a.yaml", "two", 3, 6000),
	}, jobaudit.PushOptions{})
	if len(p.Pushes) != 1 || p.Pushes[0].HeadSHA != "two" || p.Ambiguous != 1 {
		t.Fatalf("pushes = %+v, ambiguous = %d, want push two only and 1 ambiguous", p.Pushes, p.Ambiguous)
	}
}

func TestPushesLeaveOutACommitWithARunStillInProgress(t *testing.T) {
	p := jobaudit.Pushes([]jobaudit.Job{
		pushJob("a.yaml", "one", 1, 0),
		pushJob("a.yaml", "two", 2, 100), // b.yaml is still running for two
	}, jobaudit.PushOptions{Unfinished: []jobaudit.Commit{{HeadSHA: "two", Event: "pull_request"}}})
	if len(p.Pushes) != 1 || p.Pushes[0].HeadSHA != "one" || p.Unfinished != 1 {
		t.Fatalf("pushes = %+v, unfinished = %d, want push one only and 1 unfinished", p.Pushes, p.Unfinished)
	}
}

// concurrency's cancel-in-progress cancels a branch's runs when a new commit
// lands: that push never had its whole result. It is left out of the result
// sample and counted, and its jobs' time still counts as runner time.
func TestPushesLeaveOutACancelledPushButCountItsRunnerTime(t *testing.T) {
	cancelled := pushJob("b.yaml", "one", 2, 0)
	cancelled.Conclusion, cancelled.RunConclusion = "cancelled", "cancelled"
	cancelled.Completed = at(243) // ran 242 s before it was cancelled
	p := jobaudit.Pushes([]jobaudit.Job{pushJob("a.yaml", "one", 1, 0), cancelled, pushJob("a.yaml", "two", 3, 1000)}, jobaudit.PushOptions{})
	if len(p.Pushes) != 1 || p.Pushes[0].HeadSHA != "two" || p.Cancelled != 1 {
		t.Fatalf("pushes = %+v, cancelled = %d, want push two only and 1 cancelled", p.Pushes, p.Cancelled)
	}
	if p.TotalRunnerSeconds != 9+242+9 {
		t.Errorf("total runner seconds = %v, want %v (every job that ran, cancelled too)", p.TotalRunnerSeconds, 9+242+9)
	}
}

func TestPushesLeaveOutACommitWithARunThatWasNotRead(t *testing.T) {
	opt := jobaudit.PushOptions{Incomplete: []jobaudit.Commit{{HeadSHA: "one", Event: "pull_request"}}}
	p := jobaudit.Pushes([]jobaudit.Job{pushJob("a.yaml", "one", 1, 0), pushJob("a.yaml", "two", 2, 100)}, opt)
	if len(p.Pushes) != 1 || p.Pushes[0].HeadSHA != "two" || p.Incomplete != 1 {
		t.Fatalf("pushes = %+v, incomplete = %d, want push two only and 1 incomplete", p.Pushes, p.Incomplete)
	}
}

// Complete compares a commit's runs, as GitHub lists them, with the runs read.
func TestCompleteNeedsEveryRunOfAnAuditedWorkflow(t *testing.T) {
	audited := map[string]bool{"a.yaml": true, "b.yaml": true}
	read := map[int64]bool{1: true, 2: true}
	cases := []struct {
		name string
		runs []jobaudit.RunRef
		want bool
	}{
		{"every audited run was read", []jobaudit.RunRef{{ID: 1, Workflow: "a.yaml", Conclusion: "success"}, {ID: 2, Workflow: "b.yaml", Conclusion: "failure"}}, true},
		{"a run past a workflow's limit", []jobaudit.RunRef{{ID: 1, Workflow: "a.yaml", Conclusion: "success"}, {ID: 9, Workflow: "b.yaml", Conclusion: "success"}}, false},
		{"a skipped run (a draft) ran nothing", []jobaudit.RunRef{{ID: 1, Workflow: "a.yaml", Conclusion: "success"}, {ID: 9, Workflow: "b.yaml", Conclusion: "skipped"}}, true},
		{"a workflow that is not audited", []jobaudit.RunRef{{ID: 1, Workflow: "a.yaml", Conclusion: "success"}, {ID: 9, Workflow: "pages.yaml", Conclusion: "success"}}, true},
		{"a run still in progress", []jobaudit.RunRef{{ID: 1, Workflow: "a.yaml", Conclusion: "success"}, {ID: 9, Workflow: "b.yaml", Status: "in_progress"}}, false},
	}
	for _, c := range cases {
		if got := jobaudit.Complete(read, c.runs, audited); got != c.want {
			t.Errorf("%s: Complete = %v, want %v", c.name, got, c.want)
		}
	}
}

func TestRenderPushesSaysWhenNoPushCouldBeMeasured(t *testing.T) {
	out := jobaudit.RenderPushes(jobaudit.Pushes(nil, jobaudit.PushOptions{}))
	if !strings.Contains(out, "no push could be measured") || strings.Contains(out, "result 0/0s") {
		t.Fatalf("an empty sample must not print zeros as a result:\n%s", out)
	}
}

func TestRenderPrintsSampleSizeAndTheTotalRunnerSeconds(t *testing.T) {
	rows := jobaudit.Summarize([]jobaudit.Job{devcontainerJob()}, jobaudit.Options{})
	out := jobaudit.Render(rows)
	for _, want := range []string{"Required disposable Podman", "n=1", "waiting", "setup", "running", "after", "runner seconds"} {
		if !strings.Contains(out, want) {
			t.Errorf("render is missing %q:\n%s", want, out)
		}
	}
}
