package main_test

import (
	"bytes"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"slices"
	"strings"
	"testing"

	json "github.com/goccy/go-json/v2"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/guardcorpus"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/toolhookcorpus"
)

// probe is the variable the corpus's programs show they inherit.
const probe = "agent-hook-probe"

// loggedInvocation is one line faketool logs.
type loggedInvocation struct {
	Tool   string                `json:"tool"`
	Argv   []string              `json:"argv"`
	Stdin  *string               `json:"stdin"`
	Cwd    string                `json:"cwd"`
	Env    map[string]*string    `json:"env"`
	Answer toolhookcorpus.Answer `json:"answer"`
}

func TestTheBinaryDoesWhatTheToolHooksCorpusExpects(t *testing.T) {
	skipWithoutPOSIXShell(t)
	for hook, scenarios := range map[string][]toolhookcorpus.Scenario{
		"rtk":       toolhookcorpus.RTK(t),
		"formatter": toolhookcorpus.Formatter(t),
	} {
		event := map[string]string{"rtk": "pre", "formatter": "post"}[hook]
		for _, scenario := range scenarios {
			for _, run := range scenario.Runs {
				t.Run(guardcorpus.Frame(run.Difference)+"/"+hook+"/"+scenario.Name+"/"+run.Harness, func(t *testing.T) {
					t.Parallel()
					runScenario(t, scenario, run, hook, event)
				})
			}
		}
	}
}

// runScenario builds the scenario's root, runs the binary in it, and checks
// its answer and every program it ran.
func runScenario(t *testing.T, scenario toolhookcorpus.Scenario, run toolhookcorpus.Run, hook, event string) {
	root, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	sub := func(text string) string { return strings.ReplaceAll(text, toolhookcorpus.Root, root) }
	build(t, root, scenario.Environment, sub)
	path := make([]string, 0, len(scenario.Environment.Path)+1)
	for _, entry := range scenario.Environment.Path {
		path = append(path, sub(entry))
	}
	path = append(path, filepath.Join(root, "sys-bin"))

	// Audited: binary is the agent-hook this test built, and the arguments
	// are the corpus's harness and hook names.
	// nosemgrep: go.lang.security.audit.dangerous-exec-command.dangerous-exec-command
	command := exec.Command(binary, run.Harness, event, "--hook", hook)
	command.Dir = filepath.Join(root, scenario.Environment.Cwd)
	command.Env = []string{
		"PATH=" + strings.Join(path, ":"), "HOME=" + filepath.Join(root, "home"),
		"LC_ALL=C.UTF-8", "AGENT_HOOK_PROBE=" + probe,
	}
	command.Stdin = bytes.NewReader([]byte(sub(string(scenario.Stdin))))
	var stdout, stderr bytes.Buffer
	command.Stdout, command.Stderr = &stdout, &stderr
	exit := 0
	if err := command.Run(); err != nil {
		var exitErr *exec.ExitError
		if !errors.As(err, &exitErr) {
			t.Fatalf("run: %v", err)
		}
		exit = exitErr.ExitCode()
	}
	where := scenario.Name + " " + run.Harness + " (difference " + run.Difference + ")"
	run.ExpectedGo.Check(t, where, exit, stdout.String(), stderr.String(), sub)
	checkInvocations(t, where, root, run.ExpectedGo.Invocations, sub)
}

