package pirtk_test

import (
	"bytes"
	"crypto/sha256"
	"encoding/base64"
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/pipath/pioracle"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/toolhookcorpus/pirtk"
)

func oraclePaths(t *testing.T) (node, root, extension string) {
	t.Helper()
	node, root, err := pioracle.FindPackage()
	if err != nil {
		t.Skip(err)
	}
	if _, err := os.Stat("/bin/sh"); err != nil {
		t.Skipf("/bin/sh unavailable: %v", err)
	}
	extension, err = filepath.Abs("../../../../../config/pi/extensions/rtk.ts")
	if err != nil {
		t.Fatal(err)
	}
	return node, root, extension
}

func TestCorpusIsFresh(t *testing.T) {
	node, root, extension := oraclePaths(t)
	scenarios := pirtk.Scenarios()
	answers, err := pirtk.Run(node, root, extension, scenarios)
	if err != nil {
		t.Fatal(err)
	}
	source, err := os.ReadFile(extension)
	if err != nil {
		t.Fatal(err)
	}
	fresh, err := pirtk.Render(source, scenarios, answers)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(fresh, readCorpus(t)) {
		t.Fatal("Pi's rtk answers changed; run just pi-rtk-corpus")
	}
	t.Logf("ran all %d scenarios with Pi %s; corpus is byte-identical", len(scenarios), pioracle.PiVersion)
}

func TestCorpusPinsTheVendoredExtensionHash(t *testing.T) {
	source, err := os.ReadFile("../../../../../config/pi/extensions/rtk.ts")
	if err != nil {
		t.Fatal(err)
	}
	header, entries, err := pirtk.Parse(readCorpus(t))
	if err != nil {
		t.Fatal(err)
	}
	if want := fmt.Sprintf("%x", sha256.Sum256(source)); header.RtkTs != want {
		t.Fatalf("rtk.ts hash %s; corpus has %s; run just pi-rtk-corpus", want, header.RtkTs)
	}
	if len(entries) != len(pirtk.Scenarios()) {
		t.Fatalf("corpus has %d scenarios, want %d", len(entries), len(pirtk.Scenarios()))
	}
}

func readCorpus(t *testing.T) []byte {
	t.Helper()
	corpus, err := os.ReadFile("../pi-rtk.jsonl")
	if err != nil {
		t.Fatal(err)
	}
	return corpus
}

func TestCorpusIsRenderedFromTheScenarios(t *testing.T) {
	// Where node or Pi is missing (CI), the corpus must still be what Render
	// makes of Scenarios() and the answers it records, so that a changed
	// scenario, or a hand edit of what the binary must do, shows as stale.
	corpus, err := os.ReadFile("../pi-rtk.jsonl")
	if err != nil {
		t.Fatal(err)
	}
	source, err := os.ReadFile("../../../../../config/pi/extensions/rtk.ts")
	if err != nil {
		t.Fatal(err)
	}
	_, entries, err := pirtk.Parse(corpus)
	if err != nil {
		t.Fatal(err)
	}
	answers := make([]pirtk.Answer, len(entries))
	for i, entry := range entries {
		answers[i] = entry.Answer
	}
	rendered, err := pirtk.Render(source, pirtk.Scenarios(), answers)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(rendered, corpus) {
		t.Fatal("the corpus is not what Render makes of Scenarios(); run just pi-rtk-corpus")
	}
}

func TestRunRecordsPiProcessEdgeCases(t *testing.T) {
	node, root, extension := oraclePaths(t)
	for _, test := range []struct {
		name    string
		stdout  string
		rewrite pirtk.Rewrite
		want    string
	}{
		// Exit 1 if the signal failed: only a signal death rewrites.
		{"signal", "rtk git status", pirtk.Rewrite{Signal: true, Exit: 1}, "rtk git status"},
		{"exit-1-control", "rtk git status", pirtk.Rewrite{Exit: 1}, "git status"},
		{"invalid-utf8", "rtk \xff git", pirtk.Rewrite{}, "rtk \ufffd git"},
		{"split-utf8", "rtk echo 雪", pirtk.Rewrite{PauseAt: 10}, "rtk echo \ufffd\ufffd\ufffd"},
		{"late-output", "rtk git status", pirtk.Rewrite{LateB64: "IC0tc2hvcnQ=", LateMs: 350}, "rtk git status"},
		// Inside the grace the tail arrives: the child does write.
		{"late-in-grace", "rtk git status", pirtk.Rewrite{LateB64: "IC0tc2hvcnQ=", LateMs: 10}, "rtk git status --short"},
		{"timeout", "rtk git status", pirtk.Rewrite{SleepMs: 3000}, "git status"},
	} {
		t.Run(test.name, func(t *testing.T) {
			test.rewrite.StdoutB64 = base64.StdEncoding.EncodeToString([]byte(test.stdout))
			scenario := pirtk.Scenario{
				Name: test.name, Command: "git status", Env: map[string]string{},
				Fake: pirtk.Fake{Path: "absolute", Version: pirtk.Version{Stdout: "rtk 1.1.0\n"}, Rewrite: test.rewrite},
			}
			answers, err := pirtk.Run(node, root, extension, []pirtk.Scenario{scenario})
			if err != nil {
				t.Fatal(err)
			}
			if len(answers) != 1 || !answers[0].Registered || answers[0].Command != test.want {
				t.Fatalf("Pi answered %+v; want %q", answers, test.want)
			}
		})
	}
}

func TestRunUsesPiExecAndLogsArgv(t *testing.T) {
	node, root, extension := oraclePaths(t)
	scenarios := []pirtk.Scenario{{
		Name: "rewrite-exit-0", Command: "git status", Env: map[string]string{},
		Fake: pirtk.Fake{
			Path: "absolute", Version: pirtk.Version{Stdout: "rtk 1.1.0\n"},
			Rewrite: pirtk.Rewrite{StdoutB64: "cnRrIGdpdCBzdGF0dXM="},
		},
	}}
	answers, err := pirtk.Run(node, root, extension, scenarios)
	if err != nil {
		t.Fatal(err)
	}
	want := []pirtk.Answer{{
		Registered: true, Argv: [][]string{{"--version"}, {"rewrite", "git status"}}, Command: "rtk git status",
	}}
	if !reflect.DeepEqual(answers, want) {
		t.Fatalf("Pi answered %+v; want %+v", answers, want)
	}
}
