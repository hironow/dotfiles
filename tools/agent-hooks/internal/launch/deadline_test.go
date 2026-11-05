package launch

import (
	"bytes"
	"fmt"
	"io"
	"strconv"
	"strings"
	"testing"
	"time"

	json "github.com/goccy/go-json/v2"

	agenthooks "github.com/hironow/dotfiles/tools/agent-hooks"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/fake"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/logline"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/process"
)

type timedAnswer struct {
	bytes.Buffer
	written chan time.Time
}

func (w *timedAnswer) Write(p []byte) (int, error) {
	w.written <- time.Now()
	return w.Buffer.Write(p)
}

func (w *timedAnswer) WriteString(s string) (int, error) {
	return w.Write([]byte(s))
}

func TestStageDeadlineAnswersWithoutStdinEOF(t *testing.T) {
	for _, id := range []string{"command-guard", "rtk", "formatter"} {
		t.Run(id, func(t *testing.T) {
			stdin, input := io.Pipe()
			defer stdin.Close()
			defer input.Close()
			event := "pre"
			if id == "formatter" {
				event = "post"
			}
			stdout := &timedAnswer{written: make(chan time.Time, 4)}
			var stderr bytes.Buffer
			sink := &fake.LogSink{}
			done := make(chan int, 1)
			start := time.Now()
			go func() {
				done <- run([]string{"claude", event, "--hook", id}, stdin, stdout, &stderr,
					&fake.Machine{}, sink, hooks, 40*time.Millisecond)
			}()
			select {
			case written := <-stdout.written:
				if elapsed := written.Sub(start); elapsed > 140*time.Millisecond {
					t.Errorf("answer took %s, want deadline + 100 ms", elapsed)
				}
			case <-time.After(time.Second):
				input.Close()
				<-done
				t.Fatal("no answer by the deadline")
			}
			input.Close()
			exit := <-done
			wantExit, wantOutcome, wantRule := 0, "pass", ""
			if id == "command-guard" {
				wantExit, wantOutcome, wantRule = 2, "block", "hook.timeout"
				if !strings.Contains(stderr.String(), "did not finish in time") {
					t.Errorf("timeout reason missing: %q", stderr.String())
				}
			} else if stderr.Len() != 0 || stdout.Len() != 0 {
				t.Errorf("open timeout wrote stdout %q stderr %q", stdout.String(), stderr.String())
			}
			entries := sink.Lines()
			if len(entries) != 1 {
				t.Fatalf("%d log lines, want one", len(entries))
			}
			line, err := logline.Parse(entries[0].Line)
			if err != nil || exit != wantExit || line.Error != "hook.timeout" || line.Rule != wantRule || line.Outcome != wantOutcome || line.Tool != "other" || line.Kind != "none" || line.Mismatch != "" {
				t.Errorf("exit %d, line %+v, %v", exit, line, err)
			}
		})
	}
}

func TestStageDropsLateAnswersAndDiagnostics(t *testing.T) {
	for _, late := range []bool{false, true} {
		t.Run(strconv.FormatBool(late), func(t *testing.T) {
			release := make(chan struct{})
			decide := func(ir.Call, Machine) ir.Outcome {
				if late {
					<-release
				}
				panic("worker diagnostic")
			}
			stdout := &timedAnswer{written: make(chan time.Time, 4)}
			var stderr bytes.Buffer
			sink := &fake.LogSink{}
			done := make(chan int, 1)
			go func() {
				done <- run([]string{"claude", "pre", "--hook", "command-guard"}, strings.NewReader(`{"tool_name":"Bash","tool_input":{"command":"ls"}}`),
					stdout, &stderr, &fake.Machine{}, sink, map[string]hook{"command-guard": decide}, 40*time.Millisecond)
			}()
			select {
			case <-stdout.written:
			case <-time.After(time.Second):
				close(release)
				<-done
				t.Fatal("no supervised answer")
			}
			close(release)
			if exit := <-done; exit != 2 {
				t.Errorf("exit %d, want block", exit)
			}
			if len(stdout.written) != 0 {
				t.Error("more than one answer")
			}
			if strings.Contains(stderr.String(), "worker diagnostic") == late {
				t.Errorf("late=%v diagnostics: %q", late, stderr.String())
			}
			line, err := logline.Parse(sink.Lines()[0].Line)
			if err != nil || (late && (line.Error != "hook.timeout" || line.Tool != "other" || line.Kind != "none")) || (!late && line.Error != "hook.failed") {
				t.Errorf("late=%v line %+v, %v", late, line, err)
			}
		})
	}
}