// build makes the scenario's temporary root: directories, files, links, and
// each fake as a script that runs faketool.
func build(t *testing.T, root string, env toolhookcorpus.Environment, sub func(string) string) {
	t.Helper()
	for _, dir := range append([]string{"work", "home", "sys-bin"}, env.Dirs...) {
		mustDo(t, os.MkdirAll(filepath.Join(root, dir), 0o755))
	}
	for name, content := range env.Files {
		mustDo(t, os.MkdirAll(filepath.Dir(filepath.Join(root, name)), 0o755))
		mustDo(t, os.WriteFile(filepath.Join(root, name), []byte(content), 0o644))
	}
	for name, target := range env.Links {
		mustDo(t, os.MkdirAll(filepath.Dir(filepath.Join(root, name)), 0o755))
		mustDo(t, os.Symlink(sub(target), filepath.Join(root, name)))
	}
	rules := map[string]toolhookcorpus.Rule{}
	for label, rule := range env.Fakes {
		config, err := json.Marshal(map[string]string{"root": root, "label": label})
		mustDo(t, err)
		script := filepath.Join(root, label)
		mustDo(t, os.MkdirAll(filepath.Dir(script), 0o755))
		mustDo(t, os.WriteFile(script, []byte("#!"+faketool+"\n"+string(config)+"\n"), 0o755))
		rules[label] = withRoot(rule, sub)
	}
	data, err := json.Marshal(rules)
	mustDo(t, err)
	mustDo(t, os.WriteFile(filepath.Join(root, "fakes.json"), data, 0o644))
}

// withRoot puts the root into a rule's answers, as the generator did.
func withRoot(rule toolhookcorpus.Rule, sub func(string) string) toolhookcorpus.Rule {
	answer := func(a *toolhookcorpus.Answer) *toolhookcorpus.Answer {
		if a == nil {
			return nil
		}
		return &toolhookcorpus.Answer{Stdout: []byte(sub(string(a.Stdout))), Stderr: a.Stderr, Exit: a.Exit}
	}
	rule.Stdout = []byte(sub(string(rule.Stdout)))
	rule.Default, rule.Clean = answer(rule.Default), answer(rule.Clean)
	if rule.Checks != nil {
		checks := map[string]toolhookcorpus.Answer{}
		for path, a := range rule.Checks {
			checks[path] = *answer(&a)
		}
		rule.Checks = checks
	}
	return rule
}

// checkInvocations compares what faketool logged with the expected
// invocations: which fake, the path given to execve, the arguments, stdin,
// the working directory, and the environment the program saw.
func checkInvocations(t *testing.T, where, root string, expected []toolhookcorpus.Invocation, sub func(string) string) {
	t.Helper()
	var logged []loggedInvocation
	if data, err := os.ReadFile(filepath.Join(root, "invocations.jsonl")); err == nil {
		for line := range strings.SplitSeq(strings.TrimSuffix(string(data), "\n"), "\n") {
			var invocation loggedInvocation
			mustDo(t, json.Unmarshal([]byte(line), &invocation))
			logged = append(logged, invocation)
		}
	}
	if len(logged) != len(expected) {
		t.Fatalf("%s: ran %d programs, want %d: %+v", where, len(logged), len(expected), logged)
	}
	for i, want := range expected {
		got := logged[i]
		args := make([]string, len(want.Args))
		for j, arg := range want.Args {
			args[j] = sub(arg)
		}
		wantStdin := ""
		if want.Stdin != nil {
			wantStdin = sub(string(want.Stdin))
		}
		gotStdin := ""
		if got.Stdin != nil {
			gotStdin = *got.Stdin
		}
		if got.Tool != want.Tool || got.Argv[0] != sub(want.Path) || !slices.Equal(got.Argv[1:], args) ||
			gotStdin != wantStdin || (got.Stdin == nil) != (want.Stdin == nil) || got.Cwd != sub(want.Cwd) {
			t.Errorf("%s: program %d = %s %q in %s (stdin %q); want %s %s %q in %s (stdin %q)",
				where, i, got.Tool, got.Argv, got.Cwd, gotStdin, want.Tool, sub(want.Path), args, sub(want.Cwd), wantStdin)
		}
		for name, value := range want.Env {
			gotValue := got.Env[name]
			if (value == nil) != (gotValue == nil) || (value != nil && sub(*value) != *gotValue) {
				t.Errorf("%s: program %d saw %s=%v, want %v", where, i, name, deref(gotValue), deref(value))
			}
		}
	}
}

func deref(s *string) string {
	if s == nil {
		return "<unset>"
	}
	return *s
}

func mustDo(t *testing.T, err error) {
	t.Helper()
	if err != nil {
		t.Fatal(err)
	}
}
