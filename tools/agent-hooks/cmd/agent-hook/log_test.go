package main_test

import (
	"bytes"
	"errors"
	"maps"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"

	json "github.com/goccy/go-json/v2"

	"github.com/hironow/dotfiles/tools/agent-hooks/harnesses"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/logline"
)

// runIn runs the built binary with its state directory (XDG_STATE_HOME) set
// to state, or with neither XDG_STATE_HOME nor HOME when state is "".
func runIn(t *testing.T, state string, stdin []byte, args ...string) (int, string, string) {
	t.Helper()
	return runBinaryIn(t, binary, state, stdin, args...)
}

// runBinaryIn is runIn for another build of the binary, at bin.
func runBinaryIn(t *testing.T, bin, state string, stdin []byte, args ...string) (int, string, string) {
	t.Helper()
	// Audited: bin is an agent-hook this test package built into its own
	// temporary directory, and args are literals.
	// nosemgrep: go.lang.security.audit.dangerous-exec-command.dangerous-exec-command
	command := exec.Command(bin, args...)
	command.Dir = t.TempDir()
	command.Env = []string{"PATH=" + os.Getenv("PATH")}
	if state != "" {
		command.Env = append(command.Env, "XDG_STATE_HOME="+state, "HOME="+t.TempDir())
	}
	command.Stdin = bytes.NewReader(stdin)
	var stdout, stderr bytes.Buffer
	command.Stdout, command.Stderr = &stdout, &stderr
	exit := 0
	if err := command.Run(); err != nil {
		var exitErr *exec.ExitError
		if !errors.As(err, &exitErr) {
			t.Fatalf("run %v: %v", args, err)
		}
		exit = exitErr.ExitCode()
	}
	return exit, stdout.String(), stderr.String()
}

func skipOnWindows(t *testing.T) {
	t.Helper()
	if runtime.GOOS == "windows" {
		t.Skip("there is no file log on Windows yet")
	}
}

func TestEachRunLogsOneLineInTheStateDirectory(t *testing.T) {
	skipOnWindows(t)
	state := t.TempDir()
	payload, err := harnesses.FS.ReadFile("claude/fixtures/pre-bash.json")
	if err != nil {
		t.Fatal(err)
	}
	// given a state directory, when the binary answers a hook
	exit, stdout, _ := runIn(t, state, payload, "claude", "pre", "--hook", "command-guard")
	if exit != 0 || stdout != "" {
		t.Fatalf("exit %d, stdout %q; want the pass", exit, stdout)
	}
	// then its line is in today's file there, private to the user
	day := filepath.Join(state, "dotfiles", "agent-hooks", "logs", time.Now().UTC().Format("2006-01-02")+".jsonl")
	data, err := os.ReadFile(day)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Count(string(data), "\n") != 1 {
		t.Fatalf("the day's file holds %q; want one line", data)
	}
	line, err := logline.Parse(data)
	if err != nil {
		t.Fatal(err)
	}
	if line.Harness != "claude" || line.Hook != "command-guard" || line.Outcome != "pass" || len(line.Project) != 16 {
		t.Errorf("line %+v; want claude's command guard passing, with the project hashed", line)
	}
	for _, path := range []string{day, filepath.Join(state, "dotfiles", "agent-hooks", "salt")} {
		info, err := os.Stat(path)
		if err != nil {
			t.Fatal(err)
		}
		if info.Mode().Perm() != 0o600 {
			t.Errorf("%s has mode %v, want 0600", path, info.Mode().Perm())
		}
	}
	// and `agent-hook log` prints it
	exit, stdout, stderr := runIn(t, state, nil, "log")
	if exit != 0 || !strings.Contains(stdout, "HARNESS") || !strings.Contains(stdout, "command-guard") {
		t.Errorf("agent-hook log: exit %d, stdout %q, stderr %q; want the table with the line", exit, stdout, stderr)
	}
}

