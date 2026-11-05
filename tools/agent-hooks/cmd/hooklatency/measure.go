package main

import (
	"bytes"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/latency"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/toolhookcorpus"
)

func execute(config options, cases []latency.Case) ([]latency.Row, error) {
	project, err := projectDirectory(config.project)
	if err != nil {
		return nil, err
	}
	config.project = project
	root, err := os.MkdirTemp("", "hooklatency-")
	if err != nil {
		return nil, err
	}
	defer os.RemoveAll(root)
	files, state := filepath.Join(root, "files"), filepath.Join(root, "state")
	for _, path := range []string{files, state} {
		if err := os.Mkdir(path, 0o700); err != nil {
			return nil, err
		}
	}
	// Both sides share one state directory, one Python environment for the
	// formatter's `uv run`, and one ruff cache, all temporary: the binary's
	// file log, the project's .venv, and its .ruff_cache stay untouched. uv's
	// own cache is the user's, which uv only adds to: a temporary one would
	// need the network to install ruff again.
	env := os.Environ()
	for key, value := range map[string]string{
		"XDG_STATE_HOME":         state,
		"UV_PROJECT_ENVIRONMENT": filepath.Join(root, "venv"),
		"RUFF_CACHE_DIR":         filepath.Join(root, "ruff-cache"),
	} {
		env = environmentWith(env, key, value)
	}
	if config.binary == "" {
		config.binary = filepath.Join(root, "agent-hook")
		if err := buildBinary(config.binary, env); err != nil {
			return nil, err
		}
	}
	if err := absoluteCommands(&config); err != nil {
		return nil, err
	}
	m := measurement{config: config, runner: shellRunner{project: project, env: env}, files: files, state: state}
	return m.run(cases)
}

func absoluteCommands(config *options) error {
	for _, path := range []*string{&config.binary, &config.claudeHooks, &config.codexHooks} {
		absolute, err := filepath.Abs(*path)
		if err != nil {
			return err
		}
		*path = absolute
	}
	return nil
}

type measurement struct {
	config       options
	runner       commandRunner
	files, state string
}

type preparedCase struct {
	latency.Case
	payload  []byte
	expected answer
	// formatted is what today's formatter left in the case's file in its
	// warm-up: every later run of either side must leave the same.
	formatted string
	row       latency.Row
}

func (m measurement) warm(cases []latency.Case) ([]preparedCase, error) {
	var prepared []preparedCase
	for _, c := range cases {
		payload, err := c.Payload(m.config.project, m.files)
		if err != nil {
			return nil, fmt.Errorf("%s payload: %w", c.Name, err)
		}
		p := preparedCase{Case: c, payload: payload, row: latency.Row{Name: c.Name}}
		expected, after, _, err := m.sample(p, false)
		if err != nil {
			return nil, fmt.Errorf("%s warm-up old: %w", c.Name, err)
		}
		// The answer must show what the case is named for: a missing rtk or
		// gofmt passes on both sides, fast and alike, and would time nothing.
		if err := c.Shows(latency.Answer{Exit: expected.exit, Stdout: expected.stdout, Stderr: expected.stderr}); err != nil {
			return nil, fmt.Errorf("%s warm-up old: %w", c.Name, err)
		}
		if c.Changes && after == c.Content {
			return nil, fmt.Errorf("%s warm-up old: today's formatter left %s as it was: is its program on PATH?", c.Name, c.FileName)
		}
		p.expected, p.formatted = expected, after
		if _, err := m.checked(p, true); err != nil {
			return nil, fmt.Errorf("%s warm-up binary: %w", c.Name, err)
		}
		prepared = append(prepared, p)
	}
	return prepared, nil
}

