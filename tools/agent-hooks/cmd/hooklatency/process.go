package main

import (
	"bytes"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

type answer struct {
	exit           int
	stdout, stderr string
}

// commandRunner runs a harness command and returns its answer and wall time.
type commandRunner interface {
	Run(command string, payload []byte) (answer, time.Duration, error)
}

type shellRunner struct {
	project string
	env     []string
}

func (s shellRunner) Run(command string, payload []byte) (answer, time.Duration, error) {
	// Audited: the operator selects the hooks and binary to measure. Case
	// fixes the script, arguments, harness, event, and hook. It quotes every
	// path for /bin/sh; payloads go only to stdin. The brief requires -c.
	// nosemgrep: dangerous-exec-command, go.lang.security.audit.dangerous-exec-command.dangerous-exec-command
	cmd := exec.Command("/bin/sh", "-c", command) //nolint:gosec // G204: audited above
	cmd.Dir, cmd.Env, cmd.Stdin = s.project, s.env, bytes.NewReader(payload)
	var stdout, stderr bytes.Buffer
	cmd.Stdout, cmd.Stderr = &stdout, &stderr
	start := time.Now()
	if err := cmd.Start(); err != nil {
		return answer{}, 0, err
	}
	err := cmd.Wait()
	elapsed := time.Since(start)
	result := answer{stdout: stdout.String(), stderr: stderr.String()}
	var exit *exec.ExitError
	if err != nil && !errors.As(err, &exit) {
		return answer{}, 0, err
	}
	if exit != nil {
		result.exit = exit.ExitCode()
	}
	if result.exit == 126 || result.exit == 127 || result.exit < 0 {
		return answer{}, 0, fmt.Errorf("command could not run: exit %d, stderr %q", result.exit, result.stderr)
	}
	return result, elapsed, nil
}

func environmentWith(env []string, key, value string) []string {
	replaced := make([]string, 0, len(env)+1)
	for _, entry := range env {
		if !strings.HasPrefix(entry, key+"=") {
			replaced = append(replaced, entry)
		}
	}
	return append(replaced, key+"="+value)
}

func buildBinary(path string, env []string) error {
	// Audited: the program builds its sibling command with fixed release
	// flags. The sole variable argument is an output path in its temp dir.
	// nosemgrep: go.lang.security.audit.dangerous-exec-command.dangerous-exec-command
	cmd := exec.Command("go", "build", "-trimpath", "-ldflags=-s -w", "-o", path, "./cmd/agent-hook") //nolint:gosec // G204: audited above
	cmd.Env = environmentWith(env, "CGO_ENABLED", "0")
	if output, err := cmd.CombinedOutput(); err != nil {
		return fmt.Errorf("build agent-hook: %w\n%s", err, output)
	}
	return nil
}

func projectDirectory(project string) (string, error) {
	if project == "" {
		cmd := exec.Command("git", "rev-parse", "--show-toplevel")
		output, err := cmd.CombinedOutput()
		if err != nil {
			return "", fmt.Errorf("find project: %w\n%s", err, output)
		}
		project = strings.TrimSpace(string(output))
	}
	path, err := filepath.Abs(project)
	if err != nil {
		return "", err
	}
	stat, err := os.Stat(path)
	if err != nil {
		return "", err
	}
	if !stat.IsDir() {
		return "", fmt.Errorf("project is not a directory: %s", path)
	}
	return path, nil
}
