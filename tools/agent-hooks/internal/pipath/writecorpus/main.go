// Command writecorpus records Pi 1.4.0's answers to the path corpus.
package main

import (
	"errors"
	"fmt"
	"os"
	"os/user"
	"path/filepath"
	"strings"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/pipath/pioracle"
)

func main() {
	if err := writeCorpus(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func writeCorpus() error {
	node, module, err := pioracle.Find()
	if err != nil {
		return err
	}
	cases := pioracle.Cases()
	answers, err := pioracle.Run(node, module, cases)
	if err != nil {
		return err
	}
	privatePaths, err := privateDirectories()
	if err != nil {
		return err
	}
	corpus, err := renderPublicCorpus(cases, answers, privatePaths)
	if err != nil {
		return err
	}
	return os.WriteFile(filepath.FromSlash("internal/pipath/corpus.jsonl"), corpus, 0o600)
}

func privateDirectories() ([]string, error) {
	cwd, err := os.Getwd()
	if err != nil {
		return nil, fmt.Errorf("working directory: %w", err)
	}
	account, err := user.Current()
	if err != nil {
		return nil, fmt.Errorf("home directory: %w", err)
	}
	paths := []string{cwd, os.Getenv("HOME"), account.HomeDir}
	for _, path := range paths {
		if path == "" {
			continue
		}
		real, err := filepath.EvalSymlinks(path)
		if err != nil {
			return nil, fmt.Errorf("private directory: %w", err)
		}
		paths = append(paths, real)
	}
	return paths, nil
}

func renderPublicCorpus(cases []pioracle.Case, answers []pioracle.Answer, privatePaths []string) ([]byte, error) {
	for _, answer := range answers {
		resolved := ""
		if answer.Resolved != nil {
			resolved = *answer.Resolved
		}
		for _, path := range privatePaths {
			if path != "" && (strings.Contains(resolved, path) || strings.Contains(answer.Error, path)) {
				return nil, errors.New("refusing to write an answer containing a local directory")
			}
		}
	}
	return pioracle.Render(cases, answers)
}
