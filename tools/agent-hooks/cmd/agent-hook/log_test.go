package main_test

import (
	"bytes"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"

	"github.com/hironow/dotfiles/tools/agent-hooks/harnesses"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/logline"
)

// runIn runs the built binary with its state directory (XDG_STATE_HOME) set
// to state, or with neither XDG_STATE_HOME nor HOME when state is "".
func runIn(t *testing.T, state string, stdin []byte, args ...string) (int, string, string) {
	t.Helper()
	// Audited: binary is the agent-hook this test built into its own temporary
	// directory, and args are literals.
	// nosemgrep: go.lang.security.audit.dangerous-exec-command.dangerous-exec-command
	command := exec.Command(binary, args...)
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

func TestAgentHookLogRefusesArgumentsItDoesNotKnow(t *testing.T) {
	state := t.TempDir()
	for _, args := range [][]string{{"log", "--days", "0"}, {"log", "extra"}, {"log", "--weeks", "1"}} {
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