func TestAgentHookLogSummaryCountsTheDaysLines(t *testing.T) {
	skipOnWindows(t)
	state := t.TempDir()
	payload, err := harnesses.FS.ReadFile("claude/fixtures/pre-bash.json")
	if err != nil {
		t.Fatal(err)
	}
	// given a day's log with one real line
	if exit, _, _ := runIn(t, state, payload, "claude", "pre", "--hook", "command-guard"); exit != 0 {
		t.Fatalf("hook run exit %d", exit)
	}
	day := filepath.Join(state, "dotfiles", "agent-hooks", "logs", time.Now().UTC().Format("2006-01-02")+".jsonl")
	real, err := os.ReadFile(day)
	if err != nil {
		t.Fatal(err)
	}
	// and lines a reader cannot trust: a timeout, values outside the fixed
	// sets, and a line that is no JSON object
	var fields map[string]any
	if err := json.Unmarshal(real, &fields); err != nil {
		t.Fatal(err)
	}
	var crafted []byte
	for _, set := range []map[string]any{
		{"error": "hook.timeout"},
		{"error": "weird.code", "mismatch": "odd\x01"},
	} {
		line := maps.Clone(fields)
		maps.Copy(line, set)
		encoded, err := json.Marshal(line)
		if err != nil {
			t.Fatal(err)
		}
		crafted = append(append(crafted, encoded...), '\n')
	}
	crafted = append(crafted, "not a line\n"...)
	file, err := os.OpenFile(day, os.O_APPEND|os.O_WRONLY, 0)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := file.Write(crafted); err != nil {
		t.Fatal(err)
	}
	if err := file.Close(); err != nil {
		t.Fatal(err)
	}
	// when the summary is asked for
	exit, stdout, stderr := runIn(t, state, nil, "log", "--summary")
	// then it counts the readable lines, and names only codes it knows
	want := `{"days":1,"lines":3,"unreadable":1,"errors":{"hook.timeout":1,"other":1},"mismatches":{"other":1}}` + "\n"
	if exit != 0 || stdout != want || stderr != "" {
		t.Fatalf("exit %d, stdout %q, stderr %q; want %q", exit, stdout, stderr, want)
	}
}

func TestAgentHookLogSummaryOfNoLogMakesNothing(t *testing.T) {
	skipOnWindows(t)
	state := t.TempDir()
	// given no log yet, when the summary is asked for
	exit, stdout, stderr := runIn(t, state, nil, "log", "--summary", "--days", "2")
	// then it gives zero counts, and makes no directory
	want := `{"days":2,"lines":0,"unreadable":0,"errors":{},"mismatches":{}}` + "\n"
	if exit != 0 || stdout != want || stderr != "" {
		t.Fatalf("exit %d, stdout %q, stderr %q; want %q", exit, stdout, stderr, want)
	}
	if entries, err := os.ReadDir(state); err != nil || len(entries) != 0 {
		t.Errorf("the state directory holds %v (%v); want it left empty", entries, err)
	}
}

func TestAgentHookLogRefusesArgumentsItDoesNotKnow(t *testing.T) {
	state := t.TempDir()
	for _, args := range [][]string{{"log", "--days", "0"}, {"log", "extra"}, {"log", "--weeks", "1"}, {"log", "--summary", "extra"}} {
		exit, stdout, stderr := runIn(t, state, nil, args...)
		if exit != 64 || stdout != "" || !strings.Contains(stderr, "usage: agent-hook log") {
			t.Errorf("agent-hook %q: exit %d, stdout %q, stderr %q; want exit 64 and the usage", args, exit, stdout, stderr)
		}
	}
}

func TestAgentHookLogMakesNothingWhenThereIsNoLog(t *testing.T) {
	skipOnWindows(t)
	state := t.TempDir()
	// given a state directory no run has logged to, when the log is asked for
	exit, stdout, stderr := runIn(t, state, nil, "log")
	// then it says there is none, and makes no directory
	if exit != 0 || !strings.Contains(stdout, "No log yet") || stderr != "" {
		t.Errorf("exit %d, stdout %q, stderr %q; want exit 0 and that there is no log", exit, stdout, stderr)
	}
	if entries, err := os.ReadDir(state); err != nil || len(entries) != 0 {
		t.Errorf("the state directory holds %v (%v); want it left empty", entries, err)
	}
}

func TestAgentHookLogNeedsAStateDirectory(t *testing.T) {
	skipOnWindows(t)
	// given neither XDG_STATE_HOME nor HOME, when the log is asked for
	exit, stdout, stderr := runIn(t, "", nil, "log")
	// then it says why there is none
	if exit != 1 || stdout != "" || !strings.Contains(stderr, "no state directory") {
		t.Errorf("exit %d, stdout %q, stderr %q; want exit 1 and why", exit, stdout, stderr)
	}
}
