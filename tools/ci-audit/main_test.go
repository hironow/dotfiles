package main

import (
	"bytes"
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/goccy/go-json"
)

type noNetwork struct{}

func (noNetwork) Get(context.Context, string) ([]byte, error) {
	panic("the shards command must not call GitHub")
}

const collectedList = "tests/unit/test_a.py::test_one\ntests/unit/test_a.py::test_two\ntests/unit/test_b.py::test_three\n"

func junit(cases ...string) string {
	return `<?xml version="1.0"?><testsuites><testsuite name="pytest">` + strings.Join(cases, "") + `</testsuite></testsuites>`
}

func tc(class, name string, seconds string) string {
	return `<testcase classname="` + class + `" name="` + name + `" time="` + seconds + `"/>`
}

func write(t *testing.T, dir, name, body string) string {
	t.Helper()
	path := filepath.Join(dir, name)
	if err := os.WriteFile(path, []byte(body), 0o644); err != nil {
		t.Fatal(err)
	}
	return path
}

func TestShardsPassesAndWritesDurationsKeyedByNodeID(t *testing.T) {
	dir := t.TempDir()
	list := write(t, dir, "all.txt", collectedList)
	one := write(t, dir, "1.xml", junit(tc("tests.unit.test_a", "test_one", "1"), tc("tests.unit.test_b", "test_three", "1")))
	two := write(t, dir, "2.xml", junit(tc("tests.unit.test_a", "test_two", "2")))
	out := filepath.Join(dir, "durations.json")
	var stdout, stderr bytes.Buffer
	code := run(context.Background(), []string{"shards", "--collected", list, "--junit", one, "--junit", two, "--durations-out", out}, &stdout, &stderr, noNetwork{})
	if code != 0 {
		t.Fatalf("exit %d\nstdout:\n%s\nstderr:\n%s", code, stdout.String(), stderr.String())
	}
	data, err := os.ReadFile(out)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(data), `"tests/unit/test_a.py::test_two": 2`) {
		t.Fatalf("durations are not keyed by node id:\n%s", data)
	}
}

func TestShardsFailsWhenACaseWasDropped(t *testing.T) {
	dir := t.TempDir()
	list := write(t, dir, "all.txt", collectedList)
	one := write(t, dir, "1.xml", junit(tc("tests.unit.test_a", "test_one", "1")))
	two := write(t, dir, "2.xml", junit(tc("tests.unit.test_a", "test_two", "1"))) // test_three never ran
	var stdout, stderr bytes.Buffer
	code := run(context.Background(), []string{"shards", "--collected", list, "--junit", one, "--junit", two, "--max-imbalance", "0"}, &stdout, &stderr, noNetwork{})
	if code != 1 {
		t.Fatalf("exit %d, want 1\nstderr:\n%s", code, stderr.String())
	}
	if !strings.Contains(stderr.String(), "tests/unit/test_b.py::test_three") {
		t.Fatalf("the dropped test is not named:\n%s", stderr.String())
	}
}

// Each shard writes its own collected list, and pytest ends that list with a
// summary line that holds the collection time. Two runs differ there and
// nowhere else, so the lists must be compared by their ids, not their bytes.
func TestShardsComparesEachShardsListByItsIDs(t *testing.T) {
	dir := t.TempDir()
	listOne := write(t, dir, "all-1.txt", collectedList+"\n3 tests collected in 0.68s\n")
	listTwo := write(t, dir, "all-2.txt", collectedList+"\n3 tests collected in 1.00s\n")
	one := write(t, dir, "1.xml", junit(tc("tests.unit.test_a", "test_one", "1"), tc("tests.unit.test_b", "test_three", "1")))
	two := write(t, dir, "2.xml", junit(tc("tests.unit.test_a", "test_two", "2")))
	var stdout, stderr bytes.Buffer
	args := []string{"shards", "--collected", listOne, "--collected", listTwo, "--junit", one, "--junit", two, "--max-imbalance", "0"}
	if code := run(context.Background(), args, &stdout, &stderr, noNetwork{}); code != 0 {
		t.Fatalf("exit %d\nstdout:\n%s\nstderr:\n%s", code, stdout.String(), stderr.String())
	}
}

