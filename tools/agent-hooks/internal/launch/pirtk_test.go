package launch_test

import (
	"testing"
	"time"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/fake"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/process"
)

// piRewrite is Pi's rewrite answer for a command.
func piRewrite(command string) string {
	return `{"v":1,"action":"rewrite","set":{"command":"` + command + `"}}` + "\n"
}

// rtkRewrite is the invocation of `rtk rewrite` for a command, and what it
// answers.
func rtkRewrite(command string, result process.Result) fake.Invocation {
	return fake.Invocation{
		Command: process.Command{Path: "/b/rtk", Args: []string{"rtk", "rewrite", command}, Timeout: 2 * time.Second},
		Result:  result,
	}
}

func TestPiRTKAnswersRtksRewrite(t *testing.T) {
	// Pi's rtk is rtk.ts's: `rtk rewrite <command>` on exit 0 or 3, its
	// stdout trimmed as JavaScript trims it.
	bash := func(command string) string { return piRequest("pre", "bash", `{"command":"`+command+`","timeout":5}`) }
	tests := []struct {
		name    string
		machine *fake.Machine
		command string
		want    string
	}{
		{
			"a rewrite",
			&fake.Machine{
				Programs: map[string]process.Program{"rtk": {Path: "/b/rtk"}},
				Replay:   []fake.Invocation{rtkRewrite("git status", process.Result{Stdout: []byte("rtk git status\n")})},
			},
			"git status", piRewrite("rtk git status"),
		},
		{
			"an advisory rewrite",
			&fake.Machine{
				Programs: map[string]process.Program{"rtk": {Path: "/b/rtk"}},
				Replay:   []fake.Invocation{rtkRewrite("git status", process.Result{Stdout: []byte(" rtk git status "), Exit: 3})},
			},
			"git status", piRewrite("rtk git status"),
		},
		{
			"no rtk equivalent",
			&fake.Machine{
				Programs: map[string]process.Program{"rtk": {Path: "/b/rtk"}},
				Replay:   []fake.Invocation{rtkRewrite("echo hi", process.Result{Exit: 1})},
			},
			"echo hi", shimPass,
		},
		{
			"a signal after printing (rtk-signal)",
			&fake.Machine{
				Programs: map[string]process.Program{"rtk": {Path: "/b/rtk"}},
				Replay:   []fake.Invocation{rtkRewrite("git status", process.Result{Stdout: []byte("rtk git status"), Exit: -1, Signaled: true})},
			},
			"git status", shimPass,
		},
		{
			"a timeout",
			&fake.Machine{
				Programs: map[string]process.Program{"rtk": {Path: "/b/rtk"}},
				Replay:   []fake.Invocation{{Command: rtkRewrite("git status", process.Result{}).Command, Failed: true}},
			},
			"git status", shimPass,
		},
		{"no rtk", &fake.Machine{}, "git status", shimPass},
		{
			"rtk through a relative PATH entry (path-relative)",
			&fake.Machine{Programs: map[string]process.Program{"rtk": {Path: "bin/rtk", Relative: true}}},
			"git status", shimPass,
		},
		{
			"a command rtk already runs",
			&fake.Machine{Programs: map[string]process.Program{"rtk": {Path: "/b/rtk"}}},
			"rtk git status", shimPass,
		},
		{
			"RTK_DISABLED=1",
			&fake.Machine{Programs: map[string]process.Program{"rtk": {Path: "/b/rtk"}}, Env: map[string]string{"RTK_DISABLED": "1"}},
			"git status", shimPass,
		},
		{
			"RTK_DISABLED=0",
			&fake.Machine{
				Programs: map[string]process.Program{"rtk": {Path: "/b/rtk"}},
				Env:      map[string]string{"RTK_DISABLED": "0"},
				Replay:   []fake.Invocation{rtkRewrite("git status", process.Result{Stdout: []byte("rtk git status\n")})},
			},
			"git status", piRewrite("rtk git status"),
		},
	}
	for _, test := range tests {
		got := run(t, test.machine, bash(test.command), "pi", "pre", "--hook", "rtk")
		if got != (result{stdout: test.want}) {
			t.Errorf("%s: %+v, want stdout %q", test.name, got, test.want)
		}
		checkReplay(t, test.machine)
	}
}

func TestPiRTKLeavesEveryOtherTool(t *testing.T) {
	// rtk.ts acts on bash only; a write whose content looks like a command is
	// left alone.
	m := &fake.Machine{Programs: map[string]process.Program{"rtk": {Path: "/b/rtk"}}}
	for _, input := range []string{
		`{"path":"a.md","content":"git status"}`,
		// Pi's tools allow members of their own; a command beside a write is
		// still no bash command.
		`{"path":"a.md","content":"x","command":"git status"}`,
	} {
		if got := run(t, m, piRequest("pre", "write", input), "pi", "pre", "--hook", "rtk"); got != (result{stdout: shimPass}) {
			t.Errorf("a write %s: %+v, want the pass", input, got)
		}
	}
	checkReplay(t, m)
}
