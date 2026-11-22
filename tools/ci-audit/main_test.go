package main

import (
	"bytes"
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
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

func TestShardsNeedsTheCollectedListAndAReport(t *testing.T) {
	var stdout, stderr bytes.Buffer
	if code := run(context.Background(), []string{"shards", "--junit", "x.xml"}, &stdout, &stderr, noNetwork{}); code != 2 {
		t.Fatalf("exit %d, want 2", code)
	}
}

func TestUnknownCommandIsAUsageError(t *testing.T) {
	var stdout, stderr bytes.Buffer
	if code := run(context.Background(), []string{"frobnicate"}, &stdout, &stderr, noNetwork{}); code != 2 {
		t.Fatalf("exit %d, want 2", code)
	}
}