func TestShardsFailsWhenOneShardCollectedADifferentList(t *testing.T) {
	dir := t.TempDir()
	listOne := write(t, dir, "all-1.txt", collectedList)
	listTwo := write(t, dir, "all-2.txt", "tests/unit/test_a.py::test_one\ntests/unit/test_a.py::test_two\n")
	one := write(t, dir, "1.xml", junit(tc("tests.unit.test_a", "test_one", "1"), tc("tests.unit.test_b", "test_three", "1")))
	two := write(t, dir, "2.xml", junit(tc("tests.unit.test_a", "test_two", "2")))
	var stdout, stderr bytes.Buffer
	args := []string{"shards", "--collected", listOne, "--collected", listTwo, "--junit", one, "--junit", two, "--max-imbalance", "0"}
	if code := run(context.Background(), args, &stdout, &stderr, noNetwork{}); code != 1 {
		t.Fatalf("exit %d, want 1\nstderr:\n%s", code, stderr.String())
	}
	if !strings.Contains(stderr.String(), "collected a different list") {
		t.Fatalf("the differing shard is not reported:\n%s", stderr.String())
	}
}

func TestShardsNeedsOneCollectedListOrOnePerShard(t *testing.T) {
	dir := t.TempDir()
	list := write(t, dir, "all.txt", collectedList)
	one := write(t, dir, "1.xml", junit(tc("tests.unit.test_a", "test_one", "1")))
	var stdout, stderr bytes.Buffer
	args := []string{"shards", "--collected", list, "--collected", list, "--junit", one}
	if code := run(context.Background(), args, &stdout, &stderr, noNetwork{}); code != 2 {
		t.Fatalf("exit %d, want 2 (two lists for one report)", code)
	}
}

// A module that skips itself at collection (POSIX-only modules on Windows)
// is not a test, but it must stay visible in the gate's output.
func TestShardsNamesTheModulesSkippedAtCollection(t *testing.T) {
	dir := t.TempDir()
	list := write(t, dir, "all.txt", collectedList)
	skip := `<testcase classname="" name="tests.unit.test_posix_only" time="0.000"><skipped message="collection skipped"/></testcase>`
	one := write(t, dir, "1.xml", junit(tc("tests.unit.test_a", "test_one", "1"), tc("tests.unit.test_b", "test_three", "1"), skip))
	two := write(t, dir, "2.xml", junit(tc("tests.unit.test_a", "test_two", "2"), skip))
	var stdout, stderr bytes.Buffer
	args := []string{"shards", "--collected", list, "--junit", one, "--junit", two, "--max-imbalance", "0"}
	if code := run(context.Background(), args, &stdout, &stderr, noNetwork{}); code != 0 {
		t.Fatalf("exit %d\nstdout:\n%s\nstderr:\n%s", code, stdout.String(), stderr.String())
	}
	if !strings.Contains(stdout.String(), "1 module skipped itself at collection: tests.unit.test_posix_only") {
		t.Fatalf("the skipped module is not named:\n%s", stdout.String())
	}
}

func TestShardsNeedsTheCollectedListAndAReport(t *testing.T) {
	var stdout, stderr bytes.Buffer
	if code := run(context.Background(), []string{"shards", "--junit", "x.xml"}, &stdout, &stderr, noNetwork{}); code != 2 {
		t.Fatalf("exit %d, want 2", code)
	}
}

func TestARecipeStepThatIsNotJobEqualsStepIsAUsageError(t *testing.T) {
	var stdout, stderr bytes.Buffer
	args := []string{"jobs", "--repo", "o/r", "--recipe-step", "no-equals-sign", "x.yaml"}
	if code := run(context.Background(), args, &stdout, &stderr, noNetwork{}); code != 2 {
		t.Fatalf("exit %d, want 2\n%s", code, stderr.String())
	}
}

// fakeAPI serves canned bodies by path.
type fakeAPI map[string]string

func (f fakeAPI) Get(_ context.Context, path string) ([]byte, error) {
	body, ok := f[path]
	if !ok {
		return nil, fmt.Errorf("fake: no body for %s", path)
	}
	return []byte(body), nil
}

func runBody(id int64, sha string, created string) string {
	return fmt.Sprintf(`{"id":%d,"status":"completed","conclusion":"success","head_sha":%q,"event":"pull_request","created_at":%q}`, id, sha, created)
}

func jobBody(name, created, started, completed string) string {
	return fmt.Sprintf(`{"jobs":[{"name":%q,"run_attempt":1,"conclusion":"success","created_at":%q,"started_at":%q,"completed_at":%q,"steps":[]}]}`,
		name, created, started, completed)
}

