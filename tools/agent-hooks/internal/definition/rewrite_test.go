package definition_test

import (
	"strings"
	"testing"

	json "github.com/goccy/go-json/v2"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/definition"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
)

// rewriteTo is a rewrite of the command.
func rewriteTo(command string) ir.Outcome {
	return ir.Outcome{Action: ir.Rewrite, Set: ir.Assignment{Field: ir.FieldCommand, Value: command}}
}

func TestAnswerRendersPisRewrite(t *testing.T) {
	// The shim protocol's rewrite: the shim sets each field of set in place.
	got, err := load(t, "pi").Answer(rewriteTo(`rtk git "status"`))
	want := definition.Answer{Stdout: `{"v":1,"action":"rewrite","set":{"command":"rtk git \"status\""}}` + "\n"}
	if err != nil || got != want {
		t.Errorf("Answer = %+v, %v; want %+v", got, err, want)
	}
}

func TestOnlyAHarnessWithARewriteAnswerCanBeAnsweredARewrite(t *testing.T) {
	// rtk on Claude and Codex is a delegate whose answer is forwarded; no hook
	// makes a rewrite of its own for them, nor for agy.
	for _, name := range []string{"claude", "codex", "agy"} {
		if got, err := load(t, name).Answer(rewriteTo("x")); err == nil {
			t.Errorf("%s: Answer = %+v, want no rewrite answer", name, got)
		}
	}
}

// piBash is Pi's bash request with members edited.
func piBash(t *testing.T, edit func(request map[string]any)) []byte {
	t.Helper()
	var request map[string]any
	if err := json.Unmarshal(read(t, "pi/fixtures/pre-bash.json"), &request); err != nil {
		t.Fatal(err)
	}
	edit(request)
	out, err := json.Marshal(request)
	if err != nil {
		t.Fatal(err)
	}
	return out
}

func TestRewriteWritesTheValueWhereTheDefinitionMapsItsField(t *testing.T) {
	pre := load(t, "pi")
	payload := piBash(t, func(r map[string]any) {
		r["input"] = map[string]any{"command": "git status", "timeout": 30}
	})
	merged, err := pre.Rewrite(payload, ir.Assignment{Field: ir.FieldCommand, Value: "rtk git status"})
	if err != nil {
		t.Fatalf("Rewrite: %v", err)
	}
	var got struct {
		Input map[string]any `json:"input"`
		Cwd   string         `json:"cwd"`
	}
	if err := json.Unmarshal(merged, &got); err != nil {
		t.Fatal(err)
	}
	// The command changes; every other member stays.
	if got.Input["command"] != "rtk git status" || got.Input["timeout"] != float64(30) || got.Cwd != "/home/user/project" {
		t.Errorf("merged = %s", merged)
	}
	// A command that was null is replaced as well.
	null := piBash(t, func(r map[string]any) { r["input"] = map[string]any{"command": nil} })
	if _, err := pre.Rewrite(null, ir.Assignment{Field: ir.FieldCommand, Value: "x"}); err != nil {
		t.Errorf("a null command: Rewrite = %v, want nil", err)
	}
}

func TestRewriteRefusesWhatItCannotWriteOrValidate(t *testing.T) {
	pre := load(t, "pi")
	bash := piBash(t, func(map[string]any) {})
	tests := map[string]struct {
		payload []byte
		set     ir.Assignment
	}{
		"a field the definition does not map": {bash, ir.Assignment{Field: "noSuchField", Value: "x"}},
		"a list field":                        {bash, ir.Assignment{Field: ir.ListContents, Value: "x"}},
		"a pointer through a string":          {piBash(t, func(r map[string]any) { r["input"] = "git status" }), ir.Assignment{Field: ir.FieldCommand, Value: "x"}},
		"a pointer through a missing object":  {piBash(t, func(r map[string]any) { delete(r, "input") }), ir.Assignment{Field: ir.FieldCommand, Value: "x"}},
		"a result outside the schema":         {piBash(t, func(r map[string]any) { delete(r, "cwd") }), ir.Assignment{Field: ir.FieldCommand, Value: "x"}},
		"a payload that is not JSON":          {[]byte(`{"v":1`), ir.Assignment{Field: ir.FieldCommand, Value: "x"}},
	}
	for what, test := range tests {
		if merged, err := pre.Rewrite(test.payload, test.set); err == nil {
			t.Errorf("%s: Rewrite = %s, nil; want an error", what, merged)
		}
	}
}

func TestLoadRejectsAShimRewriteAnswerOutsideTheProtocol(t *testing.T) {
	answers := func(rewrite string) string {
		return strings.TrimSuffix(shimAnswers, "}") + `,"rewrite":` + rewrite + `}`
	}
	good := `{"exit":0,"stdoutJSON":{"v":1,"action":"rewrite","set":{"command":"{{.Set.command}}"}}}`
	if _, err := definition.Load(shimHarness("shim", answers(good), shimPostAnswers), "s"); err != nil {
		t.Fatalf("the control: Load = %v, want it loaded", err)
	}
	for what, rewrite := range map[string]string{
		"no set":          `{"exit":0,"stdoutJSON":{"v":1,"action":"rewrite"}}`,
		"another field":   `{"exit":0,"stdoutJSON":{"v":1,"action":"rewrite","set":{"cwd":"{{.Set.command}}"}}}`,
		"a pass in place": `{"exit":0,"stdoutJSON":{"v":1,"action":"pass","set":{"command":"{{.Set.command}}"}}}`,
	} {
		if _, err := definition.Load(shimHarness("shim", answers(rewrite), shimPostAnswers), "s"); err == nil {
			t.Errorf("%s: Load = nil, want an error", what)
		}
	}
}
