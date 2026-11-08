package rendercorpus_test

import (
	"bufio"
	"bytes"
	"os"
	"testing"

	json "github.com/goccy/go-json/v2"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/registration"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/rendercorpus"
)

func TestEveryRecordedRenderMatchesMain(t *testing.T) {
	corpus, err := os.ReadFile("render.jsonl")
	if err != nil {
		t.Fatalf("%v; run just agent-hooks-render-corpus", err)
	}
	scanner := bufio.NewScanner(bytes.NewReader(corpus))
	seen := map[string]bool{}
	for scanner.Scan() {
		var entry struct {
			Case   string   `json:"case"`
			Args   []string `json:"args"`
			Exit   int      `json:"exit"`
			Stdout string   `json:"stdout"`
			Stderr string   `json:"stderr"`
		}
		if err := json.Unmarshal(scanner.Bytes(), &entry, json.RejectUnknownMembers(true)); err != nil {
			t.Fatal(err)
		}
		if entry.Case == "" || seen[entry.Case] {
			t.Fatalf("empty or repeated case %q", entry.Case)
		}
		seen[entry.Case] = true
		t.Run(entry.Case, func(t *testing.T) {
			var stdout, stderr bytes.Buffer
			exit := registration.Main(entry.Args, &stdout, &stderr)
			if exit != entry.Exit || stdout.String() != entry.Stdout || stderr.String() != entry.Stderr {
				t.Fatalf("recorded render differs: exit %d, stdout %q, stderr %q; run just agent-hooks-render-corpus", exit, &stdout, &stderr)
			}
		})
	}
	if err := scanner.Err(); err != nil {
		t.Fatal(err)
	}
	if len(seen) == 0 {
		t.Fatal("empty corpus; run just agent-hooks-render-corpus")
	}
}

func TestRecordedCorpusIncludesEveryCurrentCase(t *testing.T) {
	fresh, err := rendercorpus.Generate()
	if err != nil {
		t.Fatal(err)
	}
	stored, err := os.ReadFile("render.jsonl")
	if err != nil {
		t.Fatalf("%v; run just agent-hooks-render-corpus", err)
	}
	if !bytes.Equal(fresh, stored) {
		t.Fatal("render corpus is stale; run just agent-hooks-render-corpus")
	}
}
