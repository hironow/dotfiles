package main_test

import (
	"bytes"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/guardcorpus"
)

// binary is agent-hook as `go build` makes it, built once for these tests.
var binary string

// faketool stands in for rtk, mise, uv, and gofmt (not on Windows).
var faketool string

func TestMain(m *testing.M) {
	os.Exit(buildAndRun(m))
}

func buildAndRun(m *testing.M) int {
	dir, err := os.MkdirTemp("", "agent-hook-test-")
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	defer os.RemoveAll(dir)
	binary = filepath.Join(dir, "agent-hook")
	build := exec.Command("go", "build", "-o", binary, ".")
	build.Stdout, build.Stderr = os.Stderr, os.Stderr
	if err := build.Run(); err != nil {
		fmt.Fprintln(os.Stderr, "go build:", err)
		return 1
	}
	if runtime.GOOS != "windows" {
		faketool = filepath.Join(dir, "faketool")
		build := exec.Command("go", "build", "-o", faketool, "../../internal/toolhookcorpus/faketool")
		build.Stdout, build.Stderr = os.Stderr, os.Stderr
		if err := build.Run(); err != nil {
			fmt.Fprintln(os.Stderr, "go build faketool:", err)
			return 1
		}
	}
	return m.Run()
}

// runBinary runs the built binary in an empty directory: it needs no
// checkout, and it runs no program for the guards (the old files guard ran
// basename(1); the binary takes base names itself: fixed-dash-line).
func runBinary(t *testing.T, stdin []byte, args ...string) guardcorpus.Answer {
	t.Helper()
	// Audited: binary is the agent-hook this test built into its own temporary
	// directory, and args are the corpus's harness and hook names or literals.
	// nosemgrep: go.lang.security.audit.dangerous-exec-command.dangerous-exec-command
	command := exec.Command(binary, args...)
	command.Dir = t.TempDir()
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
	return guardcorpus.Answer{Exit: exit, Stdout: stdout.String(), Stderr: stderr.String()}
}

func skipWithoutPOSIXShell(t *testing.T) {
	t.Helper()
	if runtime.GOOS == "windows" {
		t.Skip("the fake programs are POSIX shell scripts")
	}
}

func TestTheBinaryAnswersAsThePayloadCorpusExpects(t *testing.T) {
	payloads := guardcorpus.Payloads(t)
	if len(payloads) < 250 {
		t.Fatalf("payloads.jsonl has %d payloads; expected the whole corpus", len(payloads))
	}
	for _, payload := range payloads {
		for _, run := range payload.Runs {
			// The frame says whether the binary answers as the script did
			// ("parity") or differs on purpose, and why (the difference IDs).
			name := guardcorpus.Frame(run.Difference) + "/" + payload.Name + "/" + run.Harness + "/" + run.Hook + "/" + run.Basename
			t.Run(name, func(t *testing.T) {
				t.Parallel()
				got := runBinary(t, payload.Stdin, run.Harness, "pre", "--hook", run.Hook)
				if got != run.ExpectedGo {
					t.Errorf("payloads.jsonl:%d (difference %q):\n got %+v\nwant %+v",
						payload.Line, run.Difference, got, run.ExpectedGo)
				}
			})
		}
	}
}

func TestTheBinaryRejectsAnArgumentItDoesNotKnow(t *testing.T) {
	for _, args := range [][]string{
		{"claude", "pre", "--hook", "no-such-hook"},
		{"no-such-harness", "pre", "--hook", "files-guard"},
		{"claude", "pre"},
	} {
		got := runBinary(t, []byte(`{"tool_input":{"file_path":"a.yml"}}`), args...)
		if got.Exit != 64 || got.Stdout != "" || !strings.Contains(got.Stderr, "usage: agent-hook") {
			t.Errorf("agent-hook %q = %+v, want exit 64 and the usage", args, got)
		}
	}
}
