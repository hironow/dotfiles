package launch

import (
	"bytes"
	"strings"
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/harnesses"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/fake"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
)

func TestARewriteTheCodecRefusesPasses(t *testing.T) {
	// A rewrite the codec cannot write into the payload (here, a field Pi's
	// definition does not map) is no rewrite: the call goes on as it is, and
	// why is told on stderr.
	payload, err := harnesses.FS.ReadFile("pi/fixtures/pre-bash.json")
	if err != nil {
		t.Fatal(err)
	}
	for _, set := range []ir.Assignment{
		{Field: "noSuchField", Value: "x"},
		{Field: ir.ListContents, Value: "x"},
	} {
		rewriting := map[string]hook{"rtk": func(ir.Call, Machine) ir.Outcome {
			return ir.Outcome{Action: ir.Rewrite, Set: set}
		}}
		var stdout, stderr bytes.Buffer
		exit := run([]string{"pi", "pre", "--hook", "rtk"}, bytes.NewReader(payload), &stdout, &stderr, &fake.Machine{}, rewriting)
		if exit != 0 || stdout.String() != `{"v":1,"action":"pass"}`+"\n" || !strings.Contains(stderr.String(), "rewrite") {
			t.Errorf("%+v: exit %d, stdout %q, stderr %q; want the pass and why", set, exit, stdout.String(), stderr.String())
		}
	}
	// The control: a rewrite of the command it maps goes through.
	rewriting := map[string]hook{"rtk": func(ir.Call, Machine) ir.Outcome {
		return ir.Outcome{Action: ir.Rewrite, Set: ir.Assignment{Field: ir.FieldCommand, Value: "rtk ls"}}
	}}
	var stdout, stderr bytes.Buffer
	run([]string{"pi", "pre", "--hook", "rtk"}, bytes.NewReader(payload), &stdout, &stderr, &fake.Machine{}, rewriting)
	if want := `{"v":1,"action":"rewrite","set":{"command":"rtk ls"}}` + "\n"; stdout.String() != want {
		t.Errorf("the control: stdout %q, want %q", stdout.String(), want)
	}
}
