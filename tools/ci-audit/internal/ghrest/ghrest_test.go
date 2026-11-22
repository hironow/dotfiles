package ghrest_test

import (
	"context"
	"fmt"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/hironow/dotfiles/tools/ci-audit/internal/ghrest"
	"github.com/hironow/dotfiles/tools/ci-audit/internal/jobaudit"
)

// fakeRuns serves canned bodies by path. It records every path it was asked.
type fakeRuns struct {
	bodies map[string]string
	asked  []string
}

func (f *fakeRuns) Get(_ context.Context, path string) ([]byte, error) {
	f.asked = append(f.asked, path)
	body, ok := f.bodies[path]
	if !ok {
		return nil, fmt.Errorf("fake: no body for %s", path)
	}
	return []byte(body), nil
}

const jobsBody = `{"jobs":[
 {"name":"bun test","run_attempt":1,"conclusion":"success",
  "created_at":"2026-11-22T10:00:00Z","started_at":"2026-11-22T10:00:02Z","completed_at":"2026-11-22T10:00:12Z",
  "steps":[{"name":"Set up job","started_at":"2026-11-22T10:00:02Z","completed_at":"2026-11-22T10:00:03Z"},
           {"name":"just js-test","started_at":"2026-11-22T10:00:03Z","completed_at":"2026-11-22T10:00:11Z"},
           {"name":"Complete job","started_at":"2026-11-22T10:00:11Z","completed_at":"2026-11-22T10:00:12Z"}]},
 {"name":"Frontend CI","run_attempt":1,"conclusion":"success",
  "created_at":"2026-11-22T10:00:12Z","started_at":"2026-11-22T10:00:14Z","completed_at":"2026-11-22T10:00:18Z","steps":[]}]}`

const runsPath = "repos/o/r/actions/workflows/frontend-ci.yaml/runs?per_page=100"

func TestFetchReadsTheLastCompletedRunsJobs(t *testing.T) {
	api := &fakeRuns{bodies: map[string]string{
		runsPath + "&page=1": `{"workflow_runs":[
			{"id":11,"conclusion":"success","head_sha":"aaa","event":"pull_request","created_at":"2026-11-22T09:59:58Z"},
			{"id":12,"conclusion":"cancelled"},{"id":13,"conclusion":"failure"}]}`,
		"repos/o/r/actions/runs/11/jobs?per_page=100&filter=all&page=1": jobsBody,
	}}
	jobs, err := ghrest.Fetch(context.Background(), api, "o/r", "frontend-ci.yaml", ghrest.Filter{Limit: 2})
	if err != nil {
		t.Fatal(err)
	}
	if len(jobs) != 2 {
		t.Fatalf("jobs = %d, want 2 (run 11 only: 12 is cancelled, 13 is past the limit)", len(jobs))
	}
	if jobs[0].RunID != 11 || jobs[0].Attempt != 1 {
		t.Errorf("job 0 = %+v", jobs[0])
	}
	if jobs[0].Workflow != "frontend-ci.yaml" || jobs[0].HeadSHA != "aaa" || jobs[0].Event != "pull_request" || jobs[0].RunCreated.IsZero() {
		t.Errorf("job 0 lost its run: %+v", jobs[0])
	}
	rows := jobaudit.Summarize(jobs, jobaudit.Options{})
	for _, r := range rows {
		if r.Job == "Frontend CI" && r.Waiting[0] != 2 {
			t.Errorf("Frontend CI waiting = %v, want 2 (it was created when bun test finished)", r.Waiting[0])
		}
	}
}

// runPage is a page of completed runs with ids from first to last.
func runPage(first, last int64, conclusion string) string {
	var runs []string
	for id := first; id <= last; id++ {
		runs = append(runs, fmt.Sprintf(`{"id":%d,"conclusion":%q}`, id, conclusion))
	}
	return `{"workflow_runs":[` + strings.Join(runs, ",") + `]}`
}

func oneJob(attempt int, conclusion string) string {
	return fmt.Sprintf(`{"name":"j","run_attempt":%d,"conclusion":%q,
	  "created_at":"2026-11-22T10:00:00Z","started_at":"2026-11-22T10:00:01Z","completed_at":"2026-11-22T10:00:05Z","steps":[]}`, attempt, conclusion)
}

