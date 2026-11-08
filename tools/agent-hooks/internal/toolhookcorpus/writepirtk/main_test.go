package main

import (
	"encoding/base64"
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/toolhookcorpus/pirtk"
)

func TestRenderPublicCorpusRejectsLocalPaths(t *testing.T) {
	// A path that is not ASCII is written escaped (pioracle.ASCIILine).
	for _, local := range []string{"/machine/work", "/machine/home", `C:\machine\home`, "/machine/\u30e6\u30fc\u30b6\u30fc"} {
		for _, field := range []string{"command", "argv", "env", "fake", "stdout", "late"} {
			t.Run(local+"/"+field, func(t *testing.T) {
				scenarios := []pirtk.Scenario{{Name: "public", Command: "git status", Env: map[string]string{}}}
				answers := []pirtk.Answer{{Command: "rtk git status"}}
				switch field {
				case "command":
					answers[0].Command = "rtk cat " + local + "/secret"
				case "argv":
					answers[0].Argv = [][]string{{"rewrite", "cat " + local + "/secret"}}
				case "env":
					scenarios[0].Env["RTK_DISABLED"] = local
				case "fake":
					scenarios[0].Fake.Version.Stdout = local
				case "stdout":
					scenarios[0].Fake.Rewrite.StdoutB64 = base64.StdEncoding.EncodeToString([]byte(local))
				case "late":
					scenarios[0].Fake.Rewrite.LateB64 = base64.StdEncoding.EncodeToString([]byte(local))
				}
				if _, err := renderPublicCorpus(nil, scenarios, answers, []string{"", local}); err == nil {
					t.Fatal("accepted a local path in the corpus")
				}
			})
		}
	}
}

func TestRenderPublicCorpusKeepsPublicAnswers(t *testing.T) {
	scenarios := []pirtk.Scenario{{Name: "public", Command: "git status", Env: map[string]string{}}}
	answers := []pirtk.Answer{{Command: "rtk git status"}}
	corpus, err := renderPublicCorpus(nil, scenarios, answers, []string{"", "/machine/work", "/machine/home"})
	if err != nil {
		t.Fatal(err)
	}
	_, entries, err := pirtk.Parse(corpus)
	if err != nil {
		t.Fatal(err)
	}
	if len(entries) != 1 || entries[0].Scenario.Command != "git status" || entries[0].Answer.Command != "rtk git status" {
		t.Fatalf("changed the public run: %+v", entries)
	}
}
