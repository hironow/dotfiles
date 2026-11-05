package selftest

import (
	"slices"
	"strings"
	"testing"
)

func TestEveryCaseHasAnAnswerAndEveryAnswerACase(t *testing.T) {
	var names []string
	for _, c := range Cases() {
		if slices.Contains(names, c.Name) {
			t.Errorf("two cases named %s", c.Name)
		}
		names = append(names, c.Name)
		if _, ok := answers[c.Name]; !ok {
			t.Errorf("%s has no answer", c.Name)
		}
	}
	for name := range answers {
		if !slices.Contains(names, name) {
			t.Errorf("the answer %s has no case", name)
		}
	}
}

func TestTheCasesCoverEveryAnswerPathOfClaudeAndCodex(t *testing.T) {
	// Each guard on a pass and a block, rtk's forward, and the formatter's
	// post notice, on both harnesses: every answer form a registration uses.
	var want []string
	for _, harness := range []string{"claude", "codex"} {
		for _, guard := range []string{"command-guard", "files-guard", "secrets-guard"} {
			want = append(want, harness+"/pre/"+guard+"/pass", harness+"/pre/"+guard+"/block")
		}
		want = append(want, harness+"/pre/rtk/forward", harness+"/post/formatter/notice")
	}
	var got []string
	for _, c := range Cases() {
		got = append(got, c.Name)
	}
	slices.Sort(got)
	slices.Sort(want)
	if !slices.Equal(got, want) {
		t.Errorf("cases %v, want %v", got, want)
	}
}

func TestRunPassesOnThisBinary(t *testing.T) {
	// given the binary's own code, when it answers its cases
	n, err := Run()
	// then every case answers as recorded
	if err != nil {
		t.Fatal(err)
	}
	if n != len(Cases()) {
		t.Errorf("Run checked %d cases, want %d", n, len(Cases()))
	}
}

func TestRunNamesTheFirstCaseThatAnswersOtherwise(t *testing.T) {
	// given one recorded answer that the binary does not give
	name := "codex/pre/command-guard/block"
	saved := answers[name]
	t.Cleanup(func() { answers[name] = saved })
	changed := saved
	changed.stdout = strings.Replace(changed.stdout, "deny", "allow", 1)
	answers[name] = changed
	// when the binary answers its cases
	_, err := Run()
	// then the selftest fails, naming the case and both answers
	if err == nil || !strings.Contains(err.Error(), name) || !strings.Contains(err.Error(), "allow") {
		t.Fatalf("Run = %v, want an error naming %s and the recorded answer", err, name)
	}
}

func TestRunFailsWhenAHookDoesNotRunWhatItShould(t *testing.T) {
	// given an rtk case whose fake rtk is never asked (another payload)
	for _, c := range Cases() {
		if c.Name != "claude/pre/rtk/forward" {
			continue
		}
		c.Payload = strings.Replace(c.Payload, "git status", "git log", 1)
		// when it runs
		err := check(c, answers[c.Name])
		// then it fails, though some answer came back
		if err == nil {
			t.Fatal("check passed a run whose rtk was not asked as recorded")
		}
		return
	}
	t.Fatal("no claude/pre/rtk/forward case")
}