// The standard reads the last 150 runs; GitHub gives at most 100 a page.
func TestFetchReadsPastTheFirstPage(t *testing.T) {
	bodies := map[string]string{
		runsPath + "&page=1": runPage(1, 100, "success"),
		runsPath + "&page=2": runPage(101, 200, "success"),
	}
	for id := 1; id <= 200; id++ {
		bodies[fmt.Sprintf("repos/o/r/actions/runs/%d/jobs?per_page=100&filter=all&page=1", id)] = `{"jobs":[` + oneJob(1, "success") + `]}`
	}
	api := &fakeRuns{bodies: bodies}
	jobs, err := ghrest.Fetch(context.Background(), api, "o/r", "frontend-ci.yaml", ghrest.Filter{Limit: 150})
	if err != nil {
		t.Fatal(err)
	}
	if len(jobs) != 150 {
		t.Fatalf("jobs = %d, want 150 (one job in each of the last 150 runs)", len(jobs))
	}
}

// A failed first attempt, then a green re-run: both cost runner time, and the
// standard reads each attempt on its own. A job that ran into its timeout is
// the slow tail, and must count.
func TestFetchReadsEveryAttemptAndTimedOutRuns(t *testing.T) {
	api := &fakeRuns{bodies: map[string]string{
		runsPath + "&page=1": `{"workflow_runs":[{"id":7,"conclusion":"success"},{"id":8,"conclusion":"timed_out"}]}`,
		"repos/o/r/actions/runs/7/jobs?per_page=100&filter=all&page=1": `{"jobs":[` + oneJob(1, "failure") + `,` + oneJob(2, "success") + `]}`,
		"repos/o/r/actions/runs/8/jobs?per_page=100&filter=all&page=1": `{"jobs":[` + oneJob(1, "timed_out") + `]}`,
	}}
	jobs, err := ghrest.Fetch(context.Background(), api, "o/r", "frontend-ci.yaml", ghrest.Filter{Limit: 10})
	if err != nil {
		t.Fatal(err)
	}
	if len(jobs) != 3 {
		t.Fatalf("jobs = %d, want 3 (two attempts of run 7, the timed-out run 8)", len(jobs))
	}
	if rows := jobaudit.Summarize(jobs, jobaudit.Options{}); len(rows) != 1 || rows[0].Samples != 3 {
		t.Fatalf("rows = %+v, want one row with 3 samples", rows)
	}
}

// When the limit cuts the list, runs older than the oldest one read are
// unknown: Fetch says where its window starts. When every run was read, the
// window has no start.
func TestFetchSaysWhereItsWindowStartsOnlyWhenTheLimitCutTheList(t *testing.T) {
	bodies := map[string]string{
		runsPath + "&page=1": `{"workflow_runs":[
			{"id":1,"conclusion":"cancelled","created_at":"2026-11-22T10:00:09Z"},
			{"id":2,"conclusion":"cancelled","created_at":"2026-11-22T10:00:05Z"},
			{"id":3,"conclusion":"cancelled","created_at":"2026-11-22T10:00:01Z"}]}`,
	}
	cut, err := ghrest.FetchWindow(context.Background(), &fakeRuns{bodies: bodies}, "o/r", "frontend-ci.yaml", ghrest.Filter{Limit: 2})
	if err != nil {
		t.Fatal(err)
	}
	if want := "2026-11-22T10:00:05Z"; cut.WindowStart.Format(time.RFC3339) != want {
		t.Errorf("window start = %v, want %s (the oldest run read)", cut.WindowStart, want)
	}
	whole, err := ghrest.FetchWindow(context.Background(), &fakeRuns{bodies: bodies}, "o/r", "frontend-ci.yaml", ghrest.Filter{Limit: 10})
	if err != nil {
		t.Fatal(err)
	}
	if !whole.WindowStart.IsZero() {
		t.Errorf("window start = %v, want none: every run was read", whole.WindowStart)
	}
}

