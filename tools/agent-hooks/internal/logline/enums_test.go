package logline_test

import (
	"io/fs"
	"testing"

	json "github.com/goccy/go-json/v2"

	agenthooks "github.com/hironow/dotfiles/tools/agent-hooks"
	"github.com/hironow/dotfiles/tools/agent-hooks/harnesses"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/commandguard"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/fileguard"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/logline"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/secretguard"
)

func TestBuildListsEveryEmbeddedHarnessAndItsTools(t *testing.T) {
	names, err := fs.Glob(harnesses.FS, "*/harness.json")
	if err != nil || len(names) == 0 {
		t.Fatalf("embedded harnesses = %v, %v", names, err)
	}
	for _, name := range names {
		encoded, err := harnesses.FS.ReadFile(name)
		if err != nil {
			t.Fatal(err)
		}
		var definition struct {
			Name  string            `json:"name"`
			Tools map[string]string `json:"tools"`
		}
		if err := json.Unmarshal(encoded, &definition); err != nil {
			t.Fatal(err)
		}
		for tool, kind := range definition.Tools {
			f := logline.Firing{Harness: definition.Name, Call: &ir.Call{Tool: tool, Kind: kind}}
			got := build(f)
			if got.Harness != definition.Name || got.Tool != tool || got.Kind != kind {
				t.Errorf("%s/%s = %s/%s/%s", definition.Name, tool, got.Harness, got.Tool, got.Kind)
			}
		}
	}
}

func TestBuildChecksEnumsAndFallbacks(t *testing.T) {
	for _, c := range []struct {
		name   string
		firing logline.Firing
		want   map[string]string
	}{
		{"known pre", logline.Firing{Event: "pre"}, map[string]string{"event": "pre"}},
		{"known post", logline.Firing{Event: "post"}, map[string]string{"event": "post"}},
		{"unknown event", logline.Firing{Event: "PRE"}, map[string]string{"event": "other"}},
		{"unknown harness", logline.Firing{Harness: "claudesecret-marker"}, map[string]string{"harness": "other"}},
		{"no kind hides a known tool", logline.Firing{Harness: "claude", Call: &ir.Call{Tool: "Bash"}}, map[string]string{"tool": "other", "kind": "none"}},
		{"unknown kind", logline.Firing{Harness: "claude", Call: &ir.Call{Tool: "Bash", Kind: "future"}}, map[string]string{"tool": "Bash", "kind": "other"}},
		{"other harness tool", logline.Firing{Harness: "pi", Call: &ir.Call{Tool: "Bash", Kind: ir.KindShell}}, map[string]string{"tool": "other"}},
		{"call harness is ignored", logline.Firing{Harness: "unknown", Call: &ir.Call{Harness: "claude", Tool: "Bash", Kind: ir.KindShell}}, map[string]string{"tool": "other"}},
		{"tool prefix", logline.Firing{Harness: "claude", Call: &ir.Call{Tool: "Bashsecret-marker", Kind: ir.KindShell}}, map[string]string{"tool": "other"}},
		{"unknown hook", logline.Firing{Hook: "command-guardsecret-marker"}, map[string]string{"hook": "other"}},
		{"pass", logline.Firing{Outcome: ir.Outcome{Action: ir.Pass}}, map[string]string{"outcome": "pass"}},
		{"block", logline.Firing{Outcome: ir.Outcome{Action: ir.Block}}, map[string]string{"outcome": "block"}},
		{"forward", logline.Firing{Outcome: ir.Outcome{Action: ir.Forward}}, map[string]string{"outcome": "forward"}},
		{"rewrite", logline.Firing{Outcome: ir.Outcome{Action: ir.Rewrite}}, map[string]string{"outcome": "rewrite"}},
		{"unknown action", logline.Firing{Outcome: ir.Outcome{Action: ir.Action(99)}}, map[string]string{"outcome": "other"}},
		{"negative action", logline.Firing{Outcome: ir.Outcome{Action: ir.Action(-1)}}, map[string]string{"outcome": "other"}},
		{"unknown rule", logline.Firing{Outcome: ir.Outcome{Rule: "command.pipsecret-marker"}}, map[string]string{"rule": "other"}},
		{"unknown error", logline.Firing{Error: "hook.failedsecret-marker"}, map[string]string{"error": "other"}},
		{"unknown mismatch", logline.Firing{Mismatch: "inputsecret-marker"}, map[string]string{"mismatch": "other"}},
	} {
		t.Run(c.name, func(t *testing.T) {
			got := members(t, build(c.firing))
			for key, want := range c.want {
				if got[key] != want {
					t.Errorf("%s = %v; want %q", key, got[key], want)
				}
			}
		})
	}
}

func TestBuildListsEveryManifestHookAndGuardRule(t *testing.T) {
	var manifest struct {
		Hooks []struct {
			ID string `json:"id"`
		} `json:"hooks"`
	}
	if err := json.Unmarshal(agenthooks.Manifest, &manifest); err != nil {
		t.Fatal(err)
	}
	if len(manifest.Hooks) == 0 {
		t.Fatal("no manifest hooks")
	}
	for _, hook := range manifest.Hooks {
		if got := build(logline.Firing{Hook: hook.ID}).Hook; got != hook.ID {
			t.Errorf("hook %q = %q", hook.ID, got)
		}
	}
	rules := append(commandguard.Rules(), fileguard.Rules()...)
	rules = append(rules, secretguard.Rules()...)
	rules = append(rules, ir.RuleInputUnreadable, ir.RuleShimBroken, ir.RuleHookFailed)
	for _, rule := range rules {
		if got := build(logline.Firing{Outcome: ir.Outcome{Rule: rule}}).Rule; got != rule {
			t.Errorf("rule %q = %q", rule, got)
		}
	}
}

func TestBuildListsEveryErrorAndMismatch(t *testing.T) {
	for _, code := range []string{
		logline.ErrInputUnreadable, logline.ErrShimBroken, logline.ErrHookFailed,
		logline.ErrRewriteDropped, logline.ErrToolFailed, logline.ErrAnswerFailed, logline.ErrUsage,
	} {
		if got := build(logline.Firing{Error: code}).Error; got != code {
			t.Errorf("error %q = %q", code, got)
		}
	}
	for _, code := range []string{
		logline.MismatchEnvelope, logline.MismatchInput, logline.MismatchMapping, logline.MismatchUnchecked,
	} {
		if got := build(logline.Firing{Mismatch: code}).Mismatch; got != code {
			t.Errorf("mismatch %q = %q", code, got)
		}
	}
}
