package ghrest_test

import (
	"context"
	"fmt"
	"os"
	"strings"
	"testing"

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

func TestFetchReadsTheLastCompletedRunsJobs(t *testing.T) {
	api := &fakeRuns{bodies: map[string]string{
		"repos/o/r/actions/workflows/frontend-ci.yaml/runs?per_page=2&status=completed": `{"workflow_runs":[
			{"id":11,"conclusion":"success"},{"id":12,"conclusion":"cancelled"},{"id":13,"conclusion":"failure"}]}`,
		"repos/o/r/actions/runs/11/jobs?per_page=100&filter=latest": jobsBody,
	}}
	jobs, err := ghrest.Fetch(context.Background(), api, "o/r", "frontend-ci.yaml", 2)
	if err != nil {
		t.Fatal(err)
	}
	if len(jobs) != 2 {
		t.Fatalf("jobs = %d, want 2 (run 11 only: 12 is cancelled, 13 is past the limit)", len(jobs))
	}
	if jobs[0].RunID != 11 || jobs[0].Attempt != 1 {
		t.Errorf("job 0 = %+v", jobs[0])
	}
	rows := jobaudit.Summarize(jobs)
	for _, r := range rows {
		if r.Job == "Frontend CI" && r.Waiting[0] != 2 {
			t.Errorf("Frontend CI waiting = %v, want 2 (it was created when bun test finished)", r.Waiting[0])
		}
	}
}

func TestFetchReportsAFailedCallInsteadOfReturningFewerJobs(t *testing.T) {
	api := &fakeRuns{bodies: map[string]string{}}
	if _, err := ghrest.Fetch(context.Background(), api, "o/r", "x.yaml", 5); err == nil || !strings.Contains(err.Error(), "list runs") {
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
	rows := jobaudit.Summarize(all)
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
