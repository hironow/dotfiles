package main

import (
	"bytes"
	"strings"
	"testing"

	"github.com/hironow/dotfiles/tools/repo-lint/fake"
	"github.com/hironow/dotfiles/tools/repo-lint/internal/rules"
)

// wantsYes finds a value other than "yes" in a.toml.
var wantsYes = rules.Rule{
	ID:     "wants-yes",
	Why:    "a.toml says yes",
	Inputs: []rules.Input{{Path: "a.toml", Format: rules.TOML}},
	Check: func(in rules.Inputs) []rules.Finding {
		if v, _ := in["a.toml"].(map[string]any)["answer"].(string); v != "yes" {
			return []rules.Finding{{Path: "a.toml", Rule: "wants-yes", Message: "answer is " + v}}
		}
		return nil
	},
}

func runWith(src fake.Source, args ...string) (int, string, string) {
	var stdout, stderr bytes.Buffer
	code := run(args, &stdout, &stderr, src, []rules.Rule{wantsYes})
	return code, stdout.String(), stderr.String()
}

func TestRunPassesWhenEveryRuleHolds(t *testing.T) {
	code, out, _ := runWith(fake.Source{"a.toml": map[string]any{"answer": "yes"}})
	if code != 0 || out != "" {
		t.Fatalf("exit %d, stdout %q; want 0 and nothing", code, out)
	}
}

func TestRunPrintsEachFindingAndFails(t *testing.T) {
	code, out, _ := runWith(fake.Source{"a.toml": map[string]any{"answer": "no"}})
	if code != 1 || out != "a.toml: wants-yes: answer is no\n" {
		t.Fatalf("exit %d, stdout %q; want 1 and the finding", code, out)
	}
}

func TestRunStopsWhenAnInputCannotBeRead(t *testing.T) {
	code, out, errOut := runWith(fake.Source{})
	if code != 2 || out != "" || !strings.Contains(errOut, "a.toml") {
		t.Fatalf("exit %d, stdout %q, stderr %q; want 2 naming a.toml", code, out, errOut)
	}
}

func TestListNamesEveryRuleAndWhy(t *testing.T) {
	code, out, _ := runWith(fake.Source{}, "--list")
	if code != 0 || out != "wants-yes\ta.toml says yes\n" {
		t.Fatalf("exit %d, stdout %q", code, out)
	}
}

func TestEveryRealRuleHasAnIDAReasonAndInputs(t *testing.T) {
	seen := map[string]bool{}
	for _, r := range rules.All() {
		if r.ID == "" || r.Why == "" || len(r.Inputs) == 0 || r.Check == nil {
			t.Errorf("rule %q lacks an ID, a reason, inputs or a check", r.ID)
		}
		if seen[r.ID] {
			t.Errorf("rule %q is listed twice", r.ID)
		}
		seen[r.ID] = true
	}
}