func (m measurement) run(cases []latency.Case) ([]latency.Row, error) {
	prepared, err := m.warm(cases)
	if err != nil {
		return nil, err
	}
	for round := 1; round <= m.config.runs; round++ {
		for i := range prepared {
			p := &prepared[i]
			for _, binary := range []bool{round%2 == 1, round%2 != 1} {
				elapsed, err := m.checked(*p, binary)
				if err != nil {
					return nil, fmt.Errorf("%s round %d: %w", p.Name, round, err)
				}
				if binary {
					p.row.Binary = append(p.row.Binary, elapsed)
				} else {
					p.row.Old = append(p.row.Old, elapsed)
				}
			}
		}
	}
	rows := make([]latency.Row, 0, len(prepared))
	for _, p := range prepared {
		rows = append(rows, p.row)
	}
	return rows, nil
}

func (m measurement) checked(p preparedCase, binary bool) (time.Duration, error) {
	got, after, elapsed, err := m.sample(p, binary)
	if err != nil {
		return 0, err
	}
	if p.Reset && after != p.formatted {
		side := "today's script"
		if binary {
			side = "the binary"
		}
		return 0, fmt.Errorf("%s left %s as %q; today's formatter left %q", side, p.FileName, after, p.formatted)
	}
	if !sameAnswer(got, p.expected) {
		return 0, fmt.Errorf("answer mismatch (binary=%t):\n- old warm-up: exit=%d stdout=%q stderr=%q\n+ got: exit=%d stdout=%q stderr=%q",
			binary, p.expected.exit, p.expected.stdout, p.expected.stderr, got.exit, got.stdout, got.stderr)
	}
	return elapsed, nil
}

// sameAnswer reports whether two answers are the same as a harness reads
// them: the exit code and stderr byte for byte, and stdout byte for byte or,
// when both are JSON, as the same value (toolhookcorpus.SameJSON, as the
// parity corpora compare). Python's json.dumps spaces its separators, and the
// binary does not.
func sameAnswer(a, b answer) bool {
	if a.exit != b.exit || a.stderr != b.stderr {
		return false
	}
	if a.stdout == b.stdout {
		return true
	}
	same, err := toolhookcorpus.SameJSON([]byte(a.stdout), []byte(b.stdout))
	return err == nil && same
}

// sample runs one side once. For a formatter case it resets the file before
// and reads it after, both outside the timed span, and returns what the run
// left in it.
func (m measurement) sample(p preparedCase, binary bool) (answer, string, time.Duration, error) {
	file := filepath.Join(m.files, p.FileName)
	if p.Reset {
		if err := os.WriteFile(file, []byte(p.Content), 0o600); err != nil {
			return answer{}, "", 0, fmt.Errorf("reset formatter file: %w", err)
		}
	}
	command := p.OldCommand(m.config.claudeHooks, m.config.codexHooks)
	before := 0
	if binary {
		command = p.BinaryCommand(m.config.binary)
		var err error
		before, err = countLogLines(m.state)
		if err != nil {
			return answer{}, "", 0, err
		}
	}
	got, elapsed, err := m.runner.Run(command, p.payload)
	if err != nil {
		return answer{}, "", 0, fmt.Errorf("run %s: %w", command, err)
	}
	if binary {
		after, err := countLogLines(m.state)
		if err != nil {
			return answer{}, "", 0, err
		}
		if after-before != 1 {
			return answer{}, "", 0, fmt.Errorf("binary log grew by %d lines, want exactly 1", after-before)
		}
	}
	left := ""
	if p.Reset {
		content, err := os.ReadFile(file)
		if err != nil {
			return answer{}, "", 0, fmt.Errorf("read formatter file: %w", err)
		}
		left = string(content)
	}
	return got, left, elapsed, nil
}

func countLogLines(state string) (int, error) {
	paths, err := filepath.Glob(filepath.Join(state, "dotfiles", "agent-hooks", "logs", "*.jsonl"))
	if err != nil {
		return 0, err
	}
	count := 0
	for _, path := range paths {
		contents, err := os.ReadFile(path)
		if err != nil {
			return 0, fmt.Errorf("count log lines: %w", err)
		}
		count += bytes.Count(contents, []byte{'\n'})
	}
	return count, nil
}
