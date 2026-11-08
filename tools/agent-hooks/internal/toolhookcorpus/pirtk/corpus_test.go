package pirtk_test

import (
	"bytes"
	"crypto/sha256"
	"fmt"
	"os"
	"reflect"
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/toolhookcorpus/pirtk"
)

func TestRenderParsePreservesTheOracleRun(t *testing.T) {
	scenarios := []pirtk.Scenario{{
		Name: "rewrite-exit-0", Command: "git status", Env: map[string]string{},
		Fake: pirtk.Fake{
			Path: "absolute", Version: pirtk.Version{Stdout: "rtk 1.1.0\n"},
			Rewrite: pirtk.Rewrite{StdoutB64: "cnRrIGdpdCBzdGF0dXM="},
		},
	}}
	answers := []pirtk.Answer{{
		Registered: true, Argv: [][]string{{"--version"}, {"rewrite", "git status"}}, Command: "rtk git status",
	}}
	extension := []byte("vendored extension\n")
	corpus, err := pirtk.Render(extension, scenarios, answers)
	if err != nil {
		t.Fatal(err)
	}
	header, entries, err := pirtk.Parse(corpus)
	if err != nil {
		t.Fatal(err)
	}
	if header.Pi != "1.4.0" || header.RtkTs != fmt.Sprintf("%x", sha256.Sum256(extension)) {
		t.Fatalf("wrong provenance: %+v", header)
	}
	if len(entries) != 1 || !reflect.DeepEqual(entries[0].Scenario, scenarios[0]) ||
		!reflect.DeepEqual(entries[0].Answer, answers[0]) || entries[0].BinaryCommand == nil ||
		*entries[0].BinaryCommand != "rtk git status" || len(entries[0].Differences) != 0 {
		t.Fatalf("changed the oracle run: %+v", entries)
	}
	if !bytes.Contains(corpus, []byte(`"env":{}`)) || !bytes.Contains(corpus, []byte(`"differences":[]`)) ||
		!bytes.Contains(corpus, []byte(`"piRegistered":true`)) || !bytes.HasSuffix(corpus, []byte("\n")) {
		t.Fatalf("wrong JSONL shape: %s", corpus)
	}
}

func TestRenderRecordsTheNamedBinaryDifferences(t *testing.T) {
	want := map[string]struct {
		difference string
		binary     string
	}{
		"path-relative":        {"path-relative", ""},
		"version-exit-1":       {"rtk-version-probe", "rtk git status"},
		"version-old":          {"rtk-version-probe", "rtk git status"},
		"rewrite-signal":       {"rtk-signal", ""},
		"rewrite-invalid-utf8": {"rtk-answer-invalid-utf8", ""},
		"rewrite-split-utf8":   {"rtk-split-utf8", "rtk echo 雪"},
		"rewrite-late-output":  {"rtk-late-output", "rtk git status --short"},
	}
	seen := map[string]bool{}
	for _, scenario := range pirtk.Scenarios() {
		if seen[scenario.Name] {
			t.Fatalf("duplicate scenario %q", scenario.Name)
		}
		seen[scenario.Name] = true
		expected, ok := want[scenario.Name]
		if !ok {
			continue
		}
		corpus, err := pirtk.Render(nil, []pirtk.Scenario{scenario}, []pirtk.Answer{{Command: "observed rewrite"}})
		if err != nil {
			t.Fatal(err)
		}
		_, entries, err := pirtk.Parse(corpus)
		if err != nil {
			t.Fatal(err)
		}
		entry := entries[0]
		if !reflect.DeepEqual(entry.Differences, []string{expected.difference}) {
			t.Errorf("%s differences: %v", scenario.Name, entry.Differences)
		}
		if expected.binary == "" {
			if entry.BinaryCommand != nil {
				t.Errorf("%s must pass, got %q", scenario.Name, *entry.BinaryCommand)
			}
		} else if entry.BinaryCommand == nil || *entry.BinaryCommand != expected.binary {
			t.Errorf("%s binary command: %v; want %q", scenario.Name, entry.BinaryCommand, expected.binary)
		}
	}
	for name := range want {
		if !seen[name] {
			t.Errorf("missing scenario %s", name)
		}
	}
}

func TestCorpusIsASCII(t *testing.T) {
	// Some tools split lines on U+2028 or U+0085; the corpus holds none.
	corpus, err := os.ReadFile("../pi-rtk.jsonl")
	if err != nil {
		t.Fatal(err)
	}
	for i, b := range corpus {
		if b > 0x7f {
			t.Fatalf("byte %d is not ASCII; run just pi-rtk-corpus", i)
		}
	}
}
