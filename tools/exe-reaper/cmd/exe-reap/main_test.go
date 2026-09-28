package main

import (
	"bytes"
	"encoding/json"
	"slices"
	"strings"
	"testing"
)

func TestAPositionalArgumentIsRefused(t *testing.T) {
	// The tick takes no arguments and snapshot-gc is the one subcommand: any
	// other word is a typo in the CronJob, and guessing what it meant could
	// run the wrong thing.
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

func TestProtectedImagesArePinnedInARepositoryRetentionManages(t *testing.T) {
	// An image L1 cannot protect, named as protected, would be left to the
	// cleanup while the configuration says otherwise: refuse it instead.
	const digest = "sha256:aaaaaaaaaaaa1111111111111111111111111111111111111111111111111111"
	repos := []string{"projects/zz-p/locations/asia-northeast1/repositories/exe-platform"}
	enforcer := "asia-northeast1-docker.pkg.dev/zz-p/exe-platform/exe-l2@" + digest

	got, err := protectedImages(" "+enforcer+" ,, ", repos)
	if err != nil || !slices.Equal(got, []string{enforcer}) {
		t.Errorf("protected %q, %v; want [%s]", got, err, enforcer)
	}
	for _, bad := range []string{
		"asia-northeast1-docker.pkg.dev/zz-p/exe-platform/exe-l2:v1",  // a tag moves
		"asia-northeast1-docker.pkg.dev/zz-p/exe-task/task@" + digest, // not managed
		"ghcr.io/somewhere/else@" + digest,                            // not Artifact Registry
	} {
		if _, err := protectedImages(bad, repos); err == nil || !strings.Contains(err.Error(), envProtectImages) {
			t.Errorf("%s: err = %v, want a refusal naming %s", bad, err, envProtectImages)
		}
	}
}

func TestPodNamespacesAreACommaSeparatedList(t *testing.T) {
	if got, want := splitList(" ate-system,exe-ops ,,exe"), []string{"ate-system", "exe-ops", "exe"}; !slices.Equal(got, want) {
		t.Errorf("namespaces %q, want %q", got, want)
	}
}

func TestRepositoriesAreACommaSeparatedList(t *testing.T) {
	got := splitList(" projects/p/locations/l/repositories/a ,projects/p/locations/l/repositories/b,, ")
	want := []string{"projects/p/locations/l/repositories/a", "projects/p/locations/l/repositories/b"}
	if !slices.Equal(got, want) {
		t.Errorf("repos %q, want %q", got, want)
	}
}
