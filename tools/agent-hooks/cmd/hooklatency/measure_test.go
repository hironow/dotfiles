package main

import (
	"errors"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"testing"
	"time"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/latency"
)

// recordingCommands simulates formatting and logging, with fixed wall times.
type recordingCommands struct {
	state, file string
	order       []bool
	logLines    int
	driftAt     int
	fail        bool
}

func (r *recordingCommands) Run(command string, _ []byte) (answer, time.Duration, error) {
	binary := strings.HasPrefix(command, `"binary"`)
	r.order = append(r.order, binary)
	if r.fail {
		return answer{}, 0, errors.New("cannot start")
	}
	if r.file != "" {
		content, err := os.ReadFile(r.file)
		if err != nil {
			return answer{}, 0, err
		}
		if string(content) != "hello\n" {
			return answer{}, 0, errors.New("formatter file was not reset")
		}
		if err := os.WriteFile(r.file, []byte("formatted\n"), 0o600); err != nil {
			return answer{}, 0, err
		}
	}
	if binary {
		dir := filepath.Join(r.state, "dotfiles", "agent-hooks", "logs")
		if err := os.MkdirAll(dir, 0o700); err != nil {
			return answer{}, 0, err
		}
		path := filepath.Join(dir, "2026-11-05.jsonl")
		previous, _ := os.ReadFile(path)
		if err := os.WriteFile(path, append(previous, strings.Repeat("{}\n", r.logLines)...), 0o600); err != nil {
			return answer{}, 0, err
		}
	}
	result := answer{exit: 2, stdout: "stdout\n", stderr: "stderr\n"}
	if len(r.order) == r.driftAt {
		result.stderr = "changed stderr\n"
	}
	elapsed := time.Millisecond
	if binary {
		elapsed = 2 * time.Millisecond
	}
	return result, elapsed, nil
}

func trial(t *testing.T) (measurement, *recordingCommands) {
	t.Helper()
	dir := t.TempDir()
	runner := &recordingCommands{state: dir, logLines: 1}
	return measurement{config: options{runs: 3, binary: "binary", project: dir}, runner: runner, files: dir, state: dir}, runner
}

func TestRoundsAlternateAndResetBothFormatterSides(t *testing.T) {
	m, runner := trial(t)
	cases := []latency.Case{{
		Name: "claude/post/formatter/md", Harness: "claude", Event: "post", Hook: "formatter",
		Script: "format-after-edit.sh", FileName: "notes.md", Content: "hello\n", Reset: true,
	}}
	runner.file = filepath.Join(m.files, "notes.md")
	rows, err := m.run(cases)
	if err != nil {
		t.Fatal(err)
	}
	if want := []bool{false, true, true, false, false, true, true, false}; !slices.Equal(runner.order, want) {
		t.Errorf("binary order = %v, want %v (warm-up, then 3 alternating rounds)", runner.order, want)
	}
	if len(rows) != 1 || !slices.Equal(rows[0].Old, []time.Duration{time.Millisecond, time.Millisecond, time.Millisecond}) ||
		!slices.Equal(rows[0].Binary, []time.Duration{2 * time.Millisecond, 2 * time.Millisecond, 2 * time.Millisecond}) {
		t.Errorf("timed samples must exclude warm-ups: %+v", rows)
	}
}

func TestMeasurementRejectsMissingExtraLogsAndChangingAnswers(t *testing.T) {
	for _, test := range []struct {
		name     string
		logLines int
		driftAt  int
		fail     bool
		want     string
	}{
		{"missing log", 0, 0, false, "log grew by 0"},
		{"extra log", 2, 0, false, "log grew by 2"},
		{"binary drift", 1, 3, false, "changed stderr"},
		{"old drift", 1, 4, false, "changed stderr"},
		{"cannot start", 1, 0, true, "cannot start"},
	} {
		t.Run(test.name, func(t *testing.T) {
			m, runner := trial(t)
			runner.logLines, runner.driftAt, runner.fail = test.logLines, test.driftAt, test.fail
			_, err := m.run(latency.Cases()[:1])
			if err == nil || !strings.Contains(err.Error(), "claude/pre/command-guard/pass") || !strings.Contains(err.Error(), test.want) {
				t.Errorf("error = %v, want case name and %q", err, test.want)
			}
		})
	}
}

func TestSameAnswerReadsStdoutAsAHarnessReadsIt(t *testing.T) {
	spaced := `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "updatedInput": {"command": "rtk git status"}}}` + "\n"
	compact := `{"hookSpecificOutput":{"hookEventName":"PreToolUse","updatedInput":{"command":"rtk git status"}}}` + "\n"
	cases := []struct {
		name string
		a, b answer
		want bool
	}{
		// Python's json.dumps spaces its separators; the binary does not.
		{"the same JSON, spaced and compact", answer{stdout: spaced}, answer{stdout: compact}, true},
		{"another JSON value", answer{stdout: spaced}, answer{stdout: strings.Replace(compact, "rtk git", "git", 1)}, false},
		{"the same text", answer{exit: 2, stderr: "blocked\n"}, answer{exit: 2, stderr: "blocked\n"}, true},
		{"another exit code", answer{exit: 2}, answer{exit: 0}, false},
		{"another stderr", answer{stderr: "a"}, answer{stderr: "b"}, false},
		{"stdout that is not JSON", answer{stdout: "x \n"}, answer{stdout: "x\n"}, false},
	}
	for _, c := range cases {
		if got := sameAnswer(c.a, c.b); got != c.want {
			t.Errorf("%s: sameAnswer = %v, want %v", c.name, got, c.want)
		}
	}
}