func TestStageGivesEveryCommandTheSameAbsoluteDeadline(t *testing.T) {
	command := process.Command{Path: "/fake/rtk", Args: []string{"rtk"}, Timeout: time.Second}
	machine := &fake.Machine{Replay: []fake.Invocation{{Command: command}, {Command: command}}}
	decide := func(_ ir.Call, m Machine) ir.Outcome {
		_, _ = m.Run(command)
		command.Deadline = time.Now().Add(time.Hour)
		_, _ = m.Run(command)
		return ir.Outcome{}
	}
	var stdout, stderr bytes.Buffer
	start := time.Now()
	exit := run([]string{"claude", "pre", "--hook", "rtk"}, strings.NewReader(`{}`), &stdout, &stderr,
		machine, &fake.LogSink{}, map[string]hook{"rtk": decide})
	if exit != 0 || len(machine.Done()) != 0 {
		t.Fatalf("run failed: exit %d, replay %v", exit, machine.Done())
	}
	if len(machine.Deadlines) != 2 || !machine.Deadlines[0].Equal(machine.Deadlines[1]) || machine.Deadlines[0].Before(start.Add(10*time.Second)) || machine.Deadlines[0].After(time.Now().Add(10*time.Second)) {
		t.Errorf("command deadlines %v, want the same stage deadline", machine.Deadlines)
	}
}

func TestStageReturnsAfterItsBoundedCleanupWait(t *testing.T) {
	t.Parallel()
	stdin, input := io.Pipe()
	defer stdin.Close()
	defer input.Close()
	var stdout, stderr bytes.Buffer
	start := time.Now()
	exit := run([]string{"claude", "pre", "--hook", "rtk"}, stdin, &stdout, &stderr,
		&fake.Machine{}, &fake.LogSink{}, hooks, 40*time.Millisecond)
	if elapsed := time.Since(start); exit != 0 || elapsed < 2500*time.Millisecond || elapsed > 2900*time.Millisecond {
		t.Errorf("exit %d after %s, want a pass after the 2.5 s cleanup wait", exit, elapsed)
	}
}

func TestManifestRejectsMissingOrNonpositiveOrFractionalDeadlines(t *testing.T) {
	for _, field := range []string{"", `,"deadlineSeconds":0`, `,"deadlineSeconds":-1`, `,"deadlineSeconds":0.5`} {
		encoded := []byte(fmt.Sprintf(`{"hooks":[{"id":"rtk","event":"pre","failure":"open"%s}]}`, field))
		if _, err := decodeManifest(encoded); err == nil {
			t.Errorf("manifest accepted %s", encoded)
		}
	}
}

func TestManifestPinsEveryStageDeadline(t *testing.T) {
	var file struct {
		Hooks []struct {
			ID              string `json:"id"`
			DeadlineSeconds int    `json:"deadlineSeconds"`
		} `json:"hooks"`
	}
	if err := json.Unmarshal(agenthooks.Manifest, &file); err != nil {
		t.Fatal(err)
	}
	want := map[string]int{"command-guard": 10, "files-guard": 10, "secrets-guard": 10, "rtk": 10, "formatter": 20}
	if len(file.Hooks) != len(want) {
		t.Fatalf("%d hooks, want %d", len(file.Hooks), len(want))
	}
	for _, spec := range file.Hooks {
		if spec.DeadlineSeconds != want[spec.ID] || want[spec.ID] == 0 {
			t.Errorf("%s deadline = %d seconds, want %d", spec.ID, spec.DeadlineSeconds, want[spec.ID])
		}
	}
}
