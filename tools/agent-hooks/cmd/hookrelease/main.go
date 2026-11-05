// Command hookrelease builds immutable, reproducible agent-hook releases.
package main

import (
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"runtime"
	"strings"
)

func main() {
	os.Exit(run(os.Args[1:], os.Stdout, os.Stderr))
}

func run(args []string, stdout, stderr io.Writer) int {
	if len(args) > 0 && args[0] == "check" {
		return checkCommand(args[1:], stderr)
	}
	if len(args) > 0 && args[0] == "switch" {
		previous, err := switchCommand(args[1:])
		if err != nil {
			fmt.Fprintln(stderr, "hookrelease switch:", err)
			return 2
		}
		fmt.Fprintln(stdout, previous)
		return 0
	}
	path, err := buildCommand(args, stderr)
	if err != nil {
		fmt.Fprintln(stderr, "hookrelease:", err)
		return 2
	}
	fmt.Fprintln(stdout, path)
	return 0
}

func buildCommand(args []string, stderr io.Writer) (string, error) {
	if len(args) == 0 || strings.HasPrefix(args[0], "-") {
		args = append([]string{"build"}, args...)
	}
	if args[0] != "build" {
		return "", errors.New("usage: hookrelease build [--into DIR] [--goos OS --goarch ARCH]")
	}
	flags := flag.NewFlagSet("build", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	var into string
	target := buildTarget{OS: runtime.GOOS, Arch: runtime.GOARCH}
	flags.StringVar(&into, "into", "", "releases directory")
	flags.StringVar(&target.OS, "goos", target.OS, "target operating system")
	flags.StringVar(&target.Arch, "goarch", target.Arch, "target architecture")
	if err := flags.Parse(args[1:]); err != nil {
		return "", err
	}
	if flags.NArg() != 0 {
		return "", errors.New("expected build flags only")
	}
	if into == "" {
		root, err := dataRoot()
		if err != nil {
			return "", err
		}
		into = filepath.Join(root, "releases")
	}
	plan, err := prepareRelease(target)
	if err != nil {
		return "", err
	}
	return plan.build(into, stderr)
}
