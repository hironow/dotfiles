// Command hooklatency compares deployed hook scripts with agent-hook.
package main

import (
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"runtime"
	"time"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/latency"
)

type options struct {
	runs                             int
	claudeHooks, codexHooks, project string
	binary, only                     string
	budget                           time.Duration
}

func main() {
	os.Exit(run(os.Args[1:], os.Stdout, os.Stderr))
}

func run(args []string, stdout, stderr io.Writer) int {
	config, cases, err := parse(args)
	if err == nil && runtime.GOOS == "windows" {
		err = errors.New("there is no file log on Windows yet, so the log check cannot run")
	}
	if err != nil {
		fmt.Fprintln(stderr, "hooklatency:", err)
		return 2
	}
	rows, err := execute(config, cases)
	if err != nil {
		fmt.Fprintln(stderr, "hooklatency:", err)
		return 2
	}
	if _, err := io.WriteString(stdout, latency.Table(rows, config.budget, runtime.GOOS, runtime.GOARCH, runtime.Version(), config.runs)); err != nil {
		fmt.Fprintln(stderr, "hooklatency: write report:", err)
		return 2
	}
	for _, row := range rows {
		if !latency.WithinBudget(latency.Percentile(row.Old, 95), latency.Percentile(row.Binary, 95), config.budget) {
			return 1
		}
	}
	return 0
}

func parse(args []string) (options, []latency.Case, error) {
	var config options
	home, err := os.UserHomeDir()
	if err != nil {
		return config, nil, err
	}
	flags := flag.NewFlagSet("hooklatency", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	flags.IntVar(&config.runs, "runs", 200, "rounds per case")
	flags.StringVar(&config.claudeHooks, "claude-hooks", filepath.Join(home, ".claude", "hooks"), "deployed Claude hooks directory")
	flags.StringVar(&config.codexHooks, "codex-hooks", filepath.Join(home, ".codex", "hooks"), "deployed Codex hooks directory")
	flags.StringVar(&config.project, "project", "", "project directory (default: git root)")
	flags.StringVar(&config.binary, "binary", "", "agent-hook path (default: build once)")
	flags.StringVar(&config.only, "only", "", "case name regexp")
	flags.DurationVar(&config.budget, "budget", 15*time.Millisecond, "allowed p95 increase")
	if err := flags.Parse(args); err != nil {
		return config, nil, err
	}
	if flags.NArg() != 0 || config.runs <= 0 || config.budget < 0 {
		return config, nil, errors.New("expected flags only, positive --runs, and nonnegative --budget")
	}
	pattern, err := regexp.Compile(config.only)
	if err != nil {
		return config, nil, fmt.Errorf("--only: %w", err)
	}
	var cases []latency.Case
	for _, c := range latency.Cases() {
		if pattern.MatchString(c.Name) {
			cases = append(cases, c)
		}
	}
	if len(cases) == 0 {
		return config, nil, errors.New("--only matches no cases")
	}
	return config, cases, nil
}
