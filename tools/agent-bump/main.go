// agent-bump shows or moves the version of an agent plugin, EGM, Pi package,
// or skill that dotfiles already declares (ADR 0074). Run it through
// `just agent-bump`.
//
//	agent-bump --root DIR                  table of current and newest versions
//	agent-bump --root DIR NAME [VERSION]   move one item (newest without VERSION)
package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"strings"
	"text/tabwriter"

	"github.com/hironow/dotfiles/tools/agent-bump/internal/bump"
)

func main() {
	os.Exit(run(context.Background(), os.Args[1:], os.Stdout, os.Stderr))
}

func run(ctx context.Context, args []string, stdout, stderr io.Writer) int {
	flags := flag.NewFlagSet("agent-bump", flag.ContinueOnError)
	flags.SetOutput(stderr)
	root := flags.String("root", "", "the dotfiles checkout")
	if err := flags.Parse(args); err != nil || *root == "" || flags.NArg() > 2 {
		fmt.Fprintln(stderr, "usage: agent-bump --root DIR [NAME [VERSION]]")
		return 2
	}
	gh, err := newGitHub(ctx)
	if err != nil {
		fmt.Fprintln(stderr, "agent-bump:", err)
		return 1
	}
	app := bump.App{
		Releases: gh,
		Registry: newNpmRegistry(),
		Repo:     checkout{root: *root},
		Machine:  host{root: *root, out: stdout, err: stderr},
	}
	if flags.NArg() == 0 {
		rows, err := app.Table(ctx)
		if err != nil {
			fmt.Fprintln(stderr, "agent-bump:", err)
			return 1
		}
		printTable(stdout, rows)
		return 0
	}
	version := ""
	if flags.NArg() == 2 {
		version = flags.Arg(1)
	}
	res, err := app.Bump(ctx, flags.Arg(0), version)
	if err != nil {
		fmt.Fprintln(stderr, "agent-bump:", err)
		if errors.Is(err, bump.ErrUndeclared) || errors.Is(err, bump.ErrSkillVersion) {
			return 2
		}
		return 1
	}
	printResult(stdout, res)
	return 0
}

func printTable(w io.Writer, rows []bump.Row) {
	tw := tabwriter.NewWriter(w, 0, 0, 2, ' ', 0)
	fmt.Fprintln(tw, "KIND\tNAME\tDECLARED\tNEWEST\t")
	current := 0
	for _, r := range rows {
		mark := ""
		if r.Newer {
			mark = "newer available"
		}
		if r.Note != "" {
			mark = r.Note
		}
		// 170-odd skills: list only those that are behind or unknown.
		if r.Kind == bump.Skill && mark == "" {
			current++
			continue
		}
		fmt.Fprintf(tw, "%s\t%s\t%s\t%s\t%s\n", r.Kind, r.Name, r.Current, r.Latest, mark)
	}
	_ = tw.Flush()
	fmt.Fprintf(w, "\n%d more skills are at their upstream HEAD.\n", current)
	fmt.Fprintln(w, "Move one with: just agent-bump <NAME> [VERSION]")
}

func printResult(w io.Writer, r bump.Result) {
	if len(r.Changed) == 0 && r.Item.Kind != bump.PiPackage {
		fmt.Fprintf(w, "%s is already at %s.\n", r.Item.Name, r.To)
		return
	}
	fmt.Fprintf(w, "%s: %s -> %s, installed and checked on this machine.\n", r.Item.Name, r.From, r.To)
	if len(r.Changed) > 0 {
		fmt.Fprintf(w, "Changed: %s\n", strings.Join(r.Changed, ", "))
		fmt.Fprintln(w, "Commit it and open a PR; other machines follow once they pull and run the installers.")
	}
}
