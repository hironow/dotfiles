package pirtk

import (
	"encoding/base64"
	"fmt"
)

type scenarioKind string

const (
	relativePath scenarioKind = "path-relative"
	versionProbe scenarioKind = "rtk-version-probe"
	signalDeath  scenarioKind = "rtk-signal"
	invalidUTF8  scenarioKind = "rtk-answer-invalid-utf8"
	splitUTF8    scenarioKind = "rtk-split-utf8"
	lateOutput   scenarioKind = "rtk-late-output"
)

// Scenarios returns a new, deterministic list. All default rewrite bytes are
// recorded explicitly, so another runner can replay without hidden defaults.
func Scenarios() []Scenario {
	var scenarios []Scenario
	for _, exit := range []int{0, 3} {
		s := defaultScenario(fmt.Sprintf("rewrite-exit-%d", exit), "git status")
		s.Fake.Rewrite.Exit = exit
		scenarios = append(scenarios, s)
	}
	for _, exit := range []int{1, 2, 127} {
		s := defaultScenario(fmt.Sprintf("rewrite-exit-%d", exit), "git status")
		s.Fake.Rewrite.Exit = exit
		stdout := "rtk x"
		if exit == 1 {
			stdout = ""
		}
		s.Fake.Rewrite.StdoutB64 = encode(stdout)
		scenarios = append(scenarios, s)
	}
	for _, test := range []struct{ name, stdout string }{
		{"rewrite-empty", ""},
		{"rewrite-unchanged", "git status"},
		{"rewrite-multiline", "rtk git status\nrtk git diff\n"},
	} {
		s := defaultScenario(test.name, "git status")
		s.Fake.Rewrite.StdoutB64 = encode(test.stdout)
		scenarios = append(scenarios, s)
	}
	for _, space := range "\t\v\f \u00a0\ufeff\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u202f\u205f\u3000\n\r\u2028\u2029" {
		s := defaultScenario(fmt.Sprintf("trim-u%04x", space), "git status")
		s.Fake.Rewrite.StdoutB64 = encode(string(space) + "rtk git status" + string(space))
		scenarios = append(scenarios, s)
	}
	for _, kept := range "\u0085\u200b\u180e\u2060" {
		s := defaultScenario(fmt.Sprintf("keep-u%04x", kept), "git status")
		s.Fake.Rewrite.StdoutB64 = encode(string(kept) + "rtk git status" + string(kept))
		scenarios = append(scenarios, s)
	}
	scenarios = append(scenarios, processScenarios()...)
	scenarios = append(scenarios, gateScenarios()...)
	return scenarios
}

func processScenarios() []Scenario {
	var scenarios []Scenario
	s := defaultScenario("rewrite-stderr", "git status")
	s.Fake.Rewrite.Stderr = "rtk diagnostic\n"
	scenarios = append(scenarios, s)
	s = defaultScenario("rewrite-timeout", "git status")
	s.Fake.Rewrite.SleepMs = 3000
	scenarios = append(scenarios, s)
	s = defaultScenario("path-absent", "git status")
	s.Fake.Path = "absent"
	scenarios = append(scenarios, s)
	s = defaultScenario("path-relative", "git status")
	s.Fake.Path, s.kind = "relative", relativePath
	scenarios = append(scenarios, s)
	for _, test := range []struct {
		name, stdout string
		exit         int
		kind         scenarioKind
	}{
		{"version-exit-1", "rtk 1.1.0\n", 1, versionProbe},
		{"version-old", "rtk 0.22.0\n", 0, versionProbe},
		{"version-dev", "rtk dev\n", 0, ""},
	} {
		s = defaultScenario(test.name, "git status")
		s.Fake.Version = Version{Exit: test.exit, Stdout: test.stdout}
		s.kind = test.kind
		scenarios = append(scenarios, s)
	}
	s = defaultScenario("rewrite-signal", "git status")
	// Exit 1 if the signal failed, so only a real signal death reads as
	// code 0 (`code ?? 0`) and rewrites.
	s.Fake.Rewrite.Signal, s.Fake.Rewrite.Exit, s.kind = true, 1, signalDeath
	scenarios = append(scenarios, s)
	s = defaultScenario("rewrite-invalid-utf8", "git status")
	s.Fake.Rewrite.StdoutB64, s.kind = encode("rtk \xff git"), invalidUTF8
	scenarios = append(scenarios, s)
	s = defaultScenario("rewrite-split-utf8", "git status")
	s.Fake.Rewrite.StdoutB64, s.Fake.Rewrite.PauseAt, s.kind = encode("rtk echo 雪"), 10, splitUTF8
	scenarios = append(scenarios, s)
	s = defaultScenario("rewrite-late-output", "git status")
	s.Fake.Rewrite.StdoutB64, s.Fake.Rewrite.LateB64, s.kind = encode("rtk git status"), encode(" --short"), lateOutput
	s.Fake.Rewrite.LateMs = 350
	scenarios = append(scenarios, s)
	// The same tail inside the grace: rtk.ts keeps it, which shows the
	// background child does write.
	s = defaultScenario("rewrite-late-in-grace", "git status")
	s.Fake.Rewrite.StdoutB64, s.Fake.Rewrite.LateB64 = encode("rtk git status"), encode(" --short")
	s.Fake.Rewrite.LateMs = 10
	return append(scenarios, s)
}

func gateScenarios() []Scenario {
	var scenarios []Scenario
	for _, test := range []struct{ name, command string }{
		{"command-rtk-space", "rtk git status"},
		{"command-rtk-tab", "rtk\tgit status"},
		{"command-empty", ""},
		{"command-space", " "},
		{"command-tab", "\t"},
		{"command-u3000", "\u3000"},
		{"command-ufeff", "\ufeff"},
		{"command-u2028", "\u2028"},
		{"command-u0085", "\u0085"},
		{"command-unicode", "echo 日本語"},
		// Node's spawn refuses a NUL in an argument; rtk.ts's handler passes.
		{"command-nul", "a\x00b"},
		// The prefix is checked on the command as given, and rtk gets it
		// untrimmed; only "rtk " with the space passes.
		{"command-space-rtk", " rtk git status"},
		{"command-padded", "  git status  "},
		{"command-rtk-bare", "rtk"},
	} {
		scenarios = append(scenarios, defaultScenario(test.name, test.command))
	}
	for _, test := range []struct{ name, value string }{
		{"disabled-1", "1"},
		{"disabled-0", "0"},
		{"disabled-space-1", " 1"},
		{"disabled-true", "true"},
		{"disabled-empty", ""},
	} {
		s := defaultScenario(test.name, "git status")
		s.Env["RTK_DISABLED"] = test.value
		scenarios = append(scenarios, s)
	}
	return append(scenarios, defaultScenario("disabled-unset", "git status"), defaultScenario("command-number", 1))
}

func defaultScenario(name string, command any) Scenario {
	stdout := ""
	if text, ok := command.(string); ok {
		stdout = "rtk " + text + "\n"
	}
	return Scenario{
		Name: name, Command: command, Env: map[string]string{},
		Fake: Fake{Path: "absolute", Version: Version{Stdout: "rtk 1.1.0\n"}, Rewrite: Rewrite{StdoutB64: encode(stdout)}},
	}
}

func encode(value string) string {
	return base64.StdEncoding.EncodeToString([]byte(value))
}
