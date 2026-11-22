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
	rows := jobaudit.Summarize([]jobaudit.Job{a, b, c})
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
	if rows := jobaudit.Summarize([]jobaudit.Job{skipped, cancelled}); len(rows) != 0 {
		t.Fatalf("skipped and cancelled jobs must not count, got %+v", rows)
	}
}

func TestRenderPrintsSampleSizeAndTheTotalRunnerSeconds(t *testing.T) {
	rows := jobaudit.Summarize([]jobaudit.Job{devcontainerJob()})
	out := jobaudit.Render(rows)
	for _, want := range []string{"Required disposable Podman", "n=1", "waiting", "setup", "running", "after", "runner seconds"} {
		if !strings.Contains(out, want) {
			t.Errorf("render is missing %q:\n%s", want, out)
		}
	}
}
