package launch_test

import (
	"encoding/base64"
	"os"
	"slices"
	"strings"
	"testing"
	"time"

	json "github.com/goccy/go-json/v2"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/fake"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/process"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/toolhookcorpus/pirtk"
)

// TestPiRTKAnswersAsTheRtkTsCorpusExpects replays every scenario of
// internal/toolhookcorpus/pi-rtk.jsonl, which records what the vendored
// config/pi/extensions/rtk.ts did under Pi 1.4.0 (`just pi-rtk-corpus`),
// through the binary. The binary's answer is the corpus's binaryCommand:
// rtk.ts's own result, except where a run names its differences. Each
// subtest is named by its frame: parity, or the difference IDs.
func TestPiRTKAnswersAsTheRtkTsCorpusExpects(t *testing.T) {
	corpus, err := os.ReadFile("../toolhookcorpus/pi-rtk.jsonl")
	if err != nil {
		t.Fatal(err)
	}
	_, entries, err := pirtk.Parse(corpus)
	if err != nil {
		t.Fatal(err)
	}
	if len(entries) == 0 {
		t.Fatal("the corpus has no scenario")
	}
	for _, entry := range entries {
		frame := "parity"
		if len(entry.Differences) > 0 {
			frame = strings.Join(entry.Differences, "+")
		}
		t.Run(frame+"/"+entry.Name, func(t *testing.T) {
			m := replayMachine(t, entry)
			input, err := json.Marshal(map[string]any{"command": entry.Scenario.Command})
			if err != nil {
				t.Fatal(err)
			}
			got := run(t, m, piRequest("pre", "bash", string(input)), "pi", "pre", "--hook", "rtk")
			want := shimPass
			if entry.BinaryCommand != nil {
				command, err := json.Marshal(*entry.BinaryCommand)
				if err != nil {
					t.Fatal(err)
				}
				want = `{"v":1,"action":"rewrite","set":{"command":` + string(command) + "}}\n"
			}
			if got != (result{stdout: want}) {
				t.Errorf("%+v, want stdout %q", got, want)
			}
			checkReplay(t, m)
		})
	}
}

// replayMachine is the scenario's machine as the binary sees it: rtk where
// the scenario's PATH puts it, its environment, and, when the binary runs
// `rtk rewrite`, the fake's answer as one whole read of its pipes gives it,
// stderr apart from stdout.
func replayMachine(t *testing.T, entry pirtk.Entry) *fake.Machine {
	t.Helper()
	m := &fake.Machine{Env: entry.Env, Programs: map[string]process.Program{}}
	switch entry.Fake.Path {
	case "absolute":
		m.Programs["rtk"] = process.Program{Path: "/fake/rtk"}
	case "relative":
		m.Programs["rtk"] = process.Program{Path: "bin/rtk", Relative: true}
	case "absent":
	default:
		t.Fatalf("unknown placement %q", entry.Fake.Path)
	}
	if entry.Fake.Path != "absolute" || !runsRewrite(entry) {
		return m
	}
	rewrite := entry.Fake.Rewrite
	stdout := decode(t, rewrite.StdoutB64) + decode(t, rewrite.LateB64)
	invocation := fake.Invocation{
		Command: process.Command{
			Path: "/fake/rtk", Args: []string{"rtk", "rewrite", entry.Scenario.Command.(string)}, Timeout: 2 * time.Second,
		},
	}
	switch {
	case rewrite.SleepMs > 2000:
		invocation.Failed = true // killed at the timeout
	case rewrite.Signal:
		invocation.Result = process.Result{Stdout: []byte(stdout), Stderr: []byte(rewrite.Stderr), Exit: -1, Signaled: true}
	default:
		invocation.Result = process.Result{Stdout: []byte(stdout), Stderr: []byte(rewrite.Stderr), Exit: rewrite.Exit}
	}
	m.Replay = []fake.Invocation{invocation}
	return m
}

// runsRewrite is whether the binary asks `rtk rewrite`, read off the oracle,
// not the code under test: rtk.ts asked it, so its gates passed; or rtk.ts
// never registered (it probes the version once, which the binary does not),
// where the scenario's command passes the gates.
func runsRewrite(entry pirtk.Entry) bool {
	for _, argv := range entry.Argv {
		if len(argv) > 0 && argv[0] == "rewrite" {
			return true
		}
	}
	return !entry.Registered && slices.Contains(entry.Differences, "rtk-version-probe")
}

func decode(t *testing.T, b64 string) string {
	t.Helper()
	raw, err := base64.StdEncoding.DecodeString(b64)
	if err != nil {
		t.Fatal(err)
	}
	return string(raw)
}
