package launch_test

import (
	"bytes"
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/fake"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/fileguard"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/guardcorpus"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/launch"
)

// flavors maps the corpus's basename(1) flavors to the port's. A run of a
// hook that does not use basename names none; any flavor will do.
var flavors = map[string]fileguard.Basename{
	"":    fileguard.BSDBasename,
	"bsd": fileguard.BSDBasename,
	"gnu": fileguard.GNUBasename,
}

func TestRunAnswersAsThePayloadCorpusExpects(t *testing.T) {
	payloads := guardcorpus.Payloads(t)
	if len(payloads) < 250 {
		t.Fatalf("payloads.jsonl has %d payloads; expected the whole corpus", len(payloads))
	}
	for _, payload := range payloads {
		for _, run := range payload.Runs {
			flavor, ok := flavors[run.Basename]
			if !ok {
				t.Fatalf("%s: unknown basename flavor %q", payload.Name, run.Basename)
			}
			var stdout, stderr bytes.Buffer
			exit := launch.Run([]string{run.Harness, "pre", "--hook", run.Hook},
				bytes.NewReader(payload.Stdin), &stdout, &stderr, &fake.Machine{Flavor: flavor})
			got := guardcorpus.Answer{Exit: exit, Stdout: stdout.String(), Stderr: stderr.String()}
			if got != run.ExpectedGo {
				t.Errorf("payloads.jsonl:%d %s, %s %s %s (difference %q):\n got %+v\nwant %+v",
					payload.Line, payload.Name, run.Harness, run.Hook, run.Basename, run.Difference,
					got, run.ExpectedGo)
			}
		}
	}
}