// a.yaml reads both pushes; b.yaml reads only its newest run (limit 1), and
// GitHub's list for push "one" holds b.yaml's run 21, which was not read. The
// window rule alone would keep "one" if b.yaml's oldest read run were older,
// so the check against the commit's runs is what leaves it out.
func TestJobsLeavesOutAPushWithARunThatWasNotRead(t *testing.T) {
	api := fakeAPI{
		"repos/o/r/actions/workflows/a.yaml/runs?per_page=100&event=pull_request&page=1": `{"workflow_runs":[` +
			runBody(12, "two", "2026-11-22T10:10:00Z") + `,` + runBody(11, "one", "2026-11-22T10:00:00Z") + `]}`,
		"repos/o/r/actions/workflows/b.yaml/runs?per_page=100&event=pull_request&page=1": `{"workflow_runs":[` +
			runBody(22, "two", "2026-11-22T10:10:01Z") + `]}`,
		"repos/o/r/actions/runs/11/jobs?per_page=100&filter=all&page=1": jobBody("a", "2026-11-22T10:00:00Z", "2026-11-22T10:00:01Z", "2026-11-22T10:00:20Z"),
		"repos/o/r/actions/runs/12/jobs?per_page=100&filter=all&page=1": jobBody("a", "2026-11-22T10:10:00Z", "2026-11-22T10:10:01Z", "2026-11-22T10:10:20Z"),
		"repos/o/r/actions/runs/22/jobs?per_page=100&filter=all&page=1": jobBody("b", "2026-11-22T10:10:01Z", "2026-11-22T10:10:02Z", "2026-11-22T10:10:40Z"),
		"repos/o/r/actions/runs?event=pull_request&head_sha=one&per_page=100&page=1": `{"workflow_runs":[
			{"id":11,"status":"completed","conclusion":"success","path":".github/workflows/a.yaml"},
			{"id":21,"status":"completed","conclusion":"success","path":".github/workflows/b.yaml"}]}`,
		"repos/o/r/actions/runs?event=pull_request&head_sha=two&per_page=100&page=1": `{"workflow_runs":[
			{"id":12,"status":"completed","conclusion":"success","path":".github/workflows/a.yaml"},
			{"id":22,"status":"completed","conclusion":"success","path":".github/workflows/b.yaml"}]}`,
	}
	var stdout, stderr bytes.Buffer
	args := []string{"jobs", "--repo", "o/r", "--runs", "2", "--event", "pull_request", "a.yaml", "b.yaml"}
	if code := run(context.Background(), args, &stdout, &stderr, api); code != 0 {
		t.Fatalf("exit %d\n%s", code, stderr.String())
	}
	out := stdout.String()
	if !strings.Contains(out, "pushes n=1") || !strings.Contains(out, "1 with a run that was not read") {
		t.Fatalf("want push two only, and push one left out:\n%s", out)
	}
}

func TestUnknownCommandIsAUsageError(t *testing.T) {
	var stdout, stderr bytes.Buffer
	if code := run(context.Background(), []string{"frobnicate"}, &stdout, &stderr, noNetwork{}); code != 2 {
		t.Fatalf("exit %d, want 2", code)
	}
}

// The cases of a secret scanner's own tests carry credential-shaped text in
// their ids. The durations file is committed, and GitHub's push protection and
// the repo's private-key hook reject such text, so those ids are left out.
func TestDurationsFileLeavesOutIDsThatHoldCredentialShapedText(t *testing.T) {
	dir := t.TempDir()
	token := "gh" + "p_" + strings.Repeat("a", 36)
	list := write(t, dir, "all.txt", "tests/unit/test_a.py::test_one\ntests/unit/test_s.py::test_shape["+token+"]\n")
	one := write(t, dir, "1.xml", junit(tc("tests.unit.test_a", "test_one", "1"), tc("tests.unit.test_s", "test_shape["+token+"]", "1")))
	out := filepath.Join(dir, "durations.json")
	var stdout, stderr bytes.Buffer
	args := []string{"shards", "--collected", list, "--junit", one, "--max-imbalance", "0", "--durations-out", out}
	if code := run(context.Background(), args, &stdout, &stderr, noNetwork{}); code != 0 {
		t.Fatalf("exit %d\n%s", code, stderr.String())
	}
	data, err := os.ReadFile(out)
	if err != nil {
		t.Fatal(err)
	}
	var got map[string]float64
	if err := json.Unmarshal(data, &got); err != nil {
		t.Fatal(err)
	}
	if len(got) != 1 {
		t.Fatalf("want only the plain test, got %v", got)
	}
	if _, ok := got["tests/unit/test_a.py::test_one"]; !ok {
		t.Fatalf("the plain test is missing: %v", got)
	}
}
