package main

import (
	"slices"
	"testing"
)

func TestPiProblemsNameEveryDeclaredSourceThisMachineLacks(t *testing.T) {
	declared := []string{
		"npm:pi-goal-x",
		"npm:@ollama/pi-web-search@0.4.0",
		"npm:typo-not-installed", // a hand edit not installed yet
		"git:github.com/google/elephant-goldfish-model@v0.1.0",
	}
	configured := []string{"npm:pi-goal-x", "npm:@ollama/pi-web-search@0.4.0", "npm:typo-not-installed"}
	installed := map[string]string{"pi-goal-x": "1.0.0", "@ollama/pi-web-search": "0.3.9"}
	got := piProblems(declared, configured, installed)
	want := []string{
		"pi has @ollama/pi-web-search 0.3.9, want 0.4.0",
		"pi has no files for typo-not-installed",
	}
	if !slices.Equal(got, want) {
		t.Fatalf("got %q\nwant %q", got, want)
	}
	if got := piProblems(declared[:1], nil, installed); !slices.Equal(got, []string{"pi settings.json does not name npm:pi-goal-x"}) {
		t.Fatalf("unconfigured source: %q", got)
	}
	if got := piProblems(declared[:2], configured, map[string]string{"pi-goal-x": "1.0.0", "@ollama/pi-web-search": "0.4.0"}); got != nil {
		t.Fatalf("all installed: %q", got)
	}
}
