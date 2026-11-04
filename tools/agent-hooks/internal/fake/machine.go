// Package fake holds working in-memory stand-ins for the ports the binary's
// shell reaches the outside through. Tests use them; nothing here touches the
// machine.
package fake

import (
	"bytes"
	"fmt"
	"slices"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/fileguard"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/process"
)

// Machine is a launch.Machine whose machine is a set of fields. It answers
// Run by replaying recorded invocations, in order, and records any call that
// does not match the next one in Mismatches; a test fails on any mismatch or
// on an invocation left over.
type Machine struct {
	// Flavor is the basename(1) flavor Basename returns; Probes counts the
	// calls, so a test can check that the shell asks only when a path needs
	// the answer.
	Flavor fileguard.Basename
	Probes int

	// Programs are the programs found on PATH, by name. A name not here is
	// not found.
	Programs map[string]process.Program
	// Executable holds the paths access(2) accepts with X_OK.
	Executable map[string]bool
	// Files holds the paths that are regular files.
	Files map[string]bool
	// Cwd is the physical working directory.
	Cwd string
	// Unstartable holds paths that are no executable file: Run fails on one
	// at once, as exec would, without taking a replayed invocation.
	Unstartable map[string]bool
	// Windows makes the machine a Windows one, for its path rules.
	Windows bool
	// RealPaths maps a path to its real path (symlinks followed); a path not
	// here does not resolve.
	RealPaths map[string]string
	// Entries holds the paths that exist; BrokenEntries the paths whose
	// lookup fails (for example, a directory that cannot be read).
	Entries       map[string]bool
	BrokenEntries map[string]bool

	// Replay is what Run must be asked, in order, and what each answers.
	Replay []Invocation
	// Ran counts the invocations replayed.
	Ran int
	// Mismatches describes every Run that did not match its invocation.
	Mismatches []string
}

// Invocation is one recorded command and what it did. Failed means the
// command could not start or timed out: Run returns an error. AnyArgv0 leaves
// the command's argv[0] unchecked, for a recording that could not see it.
type Invocation struct {
	Command  process.Command
	Result   process.Result
	Failed   bool
	AnyArgv0 bool
}

// Basename returns the flavor the test set.
func (m *Machine) Basename() fileguard.Basename {
	m.Probes++
	return m.Flavor
}

// LookPath returns the program the test set for the name.
func (m *Machine) LookPath(name string) (process.Program, bool) {
	program, ok := m.Programs[name]
	return program, ok
}

// IsExecutable reports whether the test made the path executable.
func (m *Machine) IsExecutable(path string) bool { return m.Executable[path] }

// IsRegularFile reports whether the test made the path a regular file.
func (m *Machine) IsRegularFile(path string) bool { return m.Files[path] }

// IsWindows reports whether the test made the machine a Windows one.
func (m *Machine) IsWindows() bool { return m.Windows }

// Getwd returns the working directory the test set.
func (m *Machine) Getwd() string { return m.Cwd }

// RealPath returns the real path the test set for the path.
func (m *Machine) RealPath(path string) (string, error) {
	if real, ok := m.RealPaths[path]; ok {
		return real, nil
	}
	return "", fmt.Errorf("fake: %s does not resolve", path)
}

// Exists reports whether the test made the path exist, or fails for a path
// the test made broken.
func (m *Machine) Exists(path string) (bool, error) {
	if m.BrokenEntries[path] {
		return false, fmt.Errorf("fake: %s cannot be looked up", path)
	}
	return m.Entries[path], nil
}

// Run replays the next invocation when the command matches it.
func (m *Machine) Run(command process.Command) (process.Result, error) {
	if m.Unstartable[command.Path] {
		return process.Result{}, fmt.Errorf("fake: %s cannot be started", command.Path)
	}
	if m.Ran >= len(m.Replay) {
		m.Mismatches = append(m.Mismatches, fmt.Sprintf("unexpected command %+v", command))
		return process.Result{}, fmt.Errorf("fake: no invocation left for %v", command.Args)
	}
	want := m.Replay[m.Ran]
	m.Ran++
	if !sameCommand(command, want.Command, want.AnyArgv0) {
		m.Mismatches = append(m.Mismatches, fmt.Sprintf("command %d = %+v, want %+v", m.Ran, command, want.Command))
		return process.Result{}, fmt.Errorf("fake: unexpected command %v", command.Args)
	}
	if want.Failed {
		return process.Result{}, fmt.Errorf("fake: %v failed", command.Args)
	}
	return want.Result, nil
}

// Done reports what is wrong with the replay once the shell is done: the
// mismatches, and the invocations it never made.
func (m *Machine) Done() []string {
	problems := slices.Clone(m.Mismatches)
	for _, left := range m.Replay[min(m.Ran, len(m.Replay)):] {
		problems = append(problems, fmt.Sprintf("command never run: %+v", left.Command))
	}
	return problems
}

func sameCommand(a, b process.Command, anyArgv0 bool) bool {
	argsA, argsB := a.Args, b.Args
	if anyArgv0 && len(argsA) > 0 && len(argsB) > 0 {
		argsA, argsB = argsA[1:], argsB[1:]
	}
	return a.Path == b.Path && slices.Equal(argsA, argsB) && bytes.Equal(a.Stdin, b.Stdin) &&
		a.Timeout == b.Timeout && a.Combined == b.Combined && a.Dir == b.Dir
}