// A run still in progress has no jobs to measure, and its push would look
// finished and fast: Fetch names that commit, and does not count the run
// toward the limit.
func TestFetchNamesTheCommitsWithARunStillInProgress(t *testing.T) {
	api := &fakeRuns{bodies: map[string]string{
		runsPath + "&page=1": `{"workflow_runs":[
			{"id":9,"status":"in_progress","conclusion":null,"head_sha":"new","event":"pull_request"},
			{"id":8,"status":"completed","conclusion":"success","head_sha":"old","event":"pull_request"}]}`,
		"repos/o/r/actions/runs/8/jobs?per_page=100&filter=all&page=1": `{"jobs":[` + oneJob(1, "success") + `]}`,
	}}
	w, err := ghrest.FetchWindow(context.Background(), api, "o/r", "frontend-ci.yaml", ghrest.Filter{Limit: 1})
	if err != nil {
		t.Fatal(err)
	}
	if len(w.Jobs) != 1 || w.Jobs[0].HeadSHA != "old" {
		t.Fatalf("jobs = %+v, want the completed run's job: an unfinished run does not use up the limit", w.Jobs)
	}
	if len(w.Unfinished) != 1 || w.Unfinished[0] != (jobaudit.Commit{HeadSHA: "new", Event: "pull_request"}) {
		t.Fatalf("unfinished = %+v, want commit new", w.Unfinished)
	}
}

func TestFetchNarrowsTheRunsByBranchAndEvent(t *testing.T) {
	api := &fakeRuns{bodies: map[string]string{
		runsPath + "&branch=feat%2Fx&event=pull_request&page=1": `{"workflow_runs":[]}`,
	}}
	if _, err := ghrest.Fetch(context.Background(), api, "o/r", "frontend-ci.yaml", ghrest.Filter{Limit: 5, Branch: "feat/x", Event: "pull_request"}); err != nil {
		t.Fatalf("asked %v: %v", api.asked, err)
	}
}

func TestFetchReportsAFailedCallInsteadOfReturningFewerJobs(t *testing.T) {
	api := &fakeRuns{bodies: map[string]string{}}
	if _, err := ghrest.Fetch(context.Background(), api, "o/r", "x.yaml", ghrest.Filter{Limit: 5}); err == nil || !strings.Contains(err.Error(), "list runs") {
		t.Fatalf("want a list-runs error, got %v", err)
	}
}

// TestRealRunsMatchTheOwnersNumbers reads the 374 runs that the audit saved on
// 2026-11-22 (REST bodies in a folder) and checks one row against the numbers
// the same data gave with jq: bun check, p50 11 s total, 53 samples.
func TestRealRunsMatchTheOwnersNumbers(t *testing.T) {
	dir := os.Getenv("CI_AUDIT_REAL_JOBS_DIR")
	if dir == "" {
		t.Skip("CI_AUDIT_REAL_JOBS_DIR is not set")
	}
	entries, err := os.ReadDir(dir)
	if err != nil {
		t.Fatal(err)
	}
	var all []jobaudit.Job
	for _, e := range entries {
		body, err := os.ReadFile(dir + "/" + e.Name())
		if err != nil {
			t.Fatal(err)
		}
		var id int64
		fmt.Sscanf(strings.TrimSuffix(e.Name(), ".json"), "%d", &id)
		jobs, err := ghrest.ParseJobs(id, body)
		if err != nil {
			t.Fatal(err)
		}
		all = append(all, jobs...)
	}
	rows := jobaudit.Summarize(all, jobaudit.Options{})
	found := map[string]jobaudit.Row{}
	for _, r := range rows {
		found[r.Job] = r
	}
	check := found["bun check"]
	if check.Samples != 53 {
		t.Errorf("bun check samples = %d, want 53", check.Samples)
	}
	if check.Total[0] < 10 || check.Total[0] > 12 {
		t.Errorf("bun check total p50 = %v, want about 11", check.Total[0])
	}
	dev := found["Required disposable Podman devcontainer build/up/exec"]
	if dev.Running[1] < 1700 || dev.Running[1] > 1800 {
		t.Errorf("devcontainer running p95 = %v, want about 1750", dev.Running[1])
	}
	if dev.Waiting[1] > 5 {
		t.Errorf("devcontainer waiting p95 = %v, want within the 5 s budget", dev.Waiting[1])
	}
}
