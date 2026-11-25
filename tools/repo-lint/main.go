// repo-lint checks the repository's file policies that a Semgrep rule cannot
// hold: a value read from a file's structure, or values compared across files
// (ADR-0093). Each rule's tests use in-memory values; the gate runs every rule
// over the repository through `just repo-lint`.
package main

import (
	"flag"
	"fmt"
	"io"
	"os"

	"github.com/hironow/dotfiles/tools/repo-lint/internal/load"
	"github.com/hironow/dotfiles/tools/repo-lint/internal/rules"
)

func main() {
	os.Exit(run(os.Args[1:], os.Stdout, os.Stderr, nil, rules.All()))
}

// run checks every rule and returns the exit code: 0 when every rule holds,
// 1 on a finding, 2 when an input cannot be read or the arguments are wrong.
// A nil src reads the repository at --root through yq.
func run(args []string, stdout, stderr io.Writer, src load.Source, all []rules.Rule) int {
	flags := flag.NewFlagSet("repo-lint", flag.ContinueOnError)
	flags.SetOutput(stderr)
	root := flags.String("root", ".", "the repository root")
	yq := flags.String("yq", "yq", "the yq executable (mikefarah/yq) that reads TOML and YAML")
	list := flags.Bool("list", false, "print each rule and why it exists")
	if err := flags.Parse(args); err != nil {
		return 2
	}
	if *list {
		for _, r := range all {
			fmt.Fprintf(stdout, "%s\t%s\n", r.ID, r.Why)
		}
		return 0
	}
	if src == nil {
		src = load.Files{Root: *root, YQ: *yq}
	}
	inputs := rules.Inputs{}
	failed := false
	for _, in := range rules.Paths(all) {
		v, err := src.Load(in)
		if err != nil {
			fmt.Fprintf(stderr, "repo-lint: %v\n", err)
			failed = true
			continue
		}
		inputs[in.Path] = v
	}
	if failed {
		return 2
	}
	code := 0
	for _, r := range all {
		for _, f := range r.Check(inputs) {
			fmt.Fprintln(stdout, f.String())
			code = 1
		}
	}
	return code
}
