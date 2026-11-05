package registration_test

import (
	"bytes"
	"strings"
	"testing"

	"github.com/goccy/go-json/jsontext"
	json "github.com/goccy/go-json/v2"

	"github.com/hironow/dotfiles/tools/agent-hooks/harnesses"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/definition"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/registration"
)

func TestMainRendersClaudeExec(t *testing.T) {
	var stdout, stderr bytes.Buffer
	exit := registration.Main([]string{"--harness", "claude", "--os", "linux", "--binary", "/state/dotfiles/agent-hooks/current/claude/agent-hook"}, &stdout, &stderr)
	want := `{"hooks":{"PreToolUse":[{"matcher":"Write|Edit|NotebookEdit","hooks":[{"type":"command","command":"/state/dotfiles/agent-hooks/current/claude/agent-hook","args":["claude","pre","--hook","files-guard"],"timeout":30,"onFailure":"block"},{"type":"command","command":"/state/dotfiles/agent-hooks/current/claude/agent-hook","args":["claude","pre","--hook","secrets-guard"],"timeout":30,"onFailure":"block"}]},{"matcher":"Bash","hooks":[{"type":"command","command":"/state/dotfiles/agent-hooks/current/claude/agent-hook","args":["claude","pre","--hook","command-guard"],"timeout":30,"onFailure":"block"}]},{"matcher":"Bash","hooks":[{"type":"command","command":"/state/dotfiles/agent-hooks/current/claude/agent-hook","args":["claude","pre","--hook","rtk"],"timeout":30}]}],"PostToolUse":[{"matcher":"Write|Edit","hooks":[{"type":"command","command":"/state/dotfiles/agent-hooks/current/claude/agent-hook","args":["claude","post","--hook","formatter"],"timeout":30}]}]}}` + "\n"
	if exit != 0 || stdout.String() != want || stderr.Len() != 0 {
		t.Fatalf("exit %d, stdout %s, stderr %s; want %s", exit, &stdout, &stderr, want)
	}
}

func TestShellFormsAndLosses(t *testing.T) {
	const posix = "/a'$ `日本/dotfiles/agent-hooks/releases/abcdef012345/agent-hook"
	const windows = "C:\\a'$ `日本\\dotfiles\\agent-hooks\\current\\codex\\agent-hook.exe"
	const deny = `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"agent-hook failed"}}`
	for _, test := range []struct{ os, shell, path, closed, open string }{
		{"darwin", "sh", posix, "'/a'\\''$ `日本/dotfiles/agent-hooks/releases/abcdef012345/agent-hook' codex pre --hook command-guard || { printf '%s\\n' 'agent-hook failed' >&2; exit 2; }", "'/a'\\''$ `日本/dotfiles/agent-hooks/releases/abcdef012345/agent-hook' codex pre --hook rtk"},
		{"linux", "", posix, "'/a'\\''$ `日本/dotfiles/agent-hooks/releases/abcdef012345/agent-hook' codex pre --hook command-guard || { printf '%s\\n' 'agent-hook failed' >&2; exit 2; }", "'/a'\\''$ `日本/dotfiles/agent-hooks/releases/abcdef012345/agent-hook' codex pre --hook rtk"},
		{"windows", "powershell", windows, "& 'C:\\a''$ `日本\\dotfiles\\agent-hooks\\current\\codex\\agent-hook.exe' codex pre --hook command-guard; if ($LASTEXITCODE -ne 0) { '" + deny + "' }", "& 'C:\\a''$ `日本\\dotfiles\\agent-hooks\\current\\codex\\agent-hook.exe' codex pre --hook rtk"},
		{"windows", "cmd", windows, `"` + windows + `" codex pre --hook command-guard || echo ` + deny, `"` + windows + `" codex pre --hook rtk`},
	} {
		t.Run(test.os+"/"+test.shell, func(t *testing.T) {
			args := []string{"--harness", "codex", "--os", test.os, "--binary", test.path}
			if test.shell != "" {
				args = append(args, "--shell", test.shell)
			}
			var out, report bytes.Buffer
			if exit := registration.Main(args, &out, &report); exit != 0 {
				t.Fatalf("exit %d: %s", exit, &report)
			}
			var fragment struct {
				Hooks map[string][]struct {
					Hooks []struct {
						Command string `json:"command"`
					} `json:"hooks"`
				} `json:"hooks"`
			}
			if err := json.Unmarshal(out.Bytes(), &fragment); err != nil {
				t.Fatal(err)
			}
			pre := fragment.Hooks["PreToolUse"]
			if got := pre[1].Hooks[0].Command; got != test.closed {
				t.Errorf("closed %q, want %q", got, test.closed)
			}
			if got := pre[2].Hooks[0].Command; got != test.open {
				t.Errorf("open %q, want %q", got, test.open)
			}
			want := ""
			if test.os == "windows" {
				want = `{"level":"degraded","harness":"codex","os":"windows","hook":"command-guard","tool":"Bash","reason":"Codex runs PowerShell on Windows; the guard reads its text with bash grammar (PR 2e.4)"}` + "\n"
			}
			if report.String() != want {
				t.Errorf("loss report %q, want %q", &report, want)
			}
		})
	}
}

