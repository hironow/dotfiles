// Package ghrest reads completed workflow runs and their jobs from GitHub's REST
// API, through a small port so that tests use a fake and never the network.
package ghrest

import (
	"context"
	"errors"
	"fmt"
	"os/exec"
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

// Fetch returns the jobs of the last `limit` completed runs of one workflow.
// Failed and successful runs count; every job comes with its run attempt.
func Fetch(ctx context.Context, api Runs, repo, workflow string, limit int) ([]jobaudit.Job, error) {
	listPath := fmt.Sprintf("repos/%s/actions/workflows/%s/runs?per_page=%d&status=completed", repo, workflow, min(limit, 100))
	body, err := api.Get(ctx, listPath)
	if err != nil {
		return nil, fmt.Errorf("list runs of %s: %w", workflow, err)
	}
	var runs struct {
		WorkflowRuns []struct {
			ID         int64  `json:"id"`
			Conclusion string `json:"conclusion"`
		} `json:"workflow_runs"`
	}
	if err := json.Unmarshal(body, &runs); err != nil {
		return nil, fmt.Errorf("read runs of %s: %w", workflow, err)
	}
	var jobs []jobaudit.Job
	for i, run := range runs.WorkflowRuns {
		if i >= limit {
			break
		}
		if run.Conclusion != "success" && run.Conclusion != "failure" {
			continue
		}
		got, err := fetchJobs(ctx, api, repo, run.ID)
		if err != nil {
			return nil, err
		}
		jobs = append(jobs, got...)
	}
	return jobs, nil
}

func fetchJobs(ctx context.Context, api Runs, repo string, runID int64) ([]jobaudit.Job, error) {
	body, err := api.Get(ctx, fmt.Sprintf("repos/%s/actions/runs/%d/jobs?per_page=100&filter=latest", repo, runID))
	if err != nil {
		return nil, fmt.Errorf("jobs of run %d: %w", runID, err)
	}
	return ParseJobs(runID, body)
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
