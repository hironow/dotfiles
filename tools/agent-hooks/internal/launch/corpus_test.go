package launch_test

import (
	"bytes"
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/fake"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/guardcorpus"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/launch"
)

func TestRunAnswersAsThePayloadCorpusExpects(t *testing.T) {
	payloads := guardcorpus.Payloads(t)
	if len(payloads) < 250 {
		t.Fatalf("payloads.jsonl has %d payloads; expected the whole corpus", len(payloads))
	}
	for _, payload := range payloads {
		for _, run := range payload.Runs {
			name := guardcorpus.Frame(run.Difference) + "/" + payload.Name + "/" + run.Harness + "/" + run.Hook + "/" + run.Basename
			t.Run(name, func(t *testing.T) {
				var stdout, stderr bytes.Buffer
				exit := launch.Run([]string{run.Harness, "pre", "--hook", run.Hook},
					bytes.NewReader(payload.Stdin), &stdout, &stderr, &fake.Machine{})
				got := guardcorpus.Answer{Exit: exit, Stdout: stdout.String(), Stderr: stderr.String()}
				if got != run.ExpectedGo {
					t.Errorf("payloads.jsonl:%d (difference %q):\n got %+v\nwant %+v",
						payload.Line, run.Difference, got, run.ExpectedGo)
				}
			})
		}
	}
}
