package definition_test

import (
	"strings"
	"testing"
	"testing/fstest"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/definition"
)

const registrationControl = `{"events":{"pre":"PreToolUse","post":"PostToolUse"},"blocks":[
{"event":"pre","matcher":"Bash","hooks":["command-guard","files-guard","secrets-guard","rtk"]},
{"event":"post","matcher":"Write","hooks":["formatter"]}],"launchers":[
{"os":["darwin","linux","windows"],"shell":"exec","closed":{"type":"command","command":"{{.Binary}}","args":["{{.Harness}}","{{.Event}}","{{.Hook}}"]},
"open":{"type":"command","command":"{{.Binary}}","args":["{{.Harness}}","{{.Event}}","{{.Hook}}"]}}]}`

func registrationFS(t *testing.T, registration, override string) fstest.MapFS {
	t.Helper()
	support := `{"Bash":{"level":"supported"` + override + `}}`
	harness := `{"name":"h","tools":{"Bash":"shell"},"transport":"command","pathResolution":"as-given","hookCwd":"session",
"support":{"command-guard":` + support + `,"files-guard":` + support + `,"secrets-guard":` + support + `,"rtk":` + support + `,"formatter":` + support + `},
"events":{"pre":{"schema":"s.json","answers":{"pass":{"exit":0}}},"post":{"schema":"s.json","answers":{"pass":{"exit":0}}}},"registration":` + registration + `}`
	return fstest.MapFS{
		"h/harness.json": {Data: []byte(harness)},
		"h/s.json":       {Data: []byte(`{"x-ir-tool":"/tool","x-ir":{}}`)},
	}
}

func TestLoadChecksRegistration(t *testing.T) {
	if _, err := definition.Load(registrationFS(t, registrationControl, ""), "h"); err != nil {
		t.Fatalf("control: %v", err)
	}
	tests := []struct{ name, old, replacement, reason string }{
		{"unknown hook", `"command-guard"`, `"unknown"`, "hook"},
		{"missing hook", `"command-guard",`, ``, "hook"},
		{"duplicate hook", `"command-guard",`, `"command-guard","command-guard",`, "hook"},
		{"unknown event", `"event":"pre"`, `"event":"absent"`, "event"},
		{"empty matcher", `"matcher":"Bash"`, `"matcher":""`, "matcher"},
		// sync owns only a block with hooks, so an empty one would pile up.
		{"empty block", `{"event":"post","matcher":"Write","hooks":["formatter"]}`, `{"event":"post","matcher":"Write","hooks":["formatter"]},{"event":"post","matcher":"Edit","hooks":[]}`, "no hooks"},
		{"broken template", `{{.Binary}}`, `{{`, "template"},
		{"unknown function", `{{.Binary}}`, `{{unknown .Binary}}`, "template"},
		{"unknown value", `{{.Binary}}`, `{{.Absent}}`, "template"},
		{"duplicate OS shell", `"darwin","linux","windows"`, `"darwin","linux","windows","darwin"`, "launcher"},
		{"missing OS", `"darwin","linux","windows"`, `"darwin","linux"`, "launcher"},
		{"unknown OS", `"darwin","linux","windows"`, `"darwin","linux","windows","other"`, "launcher"},
		{"no launcher", `"launchers":[`, `"launchers":[],"unused":[`, "unknown"},
		{"wrong type", `"type":"command"`, `"type":"other"`, "command"},
		{"numeric command", `"command":"{{.Binary}}"`, `"command":1`, "command"},
		{"not an object", `"closed":{"type":"command","command":"{{.Binary}}","args":["{{.Harness}}","{{.Event}}","{{.Hook}}"]}`, `"closed":[]`, "object"},
		{"exec args not strings", `"args":["{{.Harness}}","{{.Event}}","{{.Hook}}"]`, `"args":[1]`, "args"},
		{"exec null argument", `"args":["{{.Harness}}","{{.Event}}","{{.Hook}}"]`, `"args":[null]`, "args"},
		{"exec no args", `,"args":["{{.Harness}}","{{.Event}}","{{.Hook}}"]`, ``, "args"},
	}
	prefix, _, found := strings.Cut(registrationControl, `"launchers":`)
	if !found {
		t.Fatal("control has no launchers")
	}
	empty := prefix + `"launchers":[]}`
	if _, err := definition.Load(registrationFS(t, empty, ""), "h"); err == nil || !strings.Contains(err.Error(), "launcher") {
		t.Fatalf("no launchers: %v", err)
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			bad := strings.Replace(registrationControl, test.old, test.replacement, 1)
			_, err := definition.Load(registrationFS(t, bad, ""), "h")
			if err == nil || !strings.Contains(err.Error(), test.reason) {
				t.Fatalf("Load = %v, want %q refusal", err, test.reason)
			}
		})
	}
	fsys := registrationFS(t, registrationControl, "")
	file := fsys["h/harness.json"]
	file.Data = []byte(strings.ReplaceAll(string(file.Data), `"level":"supported"`, `"level":"unsupported","reason":"not registered"`))
	if _, err := definition.Load(fsys, "h"); err == nil || !strings.Contains(err.Error(), "registered") {
		t.Fatalf("unregistered hooks: %v", err)
	}
}

func TestLoadChecksSupportOnOS(t *testing.T) {
	const override = `,"os":{"windows":{"level":"degraded","reason":"Windows gap"}}`
	def, err := definition.Load(registrationFS(t, registrationControl, override), "h")
	if err != nil {
		t.Fatal(err)
	}
	for os, want := range map[string]definition.OSSupport{
		"windows": {Level: "degraded", Reason: "Windows gap"},
		"linux":   {Level: "supported"},
		"other":   {Level: "supported"},
	} {
		if got := def.SupportOn("command-guard", "Bash", os); got != want {
			t.Errorf("SupportOn(%s) = %+v, want %+v", os, got, want)
		}
	}
	for _, bad := range []string{
		strings.Replace(override, "degraded", "unsupported", 1),
		strings.Replace(override, "degraded", "supported", 1),
		strings.Replace(override, "degraded", "unknown", 1),
		strings.Replace(override, "Windows gap", "", 1),
		strings.Replace(override, "windows", "freebsd", 1),
	} {
		if _, err := definition.Load(registrationFS(t, registrationControl, bad), "h"); err == nil {
			t.Errorf("accepted OS support %s", bad)
		}
	}
	if got := def.Registered("command-guard"); len(got) != 1 || got[0] != "Bash" {
		t.Fatalf("OS override changed registration: %v", got)
	}
	// An override marks a gap on one OS of a cell that is supported elsewhere.
	for _, base := range []string{`"level":"degraded","reason":"everywhere"`, `"level":"unsupported","reason":"not registered"`} {
		fsys := registrationFS(t, registrationControl, override)
		file := fsys["h/harness.json"]
		file.Data = []byte(strings.Replace(string(file.Data), `"command-guard":{"Bash":{"level":"supported"`, `"command-guard":{"Bash":{`+base, 1))
		if _, err := definition.Load(fsys, "h"); err == nil || !strings.Contains(err.Error(), "supported") {
			t.Errorf("override on a %s cell: %v", base, err)
		}
	}
}

func TestRenderIsReserved(t *testing.T) {
	_, err := definition.Load(fstest.MapFS{}, "render")
	if err == nil || !strings.Contains(err.Error(), "own command") {
		t.Fatalf("Load(render) = %v, want reserved command", err)
	}
}
