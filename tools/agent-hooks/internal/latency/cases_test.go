package latency_test

import (
	"path"
	"path/filepath"
	"slices"
	"strings"
	"testing"

	json "github.com/goccy/go-json/v2"

	"github.com/hironow/dotfiles/tools/agent-hooks/harnesses"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/definition"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/latency"
)

func TestCasesHaveUniqueNamesCommandsAndHarnessPayloads(t *testing.T) {
	project := t.TempDir()
	files := filepath.Join(project, "temporary files")
	cases := latency.Cases()
	var names []string
	for _, c := range cases {
		t.Run(c.Name, func(t *testing.T) {
			if slices.Contains(names, c.Name) {
				t.Fatalf("duplicate case %q", c.Name)
			}
			names = append(names, c.Name)
			if c.OldCommand("/claude/hooks", "/codex/hooks") == "" || c.BinaryCommand("/bin/agent-hook") == "" {
				t.Fatal("both command strings are required")
			}
			payload, err := c.Payload(project, files)
			if err != nil {
				t.Fatal(err)
			}
			var parsed map[string]any
			if err := json.Unmarshal(payload, &parsed); err != nil {
				t.Fatal(err)
			}
			def, err := definition.Load(harnesses.FS, c.Harness)
			if err != nil {
				t.Fatal(err)
			}
			event, ok := def.Event(c.Event)
			if !ok || event.Conform(payload) != definition.Conforms {
				t.Fatalf("payload does not conform to %s/%s: %s", c.Harness, c.Event, payload)
			}
			if parsed["cwd"] != project {
				t.Errorf("cwd = %v, want %s", parsed["cwd"], project)
			}
			if c.Harness == "codex" && c.Hook == "formatter" {
				patch := parsed["tool_input"].(map[string]any)["command"].(string)
				path := strings.TrimPrefix(strings.Split(patch, "\n")[1], "*** Add File: ")
				if !filepath.IsAbs(path) || path != filepath.Join(files, c.FileName) || !c.Reset {
					t.Fatalf("formatter must reset an absolute temporary path: %q", path)
				}
			}
		})
	}
	var want []string
	for _, harness := range []string{"claude", "codex"} {
		for _, hook := range []string{"command-guard", "files-guard", "secrets-guard"} {
			for _, answer := range []string{"pass", "block"} {
				want = append(want, harness+"/pre/"+hook+"/"+answer)
			}
		}
		want = append(want, harness+"/pre/rtk/git-status")
		for _, extension := range []string{"md", "py", "go"} {
			want = append(want, harness+"/post/formatter/"+extension)
		}
	}
	slices.Sort(names)
	slices.Sort(want)
	if !slices.Equal(names, want) {
		t.Errorf("cases = %v, want %v", names, want)
	}
}

func TestCommandsUseRegisteredWrappers(t *testing.T) {
	scripts := map[string]string{
		"command-guard": "block-prohibited-commands.sh",
		"files-guard":   "block-prohibited-files.sh",
		"secrets-guard": "block-secrets.sh",
		"formatter":     "format-after-edit.sh",
	}
	for _, c := range latency.Cases() {
		got := c.OldCommand("/claude hooks", "/codex hooks")
		script := scripts[c.Hook]
		argument := ""
		if c.Hook == "rtk" {
			script = "rtk-hook-" + c.Harness + ".sh"
		} else if c.Harness == "codex" && c.Event == "pre" {
			argument, script = " "+script, "guard-codex.sh"
		}
		path := filepath.Join(string(filepath.Separator), c.Harness+" hooks", script)
		want := `bash "` + strings.ReplaceAll(path, `\`, `\\`) + `"` + argument
		if got != want {
			t.Errorf("%s old command = %q, want %q", c.Name, got, want)
		}
		want = `"/binary path/agent-hook" ` + c.Harness + " " + c.Event + " --hook " + c.Hook
		if got := c.BinaryCommand("/binary path/agent-hook"); got != want {
			t.Errorf("%s binary command = %q, want %q", c.Name, got, want)
		}
	}
}

func TestEachCaseNamesWhatItsAnswerMustShow(t *testing.T) {
	for _, c := range latency.Cases() {
		hook, what := path.Split(c.Name)
		switch {
		case strings.HasSuffix(hook, "/rtk/"):
			if c.Want != latency.WantRewrite {
				t.Errorf("%s: want a rewrite", c.Name)
			}
		case what == "pass" || what == "md":
			if c.Want != latency.WantPass || c.Changes {
				t.Errorf("%s: want a pass that changes no file", c.Name)
			}
		case what == "block":
			if c.Want != latency.WantBlock {
				t.Errorf("%s: want a block", c.Name)
			}
		case what == "py" || what == "go":
			if c.Want != latency.WantPass || !c.Changes {
				t.Errorf("%s: want a pass that changes its file", c.Name)
			}
		default:
			t.Errorf("%s: no rule for this case", c.Name)
		}
	}
}

func TestShowsTellsAnAnswerThatTimesSomethingElse(t *testing.T) {
	claudePass := latency.Case{Name: "claude/pre/command-guard/pass", Harness: "claude", Want: latency.WantPass}
	claudeBlock := latency.Case{Name: "claude/pre/command-guard/block", Harness: "claude", Want: latency.WantBlock}
	codexBlock := latency.Case{Name: "codex/pre/command-guard/block", Harness: "codex", Want: latency.WantBlock}
	rtk := latency.Case{Name: "codex/pre/rtk/git-status", Harness: "codex", Want: latency.WantRewrite, Command: "git status"}
	py := latency.Case{Name: "claude/post/formatter/py", Harness: "claude", Want: latency.WantPass, Changes: true, Stderr: "ruff still reports issues"}
	deny := `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"BLOCKED: x"}}` + "\n"
	rewrite := `{"hookSpecificOutput":{"updatedInput":{"command":"/opt/rtk git status"}}}` + "\n"
	for _, test := range []struct {
		name string
		c    latency.Case
		a    latency.Answer
		ok   bool
	}{
		{"a pass", claudePass, latency.Answer{}, true},
		{"a pass that blocks", claudePass, latency.Answer{Exit: 2, Stderr: "BLOCKED: x"}, false},
		{"a pass with an answer on stdout", claudePass, latency.Answer{Stdout: "{}\n"}, false},
		{"Claude's block", claudeBlock, latency.Answer{Exit: 2, Stderr: "BLOCKED: x\n"}, true},
		{"Claude's block that passes", claudeBlock, latency.Answer{}, false},
		{"Codex's block", codexBlock, latency.Answer{Stdout: deny}, true},
		{"Codex's block that passes", codexBlock, latency.Answer{}, false},
		{"rtk's rewrite", rtk, latency.Answer{Stdout: rewrite}, true},
		// rtk not found, or failing: the hooks fail open and print nothing.
		{"no rewrite", rtk, latency.Answer{}, false},
		{"ruff's report", py, latency.Answer{Stderr: "ruff still reports issues in x.py:\nF821\n"}, true},
		{"no report", py, latency.Answer{}, false},
	} {
		if err := test.c.Shows(test.a); (err == nil) != test.ok {
			t.Errorf("%s: Shows = %v, want ok %v", test.name, err, test.ok)
		}
	}
}
