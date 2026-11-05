package main

import (
	"bytes"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func buildCommand(t *testing.T, target, output string) {
	t.Helper()
	cmd := exec.Command("go", "build", "-o", output, target)
	cmd.Dir = "../.."
	cmd.Env = append(os.Environ(), "CGO_ENABLED=0")
	if out, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("build %s: %v\n%s", target, err, out)
	}
}

func commandResult(t *testing.T, command string, args ...string) (int, string, string) {
	t.Helper()
	// Audited: command is the hooklatency binary this test built in its own
	// temporary directory. The test supplies every argument; no shell runs.
	// nosemgrep: dangerous-exec-command, go.lang.security.audit.dangerous-exec-command.dangerous-exec-command
	cmd := exec.Command(command, args...)
	cmd.Dir = "../.."
	var stdout, stderr bytes.Buffer
	cmd.Stdout, cmd.Stderr = &stdout, &stderr
	err := cmd.Run()
	var exit *exec.ExitError
	if err != nil && !errors.As(err, &exit) {
		t.Fatal(err)
	}
	code := 0
	if exit != nil {
		code = exit.ExitCode()
	}
	return code, stdout.String(), stderr.String()
}

func TestCLIWithRealProcesses(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("Windows has no file log yet")
	}
	root := t.TempDir()
	tool := filepath.Join(root, "hooklatency")
	buildCommand(t, "./cmd/hooklatency", tool)
	project := filepath.Join(root, "project with spaces")
	if err := os.Mkdir(project, 0o700); err != nil {
		t.Fatal(err)
	}
	hooks := filepath.Join(root, "hooks with spaces $cash `literal` \"quote\" \\backslash")
	if err := os.Mkdir(hooks, 0o700); err != nil {
		t.Fatal(err)
	}
	// The old side passes and records the log count it can see. In round 3
	// the binary runs first, so the final old run sees every binary line.
	script := `#!/bin/sh
cat >/dev/null
count=0
for log in "$XDG_STATE_HOME"/dotfiles/agent-hooks/logs/*.jsonl; do
    [ -f "$log" ] || continue
    while IFS= read -r line; do count=$((count + 1)); done < "$log"
done
printf '%s\n' "$count" > log-count
printf '%s\n' "$XDG_STATE_HOME" > measured-state
printf '%s\n' "$UV_PROJECT_ENVIRONMENT" > measured-venv
printf '%s\n' "$RUFF_CACHE_DIR" > measured-ruff-cache
`
	for _, name := range []string{"block-prohibited-commands.sh", "guard-codex.sh"} {
		if err := os.WriteFile(filepath.Join(hooks, name), []byte(script), 0o600); err != nil {
			t.Fatal(err)
		}
	}
	// A preexisting value must be replaced, without writing there.
	untouched := filepath.Join(root, "user-state")
	t.Setenv("XDG_STATE_HOME", untouched)
	args := []string{
		"--runs", "3", "--project", project, "--claude-hooks", hooks, "--codex-hooks", hooks,
		"--only", `^(claude|codex)/pre/command-guard/pass$`, "--budget", "1h",
	}
	exit, stdout, stderr := commandResult(t, tool, args...)
	if exit != 0 {
		t.Fatalf("exit %d, want 0\nstdout: %s\nstderr: %s", exit, stdout, stderr)
	}
	for _, harness := range []string{"claude", "codex"} {
		name := harness + "/pre/command-guard/pass"
		if strings.Count(stdout, name) != 1 {
			t.Errorf("want one row for %s: %s", name, stdout)
		}
	}
	if !strings.Contains(stdout, "N=3") {
		t.Errorf("missing run count: %s", stdout)
	}
	count, err := os.ReadFile(filepath.Join(project, "log-count"))
	if err != nil || string(count) != "8\n" {
		t.Fatalf("log count = %q (%v), want 2 cases * (3 rounds + 1 warm-up) = 8", count, err)
	}
	state, err := os.ReadFile(filepath.Join(project, "measured-state"))
	if err != nil {
		t.Fatal(err)
	}
	for _, path := range []string{untouched, strings.TrimSpace(string(state))} {
		if _, err := os.Stat(path); !errors.Is(err, os.ErrNotExist) {
			t.Errorf("state must be untouched or cleaned up: %s (%v)", path, err)
		}
	}
	// The formatter's uv environment and ruff cache are the measurement's
	// own too, next to its state, so the project's .venv and .ruff_cache
	// stay as they are.
	for _, name := range []string{"measured-venv", "measured-ruff-cache"} {
		measured, err := os.ReadFile(filepath.Join(project, name))
		if err != nil {
			t.Fatal(err)
		}
		path := strings.TrimSpace(string(measured))
		if path == "" || filepath.Dir(path) != filepath.Dir(strings.TrimSpace(string(state))) {
			t.Errorf("%s = %q; want a path in the measurement's own directory", name, path)
		}
		if _, err := os.Stat(path); !errors.Is(err, os.ErrNotExist) {
			t.Errorf("%s must be cleaned up: %s (%v)", name, path, err)
		}
	}

	// The supplied binary path also works, and a different old answer fails.
	binary := filepath.Join(root, "agent hook")
	buildCommand(t, "./cmd/agent-hook", binary)
	if err := os.WriteFile(filepath.Join(hooks, "block-prohibited-commands.sh"), []byte("#!/bin/sh\nprintf 'different answer'\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	exit, _, stderr = commandResult(t, tool, append(args, "--binary", binary)...)
	if exit != 2 || !strings.Contains(stderr, "claude/pre/command-guard/pass") || !strings.Contains(stderr, "different answer") {
		t.Errorf("wrong answer: exit %d, stderr %q; want 2 and the case's answer diff", exit, stderr)
	}
}

func TestBadFlagsFailMeasurement(t *testing.T) {
	for _, args := range [][]string{
		{"--runs", "0"},
		{"--runs", "-1"},
		{"--runs", "no"},
		{"--only", "["},
		{"--budget", "-1ns"},
		{"--budget", "no"},
		{"--unknown"},
		{"extra"},
		{"--only", "^no-case$"},
	} {
		t.Run(strings.Join(args, " "), func(t *testing.T) {
			var stdout, stderr bytes.Buffer
			if exit := run(args, &stdout, &stderr); exit != 2 || stderr.Len() == 0 {
				t.Errorf("exit %d, stderr %q; want 2 and an explanation", exit, stderr.String())
			}
		})
	}
}
