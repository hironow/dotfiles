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

func TestANamedRecipeStepOverridesTheGuess(t *testing.T) {
	opt := jobaudit.Options{RecipeSteps: map[string]string{"just check (no container)": "Run just check"}}
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
	p := jobaudit.Pushes(jobs)
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

// When the window of fetched runs cuts a push in half (one workflow's older
// runs are past its limit), its result would look too fast: leave it out and
// say so.
func TestPushesLeaveOutAPushThatMissesAWorkflow(t *testing.T) {
	job := func(workflow, sha string) jobaudit.Job {
		return jobaudit.Job{
			Name: "j", Workflow: workflow, Attempt: 1, Conclusion: "success", HeadSHA: sha, Event: "pull_request",
			RunCreated: at(0), Created: at(0), Started: at(1), Completed: at(10),
		}
	}
	p := jobaudit.Pushes([]jobaudit.Job{job("a.yaml", "one"), job("b.yaml", "one"), job("a.yaml", "two")})
	if len(p.Pushes) != 1 || p.Pushes[0].HeadSHA != "one" {
		t.Fatalf("pushes = %+v, want only the complete push one", p.Pushes)
	}
	if p.Partial != 1 {
		t.Errorf("partial = %d, want 1", p.Partial)
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
