// Package ghrest reads completed workflow runs and their jobs from GitHub's REST
// API, through a small port so that tests use a fake and never the network.
package ghrest

import (
	"context"
	"errors"
	"fmt"
	"net/url"
	"os/exec"
	"path"
	"strings"
	"time"

	"github.com/goccy/go-json"

	"github.com/hironow/dotfiles/tools/ci-audit/internal/jobaudit"
)

// Runs is the port: what the audit needs from GitHub. Its real adapter is
// GH, which runs the `gh` CLI (so the token stays in gh's own store).
type Runs interface {
	// Get returns the body of a GitHub REST path, such as "repos/o/r/actions/runs".
	Get(ctx context.Context, path string) ([]byte, error)
}

// Filter says which runs Fetch reads.
type Filter struct {
	// Limit is how many completed runs to read, newest first.
	Limit int
	// Branch and Event narrow the runs ("" reads every branch or event), so a
	// before/after comparison reads a fixed sample.
	Branch string
	Event  string
}

// perPage is the largest page GitHub's REST API gives.
const perPage = 100

// Window is what FetchWindow read.
type Window struct {
	Jobs []jobaudit.Job
	// WindowStart is the creation time of the oldest run read, when the run
	// limit cut the list (older runs exist and were not read); zero when every
	// run was read.
	WindowStart time.Time
	// Unfinished are the commits with a run of this workflow still in
	// progress. Their runs do not count toward the limit.
	Unfinished []jobaudit.Commit
}

// Fetch returns the jobs of the last f.Limit completed runs of one workflow,
// every attempt of each (see FetchWindow).
func Fetch(ctx context.Context, api Runs, repo, workflow string, f Filter) ([]jobaudit.Job, error) {
	w, err := FetchWindow(ctx, api, repo, workflow, f)
	return w.Jobs, err
}

// FetchWindow returns the jobs of the last f.Limit completed runs of one
// workflow, every attempt of each, and where its window starts. Runs that
// succeeded, failed, or timed out count; a cancelled or skipped run measured
// nothing.
func FetchWindow(ctx context.Context, api Runs, repo, workflow string, f Filter) (Window, error) {
	query := url.Values{}
	if f.Branch != "" {
		query.Set("branch", f.Branch)
	}
	if f.Event != "" {
		query.Set("event", f.Event)
	}
	extra := ""
	if len(query) > 0 {
		extra = "&" + query.Encode()
	}
	var jobs []jobaudit.Job
	var oldest time.Time
	var unfinished []jobaudit.Commit
	read, cut := 0, false
	for page := 1; read < f.Limit; page++ {
		// Every status: an unfinished run must be seen to leave its push out.
		listPath := fmt.Sprintf("repos/%s/actions/workflows/%s/runs?per_page=%d%s&page=%d", repo, workflow, perPage, extra, page)
		body, err := api.Get(ctx, listPath)
		if err != nil {
			return Window{}, fmt.Errorf("list runs of %s: %w", workflow, err)
		}
		var runs struct {
			WorkflowRuns []runJSON `json:"workflow_runs"`
		}
		if err := json.Unmarshal(body, &runs); err != nil {
			return Window{}, fmt.Errorf("read runs of %s: %w", workflow, err)
		}
		for _, run := range runs.WorkflowRuns {
			if run.Status != "" && run.Status != "completed" {
				unfinished = append(unfinished, jobaudit.Commit{HeadSHA: run.HeadSHA, Event: run.Event})
				continue
			}
			if read >= f.Limit {
				cut = true // a run past the limit is in this page
				break
			}
			read++
			if created := parseTime(run.CreatedAt); oldest.IsZero() || created.Before(oldest) {
				oldest = created
			}
			// A cancelled run ran jobs (runner time) and left its push without
			// a whole result; a skipped one (a draft) ran nothing.
			switch run.Conclusion {
			case "success", "failure", "timed_out", "cancelled":
			default:
				continue
			}
			got, err := fetchJobs(ctx, api, repo, run.ID)
			if err != nil {
				return Window{}, err
			}
			for i := range got {
				got[i].Workflow = workflow
				got[i].HeadSHA = run.HeadSHA
				got[i].Event = run.Event
				got[i].RunCreated = parseTime(run.CreatedAt)
				got[i].RunConclusion = run.Conclusion
			}
			jobs = append(jobs, got...)
		}
		if len(runs.WorkflowRuns) < perPage {
			break
		}
		if read >= f.Limit {
			cut = true // a full page at the limit: a next page may hold more
		}
	}
	w := Window{Jobs: jobs, Unfinished: unfinished}
	if cut {
		w.WindowStart = oldest
	}
	return w, nil
}

