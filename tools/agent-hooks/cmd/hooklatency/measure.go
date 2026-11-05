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
	env := environmentWith(os.Environ(), "XDG_STATE_HOME", state)
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
	row      latency.Row
}

func (m measurement) warm(cases []latency.Case) ([]preparedCase, error) {
	var prepared []preparedCase
	for _, c := range cases {
		payload, err := c.Payload(m.config.project, m.files)
		if err != nil {
			return nil, fmt.Errorf("%s payload: %w", c.Name, err)
		}
		p := preparedCase{Case: c, payload: payload, row: latency.Row{Name: c.Name}}
		expected, _, err := m.sample(p, false)
		if err != nil {
			return nil, fmt.Errorf("%s warm-up old: %w", c.Name, err)
		}
		p.expected = expected
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
	got, elapsed, err := m.sample(p, binary)
	if err != nil {
		return 0, err
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

func (m measurement) sample(p preparedCase, binary bool) (answer, time.Duration, error) {
	if p.Reset {
		if err := os.WriteFile(filepath.Join(m.files, p.FileName), []byte(p.Content), 0o600); err != nil {
			return answer{}, 0, fmt.Errorf("reset formatter file: %w", err)
		}
	}
	command := p.OldCommand(m.config.claudeHooks, m.config.codexHooks)
	before := 0
	if binary {
		command = p.BinaryCommand(m.config.binary)
		var err error
		before, err = countLogLines(m.state)
		if err != nil {
			return answer{}, 0, err
		}
	}
	got, elapsed, err := m.runner.Run(command, p.payload)
	if err != nil {
		return answer{}, 0, fmt.Errorf("run %s: %w", command, err)
	}
	if binary {
		after, err := countLogLines(m.state)
		if err != nil {
			return answer{}, 0, err
		}
		if after-before != 1 {
			return answer{}, 0, fmt.Errorf("binary log grew by %d lines, want exactly 1", after-before)
		}
	}
	return got, elapsed, nil
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
