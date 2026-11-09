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

// executableName returns name with .exe on Windows. `go build -o` writes
// exactly the name it is given, and Windows runs a program only by its .exe.
func executableName(name string) string {
	if runtime.GOOS == "windows" {
		return name + ".exe"
	}
	return name
}

func buildAndRun(m *testing.M) int {
	dir, err := os.MkdirTemp("", "agent-hook-test-")
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	defer os.RemoveAll(dir)
	binary = filepath.Join(dir, executableName("agent-hook"))
	if under := os.Getenv("AGENT_HOOK_UNDER_TEST"); under != "" {
		// An installed release (just agent-hooks-test-installed): these tests
		// run against it, once it says it is the release they were told of.
		binary = under
		if err := checkReleaseUnderTest(binary, os.Getenv("AGENT_HOOK_EXPECT_RELEASE"), dir); err != nil {
			fmt.Fprintln(os.Stderr, err)
			return 1
		}
	} else {
		build := exec.Command("go", "build", "-o", binary, ".")
		build.Stdout, build.Stderr = os.Stderr, os.Stderr
		if err := build.Run(); err != nil {
			fmt.Fprintln(os.Stderr, "go build:", err)
			return 1
		}
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
	// Every run of the binary logs a line to the state directory. The runs
	// inherit this process's environment, so it is the tests' own: no test
	// writes to the user's file log. XDG_STATE_HOME is absolute, so HOME is
	// not used for it; LOCALAPPDATA is Windows' (no file log there yet). A
	// test that sets a run's environment itself sets HOME to its own root.
	state := filepath.Join(dir, "state")
	for _, name := range []string{"XDG_STATE_HOME", "LOCALAPPDATA"} {
		if err := os.Setenv(name, state); err != nil {
			fmt.Fprintln(os.Stderr, err)
			return 1
		}
	}
	return m.Run()
}

// checkReleaseUnderTest asks the binary its version, and wants want, the
// release ID AGENT_HOOK_EXPECT_RELEASE names, so a test run cannot pass for
// another binary than the one it was meant for.
func checkReleaseUnderTest(binary, want, dir string) error {
	if want == "" {
		return errors.New("AGENT_HOOK_UNDER_TEST needs AGENT_HOOK_EXPECT_RELEASE, its release ID")
	}
	// Audited: binary is the release the operator named for these tests.
	// nosemgrep: go.lang.security.audit.dangerous-exec-command.dangerous-exec-command
	version := exec.Command(binary, "version")
	version.Dir = dir
	version.Env = []string{"PATH=" + os.Getenv("PATH"), "XDG_STATE_HOME=" + filepath.Join(dir, "version-state")}
	out, err := version.Output()
	if err != nil {
		return fmt.Errorf("%s version: %w", binary, err)
	}
	fields := strings.Fields(string(out))
	if len(fields) < 2 || fields[0] != "agent-hook" {
		return fmt.Errorf("%s version printed %q, not agent-hook <release ID>", binary, out)
	}
	if fields[1] != want {
		return fmt.Errorf("%s is release %s, not %s", binary, fields[1], want)
	}
	return nil
}

// expectedRelease is the release ID of the binary under test: dev for the
// one these tests build, else AGENT_HOOK_EXPECT_RELEASE's.
func expectedRelease() string {
	if os.Getenv("AGENT_HOOK_UNDER_TEST") == "" {
		return "dev"
	}
	return os.Getenv("AGENT_HOOK_EXPECT_RELEASE")
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
