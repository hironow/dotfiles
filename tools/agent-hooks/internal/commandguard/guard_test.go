package commandguard_test

import (
	"fmt"
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/commandguard"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/guardcorpus"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
)

func TestCheckAgreesWithThePythonGuardOnTheCorpus(t *testing.T) {
	// The port answers as the Python guard with its bugs fixed
	// (scripts/old_script_fixes.py). Each subtest is in its frame: "parity"
	// where that is the old guard's answer, else the fixes it needs, so that
	// `go test -run '/fixed-'` lists where the port differs on purpose.
	for _, entry := range guardcorpus.Entries(t) {
		t.Run(fmt.Sprintf("%s/line-%d", entry.Frame(), entry.Line), func(t *testing.T) {
			// given an input of the corpus, when the guard checks it
			outcome := commandguard.Check(entry.Input)
			// then it blocks, with the same reason, exactly when the fixed Python guard did
			if entry.Fixed == nil {
				if outcome.Action != ir.Pass {
					t.Fatalf("Check(%q) blocked (%s: %s); Python passed it", entry.Input, outcome.Rule, outcome.Reason)
				}
				return
			}
			if outcome.Action != ir.Block || outcome.Reason != *entry.Fixed {
				t.Fatalf("Check(%q) = %v %q; Python blocked: %q", entry.Input, outcome.Action, outcome.Reason, *entry.Fixed)
			}
		})
	}
}

func TestEveryBlockNamesItsRule(t *testing.T) {
	cases := []struct {
		command string
		rule    string
	}{
		{"pip install x", commandguard.RulePythonPackages},
		{"npm ci", commandguard.RuleNodePackages},
		{"corepack pnpm i", commandguard.RuleNodePackages},
		{"make build", commandguard.RuleMake},
		{"git push -f origin main", commandguard.RuleForcePush},
		{"touch a.yml", commandguard.RuleYMLFile},
		{"echo x > docker-compose.yaml", commandguard.RuleYMLFile},
		{"rm -rf /", commandguard.RuleRootDeletion},
		{"gcloud projects add-iam-policy-binding p", commandguard.RuleGcloudIAM},
		{"gcloud run deploy api", commandguard.RuleGcloudInfra},
		{"echo \"unclosed npm i", commandguard.RuleNodePackages},
		{"bash <<EOF\nmake\nEOF", commandguard.RuleMake},
		{"rtk run -c 'pip install x'", commandguard.RulePythonPackages},
	}
	for _, c := range cases {
		t.Run(c.command, func(t *testing.T) {
			// given a command the guard blocks, when it checks it
			outcome := commandguard.Check(c.command)
			// then the outcome names the rule that blocked it
			if outcome.Action != ir.Block || outcome.Rule != c.rule {
				t.Fatalf("Check(%q) = %v rule %q; want block by %q", c.command, outcome.Action, outcome.Rule, c.rule)
			}
		})
	}
}

func TestAPassNamesNoRule(t *testing.T) {
	outcome := commandguard.Check("uv add httpx")
	if outcome != (ir.Outcome{Action: ir.Pass}) {
		t.Fatalf("Check(%q) = %+v; want a bare pass", "uv add httpx", outcome)
	}
}
