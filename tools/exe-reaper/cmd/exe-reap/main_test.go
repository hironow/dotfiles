package main

import (
	"bytes"
	"encoding/json"
	"slices"
	"strings"
	"testing"
)

func TestAPositionalArgumentIsRefused(t *testing.T) {
	// exe-reap has one job and no subcommands yet: a stray word is a typo in
	// the CronJob, and guessing what it meant could run the wrong thing.
	var stdout, stderr bytes.Buffer
	if code := run([]string{"reap"}, &stdout, &stderr); code != 2 {
		t.Errorf("exit %d, want 2", code)
	}
	if !strings.Contains(stderr.String(), "no arguments") {
		t.Errorf("stderr %q, want it to say why", stderr.String())
	}
}

func TestAMissingBucketFailsWithAFailureLine(t *testing.T) {
	// The CronJob's log is where a misconfigured L1 shows up, so even this
	// failure is a contract line, not free text.
	t.Setenv(envBucket, "")
	var stdout, stderr bytes.Buffer
	if code := run(nil, &stdout, &stderr); code != 1 {
		t.Fatalf("exit %d, want 1", code)
	}
	var line struct {
		Severity string `json:"severity"`
		L1       struct {
			Event string `json:"event"`
		} `json:"exe_l1"`
	}
	if err := json.Unmarshal(bytes.TrimSpace(stdout.Bytes()), &line); err != nil {
		t.Fatalf("stdout %q is not one JSON line: %v", stdout.String(), err)
	}
	if line.Severity != severityError || line.L1.Event != "failure" {
		t.Errorf("line %+v, want an ERROR failure", line)
	}
}

func TestMissingRepositoriesFailWithAFailureLine(t *testing.T) {
	// Without the repositories to protect, retention would tag nothing, and
	// Artifact Registry's cleanup would collect the images of suspended
	// tasks. Refusing to run is the loud way to find out.
	t.Setenv(envBucket, "zz-ops")
	t.Setenv(envARRepos, "")
	var stdout, stderr bytes.Buffer
	if code := run(nil, &stdout, &stderr); code != 1 {
		t.Fatalf("exit %d, want 1", code)
	}
	if !strings.Contains(stdout.String(), envARRepos) {
		t.Errorf("stdout %q does not name %s", stdout.String(), envARRepos)
	}
}

func TestRepositoriesAreACommaSeparatedList(t *testing.T) {
	got := splitRepos(" projects/p/locations/l/repositories/a ,projects/p/locations/l/repositories/b,, ")
	want := []string{"projects/p/locations/l/repositories/a", "projects/p/locations/l/repositories/b"}
	if !slices.Equal(got, want) {
		t.Errorf("repos %q, want %q", got, want)
	}
}
