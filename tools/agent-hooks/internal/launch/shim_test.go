package launch_test

import (
	"strings"
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/fake"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/process"
)

// The shim protocol's answers, as Pi's shim reads them.
const (
	shimPass   = `{"v":1,"action":"pass"}` + "\n"
	shimBroken = `{"v":1,"action":"block","reason":"BLOCKED: agent-hook could not read the shim's request, ` +
		`so no hook ran: the shim and the binary are out of step."}` + "\n"
)

// piRequest is a request Pi's shim sends, for an event, a tool, and its input.
func piRequest(event, tool, input string) string {
	ok := ""
	if event == "post" {
		ok = `,"ok":true`
	}
	return `{"v":1,"harness":"pi","event":"` + event + `","tool":"` + tool + `","input":` + input +
		`,"cwd":"/home/user/project"` + ok + `}`
}

// brokenRequests are requests that do not follow the shim protocol, each
// made from a valid one.
func brokenRequests(valid string) map[string]string {
	return map[string]string{
		"not JSON":          valid[:len(valid)-1],
		"version 2":         strings.Replace(valid, `"v":1`, `"v":2`, 1),
		"no cwd":            strings.Replace(valid, `,"cwd":"/home/user/project"`, "", 1),
		"a relative cwd":    strings.Replace(valid, `"cwd":"/home/user/project"`, `"cwd":"project"`, 1),
		"an unknown member": strings.Replace(valid, `"cwd"`, `"toolCallId":"x","cwd"`, 1),
		"another harness":   strings.Replace(valid, `"harness":"pi"`, `"harness":"claude"`, 1),
		"empty":             "",
	}
}

func TestABrokenShimExchangeBlocksEveryPreHook(t *testing.T) {
	// The shim and the binary are out of step: no hook can trust what it
	// reads, so every pre hook blocks, rtk (which fails open) included.
	valid := piRequest("pre", "bash", `{"command":"git status"}`)
	for _, hook := range []string{"command-guard", "files-guard", "secrets-guard", "rtk"} {
		if got := run(t, &fake.Machine{}, valid, "pi", "pre", "--hook", hook); got != (result{stdout: shimPass}) {
			t.Errorf("%s, a valid request: %+v, want the pass", hook, got)
		}
		for what, payload := range brokenRequests(valid) {
			got := run(t, &fake.Machine{}, payload, "pi", "pre", "--hook", hook)
			if got.exit != 0 || got.stdout != shimBroken || !strings.Contains(got.stderr, "shim") {
				t.Errorf("%s, %s: %+v, want the broken-exchange block and why on stderr", hook, what, got)
			}
		}
		// A request for the other event is broken too.
		post := piRequest("post", "bash", `{"command":"git status"}`)
		if got := run(t, &fake.Machine{}, post, "pi", "pre", "--hook", hook); got.stdout != shimBroken {
			t.Errorf("%s, a post request: %+v, want the broken-exchange block", hook, got)
		}
	}
}

func TestABrokenShimExchangeRunsNoPostHook(t *testing.T) {
	// After the tool there is nothing to block: the formatter runs nothing
	// and passes. The machine would format the file if it ran.
	valid := piRequest("post", "write", `{"path":"/home/user/project/a.go","content":"package a\n"}`)
	for what, payload := range brokenRequests(valid) {
		m := &fake.Machine{
			Programs:  map[string]process.Program{"gofmt": {Path: "/b/gofmt"}},
			Files:     map[string]bool{"/home/user/project/a.go": true},
			RealPaths: map[string]string{"/home/user/project/a.go": "/home/user/project/a.go", "/home/user/project": "/home/user/project"},
			Cwd:       "/home/user/project",
		}
		got := run(t, m, payload, "pi", "post", "--hook", "formatter")
		if got.exit != 0 || got.stdout != shimPass {
			t.Errorf("%s: %+v, want the pass", what, got)
		}
		checkReplay(t, m)
	}
}
