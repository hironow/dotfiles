package definition_test

import (
	"io/fs"
	"path"
	"strings"
	"testing"
	"testing/fstest"

	json "github.com/goccy/go-json/v2"

	"github.com/hironow/dotfiles/tools/agent-hooks/harnesses"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/definition"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
)

// shimAnswers are a shim harness's pre answers, in the shim protocol.
const shimAnswers = `{"pass":{"exit":0,"stdoutJSON":{"v":1,"action":"pass"}},` +
	`"block":{"exit":0,"stdoutJSON":{"v":1,"action":"block","reason":"{{.Message}}"}}}`

// shimPostAnswers are a shim harness's post answers, in the shim protocol.
const shimPostAnswers = `{"pass":{"exit":0,"stdoutJSON":{"v":1,"action":"pass"},"stderr":"{{.Notice}}"}}`

// shimHarness is a harness "s" reached through a shim (or as a command, for
// the control), with these pre and post answers.
func shimHarness(transport, preAnswers, postAnswers string) fstest.MapFS {
	return fstest.MapFS{
		"s/harness.json": {Data: []byte(`{"name":"s","versions":["1"],"tools":{"bash":"shell"},` +
			`"transport":"` + transport + `","pathResolution":"as-given","hookCwd":"session","events":{` +
			`"pre":{"schema":"pre.schema.json","answers":` + preAnswers + `},` +
			`"post":{"schema":"post.schema.json","answers":` + postAnswers + `}}}`)},
		"s/pre.schema.json":  {Data: []byte(`{"x-ir-tool":"/tool","x-ir":{}}`)},
		"s/post.schema.json": {Data: []byte(`{"x-ir-tool":"/tool","x-ir":{}}`)},
	}
}

func shimEvents(t *testing.T) (pre, post definition.Event) {
	t.Helper()
	def, err := definition.Load(shimHarness("shim", shimAnswers, shimPostAnswers), "s")
	if err != nil {
		t.Fatalf("Load = %v", err)
	}
	pre, _ = def.Event("pre")
	post, _ = def.Event("post")
	return pre, post
}

func request(t *testing.T, edit func(map[string]any)) []byte {
	t.Helper()
	members := map[string]any{
		"v": 1, "harness": "s", "event": "pre", "tool": "bash",
		"input": map[string]any{"command": "ls"}, "cwd": "/w",
	}
	edit(members)
	out, err := json.Marshal(members)
	if err != nil {
		t.Fatal(err)
	}
	return out
}

func TestAShimRequestFollowsTheProtocol(t *testing.T) {
	pre, post := shimEvents(t)
	asPost := func(m map[string]any) { m["event"], m["ok"] = "post", true }
	valid := map[string][]byte{
		"pre":                     request(t, func(map[string]any) {}),
		"pre with a context":      request(t, func(m map[string]any) { m["context"] = map[string]any{"agent": "a"} }),
		"pre with an empty input": request(t, func(m map[string]any) { m["input"] = map[string]any{} }),
	}
	for what, payload := range valid {
		if err := pre.CheckShimRequest(payload); err != nil {
			t.Errorf("%s: CheckShimRequest = %v, want nil", what, err)
		}
	}
	for _, ok := range []bool{true, false} {
		payload := request(t, func(m map[string]any) { asPost(m); m["ok"] = ok })
		if err := post.CheckShimRequest(payload); err != nil {
			t.Errorf("post, ok %v: CheckShimRequest = %v, want nil", ok, err)
		}
	}
	brokenPre := map[string][]byte{
		"not JSON":                  []byte(`{"v":1`),
		"two JSON values":           append(request(t, func(map[string]any) {}), []byte(` {}`)...),
		"a duplicate member":        []byte(`{"v":1,"v":1,"harness":"s","event":"pre","tool":"bash","input":{},"cwd":"/w"}`),
		"invalid UTF-8":             []byte("{\"v\":1,\"harness\":\"s\",\"event\":\"pre\",\"tool\":\"b\xffsh\",\"input\":{},\"cwd\":\"/w\"}"),
		"an array":                  []byte(`[]`),
		"version 2":                 request(t, func(m map[string]any) { m["v"] = 2 }),
		"the version as a string":   request(t, func(m map[string]any) { m["v"] = "1" }),
		"no version":                request(t, func(m map[string]any) { delete(m, "v") }),
		"no cwd":                    request(t, func(m map[string]any) { delete(m, "cwd") }),
		"a relative cwd":            request(t, func(m map[string]any) { m["cwd"] = "w" }),
		"no tool":                   request(t, func(m map[string]any) { delete(m, "tool") }),
		"an empty tool name":        request(t, func(m map[string]any) { m["tool"] = "" }),
		"no input":                  request(t, func(m map[string]any) { delete(m, "input") }),
		"an input that is a string": request(t, func(m map[string]any) { m["input"] = "ls" }),
		"an unknown member":         request(t, func(m map[string]any) { m["id"] = "x" }),
		"a context that is a list":  request(t, func(m map[string]any) { m["context"] = []any{} }),
		"ok before the tool ran":    request(t, func(m map[string]any) { m["ok"] = true }),
		"another harness":           request(t, func(m map[string]any) { m["harness"] = "pi" }),
		"the post event":            request(t, asPost),
	}
	for what, payload := range brokenPre {
		if err := pre.CheckShimRequest(payload); err == nil {
			t.Errorf("pre, %s: CheckShimRequest = nil, want an error", what)
		}
	}
	brokenPost := map[string][]byte{
		"no ok":             request(t, func(m map[string]any) { asPost(m); delete(m, "ok") }),
		"ok as a string":    request(t, func(m map[string]any) { asPost(m); m["ok"] = "true" }),
		"the pre event":     request(t, func(map[string]any) {}),
		"another harness":   request(t, func(m map[string]any) { asPost(m); m["harness"] = "pi" }),
		"an unknown member": request(t, func(m map[string]any) { asPost(m); m["isError"] = false }),
	}
	for what, payload := range brokenPost {
		if err := post.CheckShimRequest(payload); err == nil {
			t.Errorf("post, %s: CheckShimRequest = nil, want an error", what)
		}
	}
}

