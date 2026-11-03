package launch

import (
	"bytes"
	"strings"
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/fake"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
)

func TestAHookThatPanicsPasses(t *testing.T) {
	// As the old guards' internal exceptions pass: the panic is told on
	// stderr, and the call goes on.
	panicking := map[string]hook{"files-guard": func(ir.Call, Machine) ir.Outcome { panic("broken") }}
	for _, harness := range []string{"claude", "codex"} {
		var stdout, stderr bytes.Buffer
		exit := run([]string{harness, "pre", "--hook", "files-guard"},
			strings.NewReader(`{"tool_input":{"file_path":"a.yml"}}`), &stdout, &stderr, &fake.Machine{}, panicking)
		if exit != 0 || stdout.Len() != 0 || !strings.Contains(stderr.String(), "broken") {
			t.Errorf("%s: exit %d, stdout %q, stderr %q; want exit 0, no stdout, the panic on stderr",
				harness, exit, stdout.String(), stderr.String())
		}
	}
}
