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

// fakeBasename holds, per flavor, a directory with a basename(1) that answers
// `--version` as that flavor does: GNU's succeeds, BSD's fails. Put first on
// PATH, it checks the binary's real probe and how its answer reaches the guard.
var fakeBasename = map[string]string{}

var fakeBasenameScripts = map[string]string{
	"gnu": "#!/bin/sh\n[ \"$1\" = --version ] && exit 0\nexit 1\n",
	"bsd": "#!/bin/sh\nexit 1\n",
}

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
	for flavor, script := range fakeBasenameScripts {
		fakeBasename[flavor] = filepath.Join(dir, flavor)
		if err := os.Mkdir(fakeBasename[flavor], 0o700); err != nil {
			fmt.Fprintln(os.Stderr, err)
			return 1
		}
		if err := os.WriteFile(filepath.Join(fakeBasename[flavor], "basename"), []byte(script), 0o700); err != nil {
			fmt.Fprintln(os.Stderr, err)
			return 1
		}
	}
	return m.Run()
}

// runBinary runs the built binary in an empty directory (it needs no
// checkout), with the flavor's fake basename(1) first on PATH.
func runBinary(t *testing.T, flavor string, stdin []byte, args ...string) guardcorpus.Answer {
	t.Helper()
	if flavor == "" {
		flavor = "bsd" // the hook does not ask
	}
	// Audited: binary is the agent-hook this test built into its own temporary
	// directory, and args are the corpus's harness and hook names or literals.
	// nosemgrep: go.lang.security.audit.dangerous-exec-command.dangerous-exec-command
	command := exec.Command(binary, args...)
	command.Dir = t.TempDir()
	command.Env = append(os.Environ(), "PATH="+fakeBasename[flavor]+string(os.PathListSeparator)+os.Getenv("PATH"))
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
		t.Skip("the fake basename(1) programs are POSIX shell scripts")
	}
}

func TestTheBinaryAnswersAsThePayloadCorpusExpects(t *testing.T) {
	skipWithoutPOSIXShell(t)
	payloads := guardcorpus.Payloads(t)
	if len(payloads) < 250 {
		t.Fatalf("payloads.jsonl has %d payloads; expected the whole corpus", len(payloads))
	}
	for _, payload := range payloads {
		t.Run(payload.Name, func(t *testing.T) {
			t.Parallel()
			for _, run := range payload.Runs {
				got := runBinary(t, run.Basename, payload.Stdin, run.Harness, "pre", "--hook", run.Hook)
				if got != run.ExpectedGo {
					t.Errorf("payloads.jsonl:%d, %s %s %s (difference %q):\n got %+v\nwant %+v",
						payload.Line, run.Harness, run.Hook, run.Basename, run.Difference, got, run.ExpectedGo)
				}
			}
		})
	}
}

func TestTheBinaryRejectsAnArgumentItDoesNotKnow(t *testing.T) {
	skipWithoutPOSIXShell(t)
	for _, args := range [][]string{
		{"claude", "pre", "--hook", "no-such-hook"},
		{"no-such-harness", "pre", "--hook", "files-guard"},
		{"claude", "pre"},
	} {
		got := runBinary(t, "", []byte(`{"tool_input":{"file_path":"a.yml"}}`), args...)
		if got.Exit != 64 || got.Stdout != "" || !strings.Contains(got.Stderr, "usage: agent-hook") {
			t.Errorf("agent-hook %q = %+v, want exit 64 and the usage", args, got)
		}
	}
}