func TestACommandHarnessIsNotCheckedAsAShim(t *testing.T) {
	// A command harness sends its own payload, which no shim wrote.
	for _, name := range names {
		if loadDefinition(t, name).Transport != ir.TransportCommand {
			continue
		}
		for _, event := range events {
			if err := loadEvent(t, name, event).CheckShimRequest([]byte(`not JSON`)); err != nil {
				t.Errorf("%s %s: CheckShimRequest = %v, want nil", name, event, err)
			}
		}
	}
}

func TestLoadRejectsAShimAnswerOutsideTheProtocol(t *testing.T) {
	answers := func(edit func(map[string]string)) string {
		pre := map[string]string{
			"pass":  `{"exit":0,"stdoutJSON":{"v":1,"action":"pass"}}`,
			"block": `{"exit":0,"stdoutJSON":{"v":1,"action":"block","reason":"{{.Message}}"}}`,
		}
		edit(pre)
		return `{"pass":` + pre["pass"] + `,"block":` + pre["block"] + `}`
	}
	bad := map[string]string{
		"version 2":              answers(func(a map[string]string) { a["pass"] = `{"exit":0,"stdoutJSON":{"v":2,"action":"pass"}}` }),
		"an unknown action":      answers(func(a map[string]string) { a["pass"] = `{"exit":0,"stdoutJSON":{"v":1,"action":"allow"}}` }),
		"a block with no reason": answers(func(a map[string]string) { a["block"] = `{"exit":0,"stdoutJSON":{"v":1,"action":"block"}}` }),
		"a blank reason": answers(func(a map[string]string) {
			a["block"] = `{"exit":0,"stdoutJSON":{"v":1,"action":"block","reason":" {{if false}}{{.Message}}{{end}}"}}`
		}),
		"an unknown member": answers(func(a map[string]string) {
			a["pass"] = `{"exit":0,"stdoutJSON":{"v":1,"action":"pass","decision":"ask"}}`
		}),
		"set without a rewrite": answers(func(a map[string]string) {
			a["pass"] = `{"exit":0,"stdoutJSON":{"v":1,"action":"pass","set":{"command":"x"}}}`
		}),
		"text that is not JSON": answers(func(a map[string]string) { a["pass"] = `{"exit":0,"stdout":"ok"}` }),
		"a non-zero exit":       answers(func(a map[string]string) { a["pass"] = `{"exit":2,"stdoutJSON":{"v":1,"action":"pass"}}` }),
	}
	if _, err := definition.Load(shimHarness("shim", shimAnswers, shimPostAnswers), "s"); err != nil {
		t.Fatalf("the control: Load = %v, want it loaded", err)
	}
	for what, pre := range bad {
		if _, err := definition.Load(shimHarness("shim", pre, shimPostAnswers), "s"); err == nil {
			t.Errorf("pre, %s: Load = nil, want an error", what)
		}
		// The protocol binds a shim harness only.
		if _, err := definition.Load(shimHarness("command", pre, shimPostAnswers), "s"); err != nil {
			t.Errorf("pre, %s, as a command harness: Load = %v, want it loaded", what, err)
		}
	}
	post := `{"pass":{"exit":0,"stdoutJSON":{"v":1,"action":"pass","reason":""},"stderr":"{{.Notice}}"}}`
	if _, err := definition.Load(shimHarness("shim", shimAnswers, post), "s"); err == nil {
		t.Error("post, a blank reason: Load = nil, want an error")
	}
}

func TestEveryShimFixtureIsAShimRequest(t *testing.T) {
	// The fixtures of a harness reached through a shim are the requests the
	// shim sends: each follows the protocol, for its event.
	shims := 0
	for _, name := range names {
		if loadDefinition(t, name).Transport != ir.TransportShim {
			continue
		}
		shims++
		entries, err := fs.ReadDir(harnesses.FS, path.Join(name, "fixtures"))
		if err != nil {
			t.Fatal(err)
		}
		for _, entry := range entries {
			if strings.HasSuffix(entry.Name(), ".ir.json") {
				continue
			}
			event, _, _ := strings.Cut(entry.Name(), "-")
			payload := read(t, path.Join(name, "fixtures", entry.Name()))
			if err := loadEvent(t, name, event).CheckShimRequest(payload); err != nil {
				t.Errorf("%s %s: CheckShimRequest = %v", name, entry.Name(), err)
			}
		}
	}
	if shims == 0 {
		t.Error("no harness is reached through a shim")
	}
}