func TestRenderPreservesTemplateAndFirstBlockEventOrder(t *testing.T) {
	def, err := definition.Load(harnesses.FS, "claude")
	if err != nil {
		t.Fatal(err)
	}
	reg := *def.Registration
	reg.Blocks = append([]definition.RegistrationBlock{reg.Blocks[3]}, reg.Blocks[:3]...)
	reg.Launchers = []definition.Launcher{{
		OS: []string{"linux"}, Shell: "exec",
		Closed: jsontext.Value(`{"command":"{{.Binary}}","type":"command","args":[]}`),
		Open:   jsontext.Value(`{"command":"{{.Binary}}","type":"command","args":[]}`),
	}}
	def.Registration = &reg
	def.Pending = []string{"uncaptured"}
	def.Support["rtk"]["Bash"] = definition.Support{Level: "unsupported", Reason: "not available"}
	hooks := []registration.Hook{{ID: "formatter", Event: "post", Failure: "open"}, {ID: "files-guard", Event: "pre", Failure: "closed"}, {ID: "secrets-guard", Event: "pre", Failure: "closed"}, {ID: "command-guard", Event: "pre", Failure: "closed"}, {ID: "rtk", Event: "pre", Failure: "open"}}
	out, losses, err := registration.Render(def, hooks, "linux", "", "/dotfiles/agent-hooks/current/claude/agent-hook")
	if err != nil {
		t.Fatal(err)
	}
	if !strings.HasPrefix(string(out), `{"hooks":{"PostToolUse":[{"matcher":"Write|Edit","hooks":[{"command":`) ||
		!bytes.HasSuffix(out, []byte("}}\n")) {
		t.Fatalf("lost order or newline: %s", out)
	}
	if len(losses) != 2 || losses[0].Level != "unsupported" || losses[0].Hook != "rtk" || losses[1].Level != "pending" || losses[1].Hook != "" || losses[1].Reason == "" {
		t.Fatalf("losses: %+v", losses)
	}
}

