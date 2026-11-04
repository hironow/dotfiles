package main

import (
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/pipath/pioracle"
)

func TestRenderPublicCorpusRejectsLocalAnswers(t *testing.T) {
	cases := []pioracle.Case{{Path: "x", Cwd: "/w", Home: "/home/user"}}
	privatePaths := []string{"/machine/work", "/machine/home"}
	for _, path := range []string{"/machine/work/x", "/machine/home/x", "/w/prefix/machine/home/x"} {
		t.Run(path, func(t *testing.T) {
			answers := []pioracle.Answer{{Resolved: &path}}
			if _, err := renderPublicCorpus(cases, answers, privatePaths); err == nil {
				t.Fatal("accepted an answer containing a local directory")
			}
		})
	}
	answers := []pioracle.Answer{{Error: "error at /machine/work"}}
	if _, err := renderPublicCorpus(cases, answers, privatePaths); err == nil {
		t.Fatal("accepted an error containing a local directory")
	}
}

func TestRenderPublicCorpusKeepsMadeUpPaths(t *testing.T) {
	cases := []pioracle.Case{{Path: "x", Cwd: "/w", Home: "/home/user"}}
	path := "/w/x"
	answers := []pioracle.Answer{{Resolved: &path}}
	corpus, err := renderPublicCorpus(cases, answers, []string{"", "/machine/work", "/machine/home"})
	if err != nil {
		t.Fatal(err)
	}
	entries, err := pioracle.Parse(corpus)
	if err != nil {
		t.Fatal(err)
	}
	if len(entries) != 1 || entries[0].Resolved == nil || *entries[0].Resolved != path {
		t.Fatalf("changed the public answer: %+v", entries)
	}
}