// CommitRuns lists every run GitHub made for one commit and event, in every
// workflow.
func CommitRuns(ctx context.Context, api Runs, repo string, c jobaudit.Commit) ([]jobaudit.RunRef, error) {
	query := url.Values{}
	query.Set("head_sha", c.HeadSHA)
	query.Set("event", c.Event)
	var refs []jobaudit.RunRef
	for page := 1; ; page++ {
		body, err := api.Get(ctx, fmt.Sprintf("repos/%s/actions/runs?%s&per_page=%d&page=%d", repo, query.Encode(), perPage, page))
		if err != nil {
			return nil, fmt.Errorf("runs of commit %s: %w", c.HeadSHA, err)
		}
		var runs struct {
			WorkflowRuns []runJSON `json:"workflow_runs"`
		}
		if err := json.Unmarshal(body, &runs); err != nil {
			return nil, fmt.Errorf("read runs of commit %s: %w", c.HeadSHA, err)
		}
		for _, r := range runs.WorkflowRuns {
			refs = append(refs, jobaudit.RunRef{ID: r.ID, Workflow: path.Base(r.Path), Status: r.Status, Conclusion: r.Conclusion})
		}
		if len(runs.WorkflowRuns) < perPage {
			return refs, nil
		}
	}
}

type runJSON struct {
	Path       string `json:"path"`
	ID         int64  `json:"id"`
	Status     string `json:"status"`
	Conclusion string `json:"conclusion"`
	HeadSHA    string `json:"head_sha"`
	Event      string `json:"event"`
	CreatedAt  string `json:"created_at"`
}

// fetchJobs reads every page of a run's jobs, of every attempt (filter=all).
func fetchJobs(ctx context.Context, api Runs, repo string, runID int64) ([]jobaudit.Job, error) {
	var all []jobaudit.Job
	for page := 1; ; page++ {
		body, err := api.Get(ctx, fmt.Sprintf("repos/%s/actions/runs/%d/jobs?per_page=%d&filter=all&page=%d", repo, runID, perPage, page))
		if err != nil {
			return nil, fmt.Errorf("jobs of run %d: %w", runID, err)
		}
		got, err := ParseJobs(runID, body)
		if err != nil {
			return nil, err
		}
		all = append(all, got...)
		if len(got) < perPage {
			return all, nil
		}
	}
}

type jobJSON struct {
	Name        string `json:"name"`
	RunAttempt  int    `json:"run_attempt"`
	Conclusion  string `json:"conclusion"`
	CreatedAt   string `json:"created_at"`
	StartedAt   string `json:"started_at"`
	CompletedAt string `json:"completed_at"`
	Steps       []struct {
		Name        string `json:"name"`
		StartedAt   string `json:"started_at"`
		CompletedAt string `json:"completed_at"`
	} `json:"steps"`
}

// ParseJobs reads the body of a run's jobs endpoint.
func ParseJobs(runID int64, body []byte) ([]jobaudit.Job, error) {
	var parsed struct {
		Jobs []jobJSON `json:"jobs"`
	}
	if err := json.Unmarshal(body, &parsed); err != nil {
		return nil, fmt.Errorf("read jobs of run %d: %w", runID, err)
	}
	jobs := make([]jobaudit.Job, 0, len(parsed.Jobs))
	for _, j := range parsed.Jobs {
		job := jobaudit.Job{
			Name: j.Name, RunID: runID, Attempt: j.RunAttempt, Conclusion: j.Conclusion,
			Created: parseTime(j.CreatedAt), Started: parseTime(j.StartedAt), Completed: parseTime(j.CompletedAt),
		}
		for _, s := range j.Steps {
			job.Steps = append(job.Steps, jobaudit.Step{Name: s.Name, Started: parseTime(s.StartedAt), Completed: parseTime(s.CompletedAt)})
		}
		jobs = append(jobs, job)
	}
	return jobs, nil
}

func parseTime(s string) time.Time {
	t, err := time.Parse(time.RFC3339, s)
	if err != nil {
		return time.Time{}
	}
	return t
}

// GH is the real adapter: it asks the `gh` CLI.
type GH struct{}

// Get runs `gh api PATH`.
func (GH) Get(ctx context.Context, path string) ([]byte, error) {
	out, err := exec.CommandContext(ctx, "gh", "api", path).Output()
	if err != nil {
		var exit *exec.ExitError
		if errors.As(err, &exit) {
			return nil, fmt.Errorf("gh api %s: %w: %s", path, err, strings.TrimSpace(string(exit.Stderr)))
		}
		return nil, fmt.Errorf("gh api %s: %w", path, err)
	}
	return out, nil
}