func TestMainRefusesPathsAndShellsWithoutAFragment(t *testing.T) {
	const stable = "/state/dotfiles/agent-hooks/current/claude/agent-hook"
	const windows = `C:\state\dotfiles\agent-hooks\current\codex\agent-hook.exe`
	tests := []struct{ name, harness, os, shell, binary string }{
		{"Claude shell", "claude", "linux", "sh", stable},
		{"Codex POSIX shell", "codex", "linux", "fish", stable},
		{"Codex Windows needs shell", "codex", "windows", "", windows},
		{"Codex Windows sh", "codex", "windows", "sh", windows},
		{"relative POSIX", "claude", "linux", "", strings.TrimPrefix(stable, "/")},
		{"relative Windows", "codex", "windows", "cmd", `C:state\dotfiles\agent-hooks\current\codex\agent-hook.exe`},
		{"UNC", "claude", "windows", "", `\\server\state\dotfiles\agent-hooks\current\claude\agent-hook.exe`},
		{"wrong layout", "claude", "linux", "", "/bin/agent-hook"},
		{"uppercase home", "claude", "linux", "", strings.Replace(stable, "/claude/", "/Claude/", 1)},
		{"empty home", "claude", "linux", "", strings.Replace(stable, "/claude/", "//", 1)},
		{"nested home", "claude", "linux", "", strings.Replace(stable, "/claude/", "/a/b/", 1)},
		{"wrong filename", "claude", "linux", "", stable + "-x"},
		{"POSIX exe", "claude", "linux", "", stable + ".exe"},
		{"Windows no exe", "claude", "windows", "", strings.TrimSuffix(windows, ".exe")},
		{"short release", "claude", "linux", "", "/dotfiles/agent-hooks/releases/abcdef01234/agent-hook"},
		{"uppercase release", "claude", "linux", "", "/dotfiles/agent-hooks/releases/ABCDEF012345/agent-hook"},
		{"exec placeholder", "claude", "linux", "", "/${root}" + stable},
	}
	for _, form := range []struct{ shell, chars string }{{"cmd", "%!\""}, {"powershell", "*?[]‘’‚‛"}} {
		for _, char := range form.chars {
			tests = append(tests, struct{ name, harness, os, shell, binary string }{
				form.shell + "/" + string(char), "codex", "windows", form.shell, strings.Replace(windows, "state", "state"+string(char), 1),
			})
		}
	}
	for _, os := range []string{"linux", "darwin", "windows"} {
		path := stable
		if os == "windows" {
			path = windows
		}
		for char := rune(0); char <= 0x7f; char++ {
			if char > 0x1f && char != 0x7f {
				continue
			}
			tests = append(tests, struct{ name, harness, os, shell, binary string }{
				os + "/control/" + string(char), "claude", os, "", strings.Replace(path, "state", "state"+string(char), 1),
			})
		}
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			args := []string{"--harness", test.harness, "--os", test.os, "--binary", test.binary}
			if test.shell != "" {
				args = append(args, "--shell", test.shell)
			}
			var out, report bytes.Buffer
			if exit := registration.Main(args, &out, &report); exit != 2 || out.Len() != 0 || report.Len() == 0 {
				t.Fatalf("exit %d, stdout %q, stderr %q; want 2, empty stdout and reason", exit, &out, &report)
			}
		})
	}
}

func TestMainUsageErrorsHaveNoFragment(t *testing.T) {
	base := []string{"--harness", "claude", "--os", "linux", "--binary", "/dotfiles/agent-hooks/current/claude/agent-hook"}
	for _, args := range [][]string{
		nil,
		{"--unknown"},
		{"--harness"},
		{"--os"},
		{"--binary"},
		{"--shell"},
		{"--help"},
		base[:4], base[2:], append([]string{"--harness", "agy"}, base[2:]...),
		append([]string{"--harness", "pi"}, base[2:]...), append([]string{"--harness", "absent"}, base[2:]...),
		append(append([]string{}, base...), "--os", "freebsd"), append(append([]string{}, base...), "extra"),
	} {
		var out, report bytes.Buffer
		if exit := registration.Main(args, &out, &report); exit != 64 || out.Len() != 0 || report.Len() == 0 {
			t.Errorf("%q: exit %d, stdout %q, stderr %q", args, exit, &out, &report)
		}
	}
}

func TestMainRefusesAnExplicitEmptyShell(t *testing.T) {
	for _, harness := range []string{"claude", "codex"} {
		var out, report bytes.Buffer
		exit := registration.Main([]string{"--harness", harness, "--os", "linux", "--binary", "/dotfiles/agent-hooks/current/claude/agent-hook", "--shell="}, &out, &report)
		if exit != 2 || out.Len() != 0 || report.Len() == 0 {
			t.Fatalf("%s: exit %d, stdout bytes %d, stderr %q", harness, exit, out.Len(), &report)
		}
	}
}
