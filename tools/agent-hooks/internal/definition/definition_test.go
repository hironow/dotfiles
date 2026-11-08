package definition_test

import (
	"errors"
	"io/fs"
	"maps"
	"path"
	"slices"
	"strings"
	"testing"
	"testing/fstest"

	json "github.com/goccy/go-json/v2"

	"github.com/hironow/dotfiles/tools/agent-hooks/harnesses"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/definition"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
)

// The harnesses defined so far.
var names = []string{"claude", "codex", "agy", "pi"}

// events are the events every harness here defines.
var events = []string{"pre", "post"}

func load(t *testing.T, name string) definition.Event {
	t.Helper()
	return loadEvent(t, name, "pre")
}

func loadEvent(t *testing.T, name, event string) definition.Event {
	t.Helper()
	def, err := definition.Load(harnesses.FS, name)
	if err != nil {
		t.Fatalf("Load(%q): %v", name, err)
	}
	loaded, ok := def.Event(event)
	if !ok {
		t.Fatalf("%s: no %s event", name, event)
	}
	return loaded
}

func TestEveryHarnessMapsTheFieldsItsHooksRead(t *testing.T) {
	// The old scripts read these fields whatever the harness, the event, and
	// the tool; the rtk hook reads the payload's cwd.
	scripts := map[string][]string{
		ir.FieldCommand:  {"/tool_input/command"},
		ir.FieldFilePath: {"/tool_input/file_path"},
		ir.FieldContent:  {"/tool_input/content", "/tool_input/new_string", "/tool_input/new_source"},
		ir.FieldCwd:      {"/cwd"},
		// fixed-notebook-path: the old files guard never read it.
		ir.FieldNotebookPath: {"/tool_input/notebook_path"},
	}
	// agy's tools name their arguments themselves (run_command CommandLine,
	// write_file Path and Content, edit_file Path and Replacement), and each
	// call names its workspaces.
	agy := map[string][]string{
		ir.FieldCommand:   {"/toolCall/args/CommandLine"},
		ir.FieldFilePath:  {"/toolCall/args/Path"},
		ir.FieldContent:   {"/toolCall/args/Content", "/toolCall/args/Replacement"},
		ir.ListWorkspaces: {"/workspacePaths/*"},
	}
	// Pi's shim sends the tool's input as Pi hands it to its extensions:
	// bash command, write path and content, edit path and each replacement's
	// newText; and the cwd Pi resolves the path against.
	pi := map[string][]string{
		ir.FieldCommand:  {"/input/command"},
		ir.FieldFilePath: {"/input/path"},
		ir.FieldContent:  {"/input/content"},
		ir.ListContents:  {"/input/edits/*/newText"},
		ir.FieldCwd:      {"/cwd"},
	}
	// The log hashes the session's and the call's ids into a trace id, so
	// that a call's pre and post lines share it. Pi's shim sends none yet.
	claudeIDs := map[string][]string{ir.FieldSessionID: {"/session_id"}, ir.FieldCallID: {"/tool_use_id"}}
	agyIDs := map[string][]string{ir.FieldSessionID: {"/conversationId"}, ir.FieldCallID: {"/stepIdx"}}
	with := func(fields, ids map[string][]string) map[string][]string {
		joined := maps.Clone(fields)
		maps.Copy(joined, ids)
		return joined
	}
	want := map[string]map[string][]string{
		"claude": with(scripts, claudeIDs), "codex": with(scripts, claudeIDs), "agy": with(agy, agyIDs), "pi": pi,
	}
	for _, name := range names {
		for _, event := range events {
			t.Run(name+"/"+event, func(t *testing.T) {
				if got := loadEvent(t, name, event).IR; !maps.EqualFunc(got, want[name], slices.Equal) {
					t.Errorf("x-ir = %v, want %v", got, want[name])
				}
			})
		}
	}
}

func TestEveryHarnessRegistersItsHooksForTodaysTools(t *testing.T) {
	// The tools each hook is registered for (supported or degraded) are the
	// matchers of today's registrations: .claude/settings.hooks.json for
	// Claude, the same blocks for Codex under Codex's names, and agy's plugin
	// (PR 4) for the tools seen in its payloads.
	want := map[string]map[string][]string{
		"claude": {
			"command-guard": {"Bash"},
			"files-guard":   {"Edit", "NotebookEdit", "Write"},
			"secrets-guard": {"Edit", "NotebookEdit", "Write"},
			"rtk":           {"Bash"},
			"formatter":     {"Edit", "Write"},
		},
		"codex": {
			"command-guard": {"Bash"},
			"files-guard":   {"apply_patch"},
			"secrets-guard": {"apply_patch"},
			"rtk":           {"Bash"},
			"formatter":     {"apply_patch"},
		},
		"agy": {
			"command-guard": {"run_command"},
			"files-guard":   {"edit_file", "write_file"},
			"secrets-guard": {"edit_file", "write_file"},
			"rtk":           nil,
			"formatter":     {"edit_file", "write_file"},
		},
		// Pi's tools, as the vendored extensions (config/pi/extensions) and the
		// shim (PR 4) see them.
		"pi": {
			"command-guard": {"bash"},
			"files-guard":   {"edit", "write"},
			"secrets-guard": {"edit", "write"},
			"rtk":           {"bash"},
			"formatter":     {"edit", "write"},
		},
	}
	for _, name := range names {
		def := loadDefinition(t, name)
		for hook, tools := range want[name] {
			if got := def.Registered(hook); !slices.Equal(got, tools) {
				t.Errorf("%s %s: registered for %v, want %v", name, hook, got, tools)
			}
		}
		if len(def.Support) != len(want[name]) {
			t.Errorf("%s: support names hooks %v, want %v", name, slices.Sorted(maps.Keys(def.Support)),
				slices.Sorted(maps.Keys(want[name])))
		}
	}
}

func TestEveryKnownGapIsDegradedOrUnsupportedWithItsReason(t *testing.T) {
	// Every other cell is supported.
	gaps := map[[3]string]string{
		// agy's sandbox cannot run rtk, and agy checks its permission rules
		// against the rewritten command.
		{"agy", "rtk", "run_command"}: definition.LevelUnsupported,
	}
	for _, name := range names {
		def := loadDefinition(t, name)
		for hook, tools := range def.Support {
			for tool, support := range tools {
				want, gap := gaps[[3]string{name, hook, tool}]
				if !gap {
					want = definition.LevelSupported
				}
				if support.Level != want || (gap && support.Reason == "") {
					t.Errorf("%s %s %s: %+v, want level %s (with a reason: %v)", name, hook, tool, support, want, gap)
				}
			}
		}
	}
}

func TestEveryHarnessSaysWhereItRunsItsHooks(t *testing.T) {
	// Claude and Codex run a hook in the session's directory, which the old
	// scripts relied on; agy runs it in the directory holding hooks.json.
	want := map[string]string{
		"claude": ir.HookCwdSession,
		"codex":  ir.HookCwdSession,
		"agy":    ir.HookCwdRegistration,
		// The shim runs the binary in the call's cwd (its contract, PR 4).
		"pi": ir.HookCwdSession,
	}
	for _, name := range names {
		if got := loadDefinition(t, name).HookCwd; got != want[name] {
			t.Errorf("%s: hookCwd %q, want %q", name, got, want[name])
		}
	}
}

func TestEveryHarnessSaysHowItIsReachedAndHowItNamesFiles(t *testing.T) {
	// Claude, Codex, and agy run the binary as a command, and write a tool's
	// path as given. Every call the definition decodes carries both.
	want := map[string][2]string{
		"claude": {ir.TransportCommand, ir.PathsAsGiven},
		"codex":  {ir.TransportCommand, ir.PathsAsGiven},
		"agy":    {ir.TransportCommand, ir.PathsAsGiven},
		// Pi reaches the binary through its shim, and resolves a tool's path
		// against its cwd before it writes (internal/pipath).
		"pi": {ir.TransportShim, ir.PathsPi},
	}
	for _, name := range names {
		def := loadDefinition(t, name)
		if got := [2]string{def.Transport, def.PathResolution}; got != want[name] {
			t.Errorf("%s: transport and path resolution %q, want %q", name, got, want[name])
		}
		for _, event := range events {
			call, err := loadEvent(t, name, event).Decode([]byte(`{}`))
			if err != nil {
				t.Fatal(err)
			}
			if got := [2]string{call.Transport, call.PathResolution}; got != want[name] {
				t.Errorf("%s %s: the call's transport and path resolution %q, want %q", name, event, got, want[name])
			}
		}
	}
}

func TestAgyListsTheToolsItsDocsNameButNoPayloadShowed(t *testing.T) {
	want := []string{"multi_replace_file_content", "replace_file_content", "write_to_file"}
	if got := loadDefinition(t, "agy").Pending; !slices.Equal(slices.Sorted(slices.Values(got)), want) {
		t.Errorf("pending = %v, want %v", got, want)
	}
}

func TestPiListsTheToolsItsDocsNameButNoPayloadShowed(t *testing.T) {
	if got := loadDefinition(t, "pi").Pending; !slices.Equal(got, []string{"powershell"}) {
		t.Errorf("pending = %v, want [powershell]", got)
	}
}

func TestDecodeReadsPisSuccessSignal(t *testing.T) {
	// The shim sends ok: whether the tool call succeeded (Pi's !isError).
	post := loadEvent(t, "pi", "post")
	for payload, failed := range map[string]bool{
		`{"ok":true}`:  false,
		`{"ok":false}`: true,
		`{"ok":null}`:  true,
		`{"ok":"yes"}`: true,
		`{}`:           true,
	} {
		got, err := post.Decode([]byte(payload))
		if err != nil {
			t.Fatal(err)
		}
		if got.ToolFailed != failed {
			t.Errorf("Decode(%s): tool failed %v, want %v", payload, got.ToolFailed, failed)
		}
	}
}

func TestLoadRejectsSupportItCannotUse(t *testing.T) {
	const known = `"transport":"command","pathResolution":"as-given",`
	harness := func(extra string) []byte {
		return []byte(`{"name":"h","versions":["1"],"tools":{"T":"shell"},` + extra +
			`"events":{"pre":{"schema":"pre.schema.json","answers":{"pass":{"exit":0}}}}}`)
	}
	tests := map[string]string{
		"an unknown level":                    known + `"hookCwd":"session","support":{"x":{"T":{"level":"maybe"}}},`,
		"a degraded level with no reason":     known + `"hookCwd":"session","support":{"x":{"T":{"level":"degraded"}}},`,
		"an unsupported level with no reason": known + `"hookCwd":"session","support":{"x":{"T":{"level":"unsupported"}}},`,
		"a tool the harness does not map":     known + `"hookCwd":"session","support":{"x":{"U":{"level":"supported"}}},`,
		"a pending tool that is mapped":       known + `"hookCwd":"session","pending":["T"],`,
		"an unknown hook directory":           known + `"hookCwd":"plugin",`,
		"no hook directory":                   known,
		"an unknown transport":                `"transport":"socket","pathResolution":"as-given","hookCwd":"session",`,
		"no transport":                        `"pathResolution":"as-given","hookCwd":"session",`,
		"an unknown path resolution":          `"transport":"command","pathResolution":"lines","hookCwd":"session",`,
		"no path resolution":                  `"transport":"command","hookCwd":"session",`,
	}
	control := known + `"hookCwd":"registration","pending":["U"],"support":{"x":{"T":{"level":"degraded","reason":"r"}}},`
	if _, err := definition.Load(fstest.MapFS{
		"h/harness.json":    {Data: harness(control)},
		"h/pre.schema.json": {Data: []byte(`{"x-ir-tool":"/tool","x-ir":{}}`)},
	}, "h"); err != nil {
		t.Fatalf("the control: Load = %v, want it loaded", err)
	}
	for what, extra := range tests {
		_, err := definition.Load(fstest.MapFS{
			"h/harness.json":    {Data: harness(extra)},
			"h/pre.schema.json": {Data: []byte(`{"x-ir-tool":"/tool","x-ir":{}}`)},
		}, "h")
		if err == nil {
			t.Errorf("%s: Load = nil, want an error", what)
		}
	}
}

func loadDefinition(t *testing.T, name string) definition.Definition {
	t.Helper()
	def, err := definition.Load(harnesses.FS, name)
	if err != nil {
		t.Fatalf("Load(%q): %v", name, err)
	}
	return def
}

func TestEverySchemaNamesWhereItsToolNameIs(t *testing.T) {
	want := map[string]string{"claude": "/tool_name", "codex": "/tool_name", "agy": "/toolCall/name", "pi": "/tool"}
	for _, name := range names {
		for _, event := range events {
			loaded := loadEvent(t, name, event)
			if loaded.Tool != want[name] {
				t.Errorf("%s %s: x-ir-tool = %q, want %q", name, event, loaded.Tool, want[name])
			}
			if !loaded.Declares(loaded.Tool) {
				t.Errorf("%s %s: the schema does not declare its tool pointer %q", name, event, loaded.Tool)
			}
		}
	}
}

func TestEveryIRPointerIsDeclaredInItsSchema(t *testing.T) {
	// Except those listed as undeclared: Codex never sends file_path or
	// content, but the old guards read them for every harness.
	wantUndeclared := map[string][]string{
		"claude": nil,
		"codex": {
			"/tool_input/file_path", "/tool_input/content", "/tool_input/new_string", "/tool_input/new_source",
			"/tool_input/notebook_path",
		},
		"agy": nil,
		"pi":  nil,
	}
	for _, name := range names {
		for _, event := range events {
			loaded := loadEvent(t, name, event)
			if !slices.Equal(loaded.Undeclared, wantUndeclared[name]) {
				t.Errorf("%s %s: undeclared = %v, want %v", name, event, loaded.Undeclared, wantUndeclared[name])
			}
			for field, pointers := range loaded.IR {
				for _, pointer := range pointers {
					undeclared := slices.Contains(loaded.Undeclared, pointer)
					if declared := loaded.Declares(pointer); declared == undeclared {
						t.Errorf("%s %s: %s pointer %s: declared %v, listed as undeclared %v",
							name, event, field, pointer, declared, undeclared)
					}
				}
			}
			for _, pointer := range loaded.Undeclared {
				if !slices.ContainsFunc(slices.Collect(maps.Values(loaded.IR)), func(p []string) bool {
					return slices.Contains(p, pointer)
				}) {
					t.Errorf("%s %s: undeclared pointer %s is not in x-ir", name, event, pointer)
				}
			}
		}
	}
}

func TestDeclaresIsFalseForAPointerTheSchemaLacks(t *testing.T) {
	pre := load(t, "claude")
	for _, pointer := range []string{"/tool_input/no_such_field", "/no_such_member", "/tool_input/command/deeper"} {
		if pre.Declares(pointer) {
			t.Errorf("Declares(%q) = true, want false", pointer)
		}
	}
	// "*" is declared by an array's items, not by an object's members.
	agy := load(t, "agy")
	for _, pointer := range []string{"/toolCall/*", "/workspacePaths/*/x", "/stepIdx/*"} {
		if agy.Declares(pointer) {
			t.Errorf("agy: Declares(%q) = true, want false", pointer)
		}
	}
	if !agy.Declares("/workspacePaths/*") {
		t.Error(`agy: Declares("/workspacePaths/*") = false, want true`)
	}
}

// expectedCall is a fixture's hand-written IR.
type expectedCall struct {
	Tool       string                     `json:"tool"`
	Kind       string                     `json:"kind"`
	Fields     map[string]expectedValue   `json:"fields"`
	Lists      map[string][]expectedValue `json:"lists"`
	ToolFailed bool                       `json:"toolFailed"`
}

type expectedValue struct {
	String *string `json:"string"`
	JSON   *string `json:"json"`
}

func (e expectedValue) value() ir.Value {
	if e.String != nil {
		return ir.Value{Text: *e.String, IsString: true}
	}
	return ir.Value{Text: *e.JSON}
}

func TestEveryFixtureValidatesAndDecodesToItsIR(t *testing.T) {
	// A fixture's name starts with its event: pre-bash.json, post-write.json.
	for _, name := range names {
		dir := path.Join(name, "fixtures")
		entries, err := fs.ReadDir(harnesses.FS, dir)
		if err != nil {
			t.Fatal(err)
		}
		found := 0
		for _, entry := range entries {
			fixture, ok := strings.CutSuffix(entry.Name(), ".ir.json")
			if !ok {
				continue
			}
			found++
			t.Run(name+"/"+fixture, func(t *testing.T) {
				event, _, _ := strings.Cut(fixture, "-")
				loaded := loadEvent(t, name, event)
				payload := read(t, path.Join(dir, fixture+".json"))
				if err := loaded.Validate(payload); err != nil {
					t.Errorf("Validate: %v", err)
				}
				var want expectedCall
				if err := json.Unmarshal(read(t, path.Join(dir, entry.Name())), &want,
					json.RejectUnknownMembers(true)); err != nil {
					t.Fatal(err)
				}
				got, err := loaded.Decode(payload)
				if err != nil {
					t.Fatalf("Decode: %v", err)
				}
				wantFields := map[string]ir.Value{}
				for field, value := range want.Fields {
					wantFields[field] = value.value()
				}
				wantLists := map[string][]ir.Value{}
				for field, values := range want.Lists {
					for _, value := range values {
						wantLists[field] = append(wantLists[field], value.value())
					}
				}
				if got.Harness != name || got.Event != event || got.Tool != want.Tool || got.Kind != want.Kind ||
					!maps.Equal(got.Fields, wantFields) || !maps.EqualFunc(got.Lists, wantLists, slices.Equal) ||
					got.ToolFailed != want.ToolFailed {
					t.Errorf("Decode = %+v, want tool %q kind %q fields %+v lists %+v tool failed %v",
						got, want.Tool, want.Kind, wantFields, wantLists, want.ToolFailed)
				}
			})
		}
		if found == 0 {
			t.Errorf("%s: no fixtures", name)
		}
	}
}

func TestValidateRejectsAPayloadOutsideTheSchema(t *testing.T) {
	// Each harness's shell call, with its command made a number.
	shell := map[string]struct {
		fixture string
		break_  func(payload map[string]any)
	}{
		"claude": {"pre-bash.json", func(p map[string]any) { p["tool_input"] = map[string]any{"command": 1} }},
		"codex":  {"pre-bash.json", func(p map[string]any) { p["tool_input"] = map[string]any{"command": 1} }},
		"agy": {"pre-run-command.json", func(p map[string]any) {
			p["toolCall"] = map[string]any{"name": "run_command", "args": map[string]any{"CommandLine": 1}}
		}},
		"pi": {"pre-bash.json", func(p map[string]any) { p["input"] = map[string]any{"command": 1} }},
	}
	for _, name := range names {
		pre := load(t, name)
		if err := pre.Validate([]byte(`{}`)); err == nil {
			t.Errorf("%s: Validate({}) = nil, want an error", name)
		}
		var payload map[string]any
		if err := json.Unmarshal(read(t, path.Join(name, "fixtures", shell[name].fixture)), &payload); err != nil {
			t.Fatal(err)
		}
		shell[name].break_(payload)
		data, err := json.Marshal(payload)
		if err != nil {
			t.Fatal(err)
		}
		if err := pre.Validate(data); err == nil {
			t.Errorf("%s: Validate(%s) = nil, want an error", name, data)
		}
	}
}

func read(t *testing.T, name string) []byte {
	t.Helper()
	data, err := fs.ReadFile(harnesses.FS, name)
	if err != nil {
		t.Fatal(err)
	}
	return data
}

func TestDecodeSelectsTheFirstCandidateThatIsNotNullOrFalse(t *testing.T) {
	pre := load(t, "claude")
	tests := []struct {
		payload string
		want    map[string]ir.Value
	}{
		{`{"tool_input":{"content":false,"new_string":"b"}}`, map[string]ir.Value{
			ir.FieldContent: {Text: "b", IsString: true},
		}},
		{`{"tool_input":{"content":null,"new_string":null,"new_source":"c"}}`, map[string]ir.Value{
			ir.FieldContent: {Text: "c", IsString: true},
		}},
		{`{"tool_input":{"content":"","new_string":"b"}}`, map[string]ir.Value{
			ir.FieldContent: {Text: "", IsString: true},
		}},
		{`{"tool_input":{"file_path":0,"command":"x"}}`, map[string]ir.Value{
			ir.FieldFilePath: {Text: "0"},
			ir.FieldCommand:  {Text: "x", IsString: true},
		}},
		{`{"tool_input":{"content":true}}`, map[string]ir.Value{ir.FieldContent: {Text: "true"}}},
		{`{"tool_input":{"command":false,"file_path":null}}`, map[string]ir.Value{}},
		{`{"tool_input":[]}`, map[string]ir.Value{}},
		{`{"tool_input":"x"}`, map[string]ir.Value{}},
		{`[1]`, map[string]ir.Value{}},
		{`null`, map[string]ir.Value{}},
		{`{}`, map[string]ir.Value{}},
	}
	for _, test := range tests {
		got, err := pre.Decode([]byte(test.payload))
		if err != nil {
			t.Errorf("Decode(%s): %v", test.payload, err)
			continue
		}
		if !maps.Equal(got.Fields, test.want) {
			t.Errorf("Decode(%s).Fields = %+v, want %+v", test.payload, got.Fields, test.want)
		}
	}
}

func TestDecodePrintsANonStringValueAsJQPrintsIt(t *testing.T) {
	// Strings inside are decoded and escaped again, so an escaped letter
	// reads as the letter and a NUL stays escaped; numbers keep their text.
	pre := load(t, "claude")
	tests := []struct{ content, want string }{
		{`["a\u0041", "b\u0000c"]`, `["aA","b\u0000c"]`},
		{`{ "k\tey" : [ 1e400 , -0, true , null ] }`, `{"k\tey":[1e400,-0,true,null]}`},
	}
	for _, test := range tests {
		got, err := pre.Decode([]byte(`{"tool_input":{"content":` + test.content + `}}`))
		if err != nil {
			t.Fatalf("Decode(%s): %v", test.content, err)
		}
		if value := got.Fields[ir.FieldContent]; value.IsString || value.Text != test.want {
			t.Errorf("content %s = %+v, want JSON text %s", test.content, value, test.want)
		}
	}
	got, err := pre.Decode([]byte(`{"tool_input":{"content":"é\u0000"}}`))
	if err != nil {
		t.Fatal(err)
	}
	if value := got.Fields[ir.FieldContent]; !value.IsString || value.Text != "é\x00" {
		t.Errorf("a string content = %+v, want the string with its NUL", value)
	}
}

func TestDecodeReadsTheToolAndItsKind(t *testing.T) {
	tests := []struct{ harness, tool, kind string }{
		{"claude", "Bash", ir.KindShell},
		{"claude", "Write", ir.KindWrite},
		{"claude", "Edit", ir.KindEdit},
		{"claude", "NotebookEdit", ir.KindNotebook},
		{"claude", "WebFetch", ""},
		{"codex", "Bash", ir.KindShell},
		{"codex", "apply_patch", ir.KindPatch},
		{"agy", "run_command", ir.KindShell},
		{"agy", "write_file", ir.KindWrite},
		{"agy", "edit_file", ir.KindEdit},
		{"agy", "read_file", ""},
		// Named in agy's public docs, never seen in a payload: not mapped.
		{"agy", "write_to_file", ""},
		{"pi", "bash", ir.KindShell},
		{"pi", "write", ir.KindWrite},
		{"pi", "edit", ir.KindEdit},
		{"pi", "read", ""},
		// Pi's Windows shell tool, never seen in a payload: not mapped.
		{"pi", "powershell", ""},
	}
	// Where each harness names the tool.
	payload := map[string]func(tool string) string{
		"claude": func(tool string) string { return `{"tool_name":"` + tool + `"}` },
		"codex":  func(tool string) string { return `{"tool_name":"` + tool + `"}` },
		"agy":    func(tool string) string { return `{"toolCall":{"name":"` + tool + `"}}` },
		"pi":     func(tool string) string { return `{"tool":"` + tool + `"}` },
	}
	for _, test := range tests {
		got, err := load(t, test.harness).Decode([]byte(payload[test.harness](test.tool)))
		if err != nil {
			t.Fatal(err)
		}
		if got.Tool != test.tool || got.Kind != test.kind {
			t.Errorf("%s %s: tool %q kind %q, want kind %q", test.harness, test.tool, got.Tool, got.Kind, test.kind)
		}
	}
	// A tool name elsewhere, or not a string, is no tool.
	for _, test := range []struct{ harness, payload string }{
		{"agy", `{"tool_name":"run_command"}`},
		{"agy", `{"toolCall":{"name":1}}`},
		{"agy", `{"toolCall":"run_command"}`},
		{"claude", `{"toolCall":{"name":"Bash"}}`},
	} {
		got, err := load(t, test.harness).Decode([]byte(test.payload))
		if err != nil {
			t.Fatal(err)
		}
		if got.Tool != "" || got.Kind != "" {
			t.Errorf("%s %s: tool %q kind %q, want none", test.harness, test.payload, got.Tool, got.Kind)
		}
	}
}

func TestDecodeReadsAListFieldElementByElement(t *testing.T) {
	// Each element is read as a single field is: null and false are skipped,
	// any other value is taken, a string as it is and the rest as JSON text.
	// A list with no element taken is missing.
	pre := load(t, "agy")
	text := func(s string) ir.Value { return ir.Value{Text: s, IsString: true} }
	tests := []struct {
		payload string
		want    []ir.Value
	}{
		{`{"workspacePaths":["/a"]}`, []ir.Value{text("/a")}},
		{
			`{"workspacePaths":["/a",null,false,"/b",1,"",["/c"]]}`,
			[]ir.Value{text("/a"), text("/b"), {Text: "1"}, text(""), {Text: `["/c"]`}},
		},
		{`{"workspacePaths":[null,false]}`, nil},
		{`{"workspacePaths":[]}`, nil},
		{`{"workspacePaths":null}`, nil},
		{`{"workspacePaths":"/a"}`, nil},
		// "*" selects an array's elements; it is never a member's name.
		{`{"workspacePaths":{"*":"/a"}}`, nil},
		{`{}`, nil},
	}
	for _, test := range tests {
		got, err := pre.Decode([]byte(test.payload))
		if err != nil {
			t.Fatalf("Decode(%s): %v", test.payload, err)
		}
		list, ok := got.Lists[ir.ListWorkspaces]
		if !slices.Equal(list, test.want) || ok != (test.want != nil) {
			t.Errorf("Decode(%s): workspaces %+v (present %v), want %+v", test.payload, list, ok, test.want)
		}
	}
}

func TestDecodeReadsAListPointerThroughEachElement(t *testing.T) {
	// A pointer goes on after "*" inside each element; an element where it
	// finds nothing, or null or false, adds nothing.
	def, err := definition.Load(fstest.MapFS{
		"h/harness.json": {Data: []byte(`{"name":"h","versions":["1"],"tools":{},"transport":"command","pathResolution":"as-given","hookCwd":"session",` +
			`"events":{"pre":{"schema":"pre.schema.json","answers":{"pass":{"exit":0}}}}}`)},
		"h/pre.schema.json": {Data: []byte(`{"type":"object","x-ir-tool":"/tool",` +
			`"x-ir":{"contents":["/input/edits/*/newText"]}}`)},
	}, "h")
	if err != nil {
		t.Fatal(err)
	}
	pre, _ := def.Event("pre")
	got, err := pre.Decode([]byte(`{"input":{"edits":[{"newText":"a"},{"oldText":"x"},{"newText":null},` +
		`"b",{"newText":"c","n":2}]}}`))
	if err != nil {
		t.Fatal(err)
	}
	want := []ir.Value{{Text: "a", IsString: true}, {Text: "c", IsString: true}}
	if !slices.Equal(got.Lists["contents"], want) {
		t.Errorf("contents = %+v, want %+v", got.Lists["contents"], want)
	}
}

func TestDecodeReadsWhetherThePostedToolCallFailed(t *testing.T) {
	// agy's post payload carries error: "" after a success. Its docs make
	// error optional, set on failure, so an omitted error is a success too;
	// anything else is a failure.
	var captured map[string]any
	if err := json.Unmarshal(read(t, "agy/fixtures/post-write-file.json"), &captured); err != nil {
		t.Fatal(err)
	}
	post := loadEvent(t, "agy", "post")
	tests := []struct {
		error  any // the error member; omitted when nil and not set
		omit   bool
		failed bool
	}{
		{"", false, false},
		{nil, true, false},
		{"write failed", false, true},
		{" ", false, true},
		{nil, false, true}, // "error": null
		{1, false, true},
		{false, false, true},
		{[]any{""}, false, true},
		{map[string]any{}, false, true},
		{map[string]any{"error": ""}, false, true},
	}
	for _, test := range tests {
		payload := maps.Clone(captured)
		if test.omit {
			delete(payload, "error")
		} else {
			payload["error"] = test.error
		}
		data, err := json.Marshal(payload)
		if err != nil {
			t.Fatal(err)
		}
		got, err := post.Decode(data)
		if err != nil {
			t.Fatal(err)
		}
		if got.ToolFailed != test.failed {
			t.Errorf("error %#v (omitted %v): tool failed %v, want %v", test.error, test.omit, got.ToolFailed, test.failed)
		}
	}
	// The member is read as written: a number no float64 holds, as error or
	// anywhere else, is read like any other value.
	for payload, failed := range map[string]bool{
		`{"error":"","x":1e400}`:                   false,
		`{"x":[-1e400,{"y":1e-400}]}`:              false,
		`{"error":1e400}`:                          true,
		`{"error":123456789012345678901234567890}`: true,
		`{"error":"\u0000"}`:                       true,
		`{"error":"\u0061"}`:                       true,
		`[]`:                                       false,
	} {
		got, err := post.Decode([]byte(payload))
		if err != nil {
			t.Fatalf("Decode(%s): %v", payload, err)
		}
		if got.ToolFailed != failed {
			t.Errorf("Decode(%s): tool failed %v, want %v", payload, got.ToolFailed, failed)
		}
	}
	// Claude's PostToolUse fires only after a success, and Codex's post has
	// no success signal: their calls never read as failed, nor does a pre call.
	for _, name := range names {
		for _, event := range events {
			if (name == "agy" || name == "pi") && event == "post" {
				continue // they have one (TestDecodeReadsPisSuccessSignal for Pi's)
			}
			got, err := loadEvent(t, name, event).Decode([]byte(`{"error":"x","tool_response":{"success":false}}`))
			if err != nil {
				t.Fatal(err)
			}
			if got.ToolFailed {
				t.Errorf("%s %s: tool failed, want no failure signal", name, event)
			}
		}
	}
}

func TestDecodeReadsASuccessSignalAsWritten(t *testing.T) {
	// Signals of the shapes other harnesses use: Pi's isError (false, or
	// absent), and OpenCode's status, which must be there.
	load := func(success string) definition.Event {
		def, err := definition.Load(fstest.MapFS{
			"h/harness.json": {Data: []byte(`{"name":"h","versions":["1"],"tools":{},"transport":"command","pathResolution":"as-given","hookCwd":"session",` +
				`"events":{"post":{"schema":"s.schema.json","answers":{"pass":{"exit":0}}}}}`)},
			"h/s.schema.json": {Data: []byte(`{"x-ir-tool":"/tool","x-ir":{},"x-success":` + success + `}`)},
		}, "h")
		if err != nil {
			t.Fatal(err)
		}
		post, _ := def.Event("post")
		return post
	}
	isError := load(`{"pointer":"/isError","values":[false,null],"absent":true}`)
	status := load(`{"pointer":"/result/status","values":["completed"],"absent":false}`)
	tests := []struct {
		event   definition.Event
		payload string
		failed  bool
	}{
		{isError, `{"isError":false}`, false},
		{isError, `{"isError":null}`, false},
		{isError, `{}`, false},
		{isError, `{"isError":true}`, true},
		{isError, `{"isError":"false"}`, true},
		{isError, `{"isError":0}`, true},
		{status, `{"result":{"status":"completed"}}`, false},
		// A string is compared after decoding: its escapes do not matter.
		{status, `{"result":{"status":"\u0063ompleted"}}`, false},
		{status, `{"result":{"status":"completed "}}`, true},
		{status, `{"result":{"status":"error"}}`, true},
		{status, `{"result":{}}`, true},
		{status, `{"result":"completed"}`, true},
		{status, `{}`, true},
	}
	for _, test := range tests {
		got, err := test.event.Decode([]byte(test.payload))
		if err != nil {
			t.Fatalf("Decode(%s): %v", test.payload, err)
		}
		if got.ToolFailed != test.failed {
			t.Errorf("Decode(%s): tool failed %v, want %v", test.payload, got.ToolFailed, test.failed)
		}
	}
}

func TestLoadRejectsAPostSuccessSignalItCannotUse(t *testing.T) {
	harness := func(event string) []byte {
		return []byte(`{"name":"h","versions":["1"],"tools":{},"transport":"command","pathResolution":"as-given","hookCwd":"session","events":{"` + event +
			`":{"schema":"s.schema.json","answers":{"pass":{"exit":0}}}}}`)
	}
	schema := func(success string) string { return `{"x-ir-tool":"/tool","x-ir":{},"x-success":` + success + `}` }
	control := `{"description":"d","pointer":"/a/b","values":["",true,false,null],"absent":false}`
	tests := map[string]struct{ event, schema string }{
		"x-success before the tool runs":      {"pre", schema(control)},
		"x-success that is not an object":     {"post", schema(`1`)},
		"an unknown member":                   {"post", schema(`{"pointer":"/a","values":[""],"absent":true,"type":"object"}`)},
		"no pointer":                          {"post", schema(`{"values":[""],"absent":true}`)},
		"a pointer that is not from the root": {"post", schema(`{"pointer":"a","values":[""],"absent":true}`)},
		"a star in the pointer":               {"post", schema(`{"pointer":"/a/*","values":[""],"absent":true}`)},
		"no values":                           {"post", schema(`{"pointer":"/a","values":[],"absent":true}`)},
		"a number among the values":           {"post", schema(`{"pointer":"/a","values":[0],"absent":true}`)},
		"an object among the values":          {"post", schema(`{"pointer":"/a","values":[{}],"absent":true}`)},
		"no word on an absent member":         {"post", schema(`{"pointer":"/a","values":[""]}`)},
	}
	if _, err := definition.Load(fstest.MapFS{
		"h/harness.json":  {Data: harness("post")},
		"h/s.schema.json": {Data: []byte(schema(control))},
	}, "h"); err != nil {
		t.Fatalf("the control: Load = %v, want it loaded", err)
	}
	for what, test := range tests {
		_, err := definition.Load(fstest.MapFS{
			"h/harness.json":  {Data: harness(test.event)},
			"h/s.schema.json": {Data: []byte(test.schema)},
		}, "h")
		if err == nil {
			t.Errorf("%s: Load = nil, want an error", what)
		}
	}
}

func TestLoadRejectsAnIRMapItCannotRead(t *testing.T) {
	harness := []byte(`{"name":"h","versions":["1"],"tools":{},"transport":"command","pathResolution":"as-given","hookCwd":"session",` +
		`"events":{"pre":{"schema":"pre.schema.json","answers":{"pass":{"exit":0}}}}}`)
	schemas := map[string]string{
		"a list pointer among other candidates": `{"x-ir-tool":"/tool","x-ir":{"w":["/a/*","/b"]}}`,
		"two stars in one pointer":              `{"x-ir-tool":"/tool","x-ir":{"w":["/a/*/b/*"]}}`,
		"no tool pointer":                       `{"x-ir":{"command":["/command"]}}`,
		"a tool pointer that is not one":        `{"x-ir-tool":"tool","x-ir":{}}`,
		"a star in the tool pointer":            `{"x-ir-tool":"/tools/*","x-ir":{}}`,
	}
	if _, err := definition.Load(fstest.MapFS{
		"h/harness.json":    {Data: harness},
		"h/pre.schema.json": {Data: []byte(`{"x-ir-tool":"/tool","x-ir":{"w":["/a/*/b"],"c":["/c","/d"]}}`)},
	}, "h"); err != nil {
		t.Fatalf("the control: Load = %v, want it loaded", err)
	}
	for what, schema := range schemas {
		_, err := definition.Load(fstest.MapFS{
			"h/harness.json":    {Data: harness},
			"h/pre.schema.json": {Data: []byte(schema)},
		}, "h")
		if err == nil {
			t.Errorf("%s: Load = nil, want an error", what)
		}
	}
}

// nested is a payload with n levels of nesting in all: the root object, then
// n-1 arrays.
func nested(n int) string {
	return `{"x":` + strings.Repeat("[", n-1) + "1" + strings.Repeat("]", n-1) + "}"
}

func TestDecodeReadsOneJSONValueAndNothingElse(t *testing.T) {
	// Every harness and event reads the same payloads, whatever it maps.
	readable := []string{
		`{"tool_input":{"command":"x"}}`,
		`{"a":-1e400,"b":1e-400,"c":123456789012345678901234567890}`,
		`{"error":"","x":1e400}`,
		"{\"a\":1}\n",
		`{"a":1e400}`,
		"{\"a\":\"\U0001F600\"}",
		"{\"a\":\"\uffff\"}",
		nested(10000),
	}
	unreadable := []string{
		``,
		`   `,
		`hello`,
		`{"a":1} x`,
		`{"a":1}{"a":2}`,
		"\xef\xbb\xbf{\"a\":1}",
		"{\"a\":\"\xff\"}",
		"{\"a\":\"\x00\"}",
		"{\"a\":\x00 1}",
		"{\"a\":\"\x01\"}",
		"{\"a\":\"\t\"}",
		`{"a":NaN}`,
		`{"a":Infinity}`,
		`{"a":-Infinity}`,
		`{"a":"\ud800"}`,
		`{"a":"\udc00\ud800"}`,
		`{"a":1,"a":2}`,
		`{"a":[{"b":1,"b":2}]}`,
		nested(10001),
	}
	for _, name := range names {
		for _, event := range events {
			loaded := loadEvent(t, name, event)
			for _, payload := range readable {
				if _, err := loaded.Decode([]byte(payload)); err != nil {
					t.Errorf("%s %s: Decode(%.40q): %v, want it read", name, event, payload, err)
				}
			}
			for _, payload := range unreadable {
				if _, err := loaded.Decode([]byte(payload)); !errors.Is(err, definition.ErrUnreadable) {
					t.Errorf("%s %s: Decode(%.40q) = %v, want ErrUnreadable", name, event, payload, err)
				}
			}
		}
	}
}

func TestAnswerRendersEachHarnessAnswer(t *testing.T) {
	block := ir.Outcome{Action: ir.Block, Rule: "file.yml", Reason: "'a.yml' uses '.yml'."}
	tests := []struct {
		harness string
		outcome ir.Outcome
		want    definition.Answer
	}{
		{"claude", ir.Outcome{}, definition.Answer{}},
		{"codex", ir.Outcome{}, definition.Answer{}},
		{"claude", block, definition.Answer{Exit: 2, Stderr: "BLOCKED: 'a.yml' uses '.yml'.\n"}},
		{"codex", block, definition.Answer{Stdout: `{"hookSpecificOutput":{"hookEventName":"PreToolUse",` +
			`"permissionDecision":"deny","permissionDecisionReason":"BLOCKED: 'a.yml' uses '.yml'."}}` + "\n"}},
		// agy's neutral answer is "ask" (no answer at all denies), and its
		// reason reaches the model as it is: escaped, not made one line.
		{"agy", ir.Outcome{}, definition.Answer{Stdout: `{"decision":"ask"}` + "\n"}},
		{"agy", block, definition.Answer{Stdout: `{"decision":"deny","reason":"BLOCKED: 'a.yml' uses '.yml'."}` + "\n"}},
		{"agy", ir.Outcome{Action: ir.Block, Reason: "two\tlines\nand \"quotes\" \\"}, definition.Answer{
			Stdout: `{"decision":"deny","reason":"BLOCKED: two\tlines\nand \"quotes\" \\"}` + "\n",
		}},
		// Pi's shim reads the shim protocol's response (package shim).
		{"pi", ir.Outcome{}, definition.Answer{Stdout: `{"v":1,"action":"pass"}` + "\n"}},
		{"pi", block, definition.Answer{Stdout: `{"v":1,"action":"block","reason":"BLOCKED: 'a.yml' uses '.yml'."}` + "\n"}},
	}
	for _, test := range tests {
		got, err := load(t, test.harness).Answer(test.outcome)
		if err != nil {
			t.Fatalf("%s: Answer: %v", test.harness, err)
		}
		if got != test.want {
			t.Errorf("%s %v: Answer = %+v, want %+v", test.harness, test.outcome.Action, got, test.want)
		}
	}
}

func TestAnswerWritesAForwardedAnswerAndANoticeAsTheScriptsDid(t *testing.T) {
	native := `{"hookSpecificOutput":{"hookEventName":"PreToolUse","updatedInput":{"command":"rtk ls"}}}`
	forward := ir.Outcome{Action: ir.Forward, Native: native}
	notice := ir.Outcome{Notice: "ruff still reports issues in a.py:\nx\n"}
	// agy answers a post hook with {} on stdout; the others with nothing.
	postStdout := map[string]string{"claude": "", "codex": "", "agy": "{}\n", "pi": `{"v":1,"action":"pass"}` + "\n"}
	for _, name := range names {
		// rtk's edited answer goes to stdout as it is, with a newline (print()).
		// agy and Pi have no rtk yet, so their pre event has no forward answer.
		got, err := load(t, name).Answer(forward)
		if name == "agy" || name == "pi" {
			if err == nil {
				t.Errorf("%s pre forward: Answer = %+v, want no answer", name, got)
			}
		} else if err != nil || got != (definition.Answer{Stdout: native + "\n"}) {
			t.Errorf("%s pre forward: Answer = %+v, %v", name, got, err)
		}
		// The formatter's report goes to stderr; it exits 0 (a pass).
		got, err = loadEvent(t, name, "post").Answer(notice)
		if err != nil || got != (definition.Answer{Stdout: postStdout[name], Stderr: notice.Notice}) {
			t.Errorf("%s post pass: Answer = %+v, %v", name, got, err)
		}
		// A post hook never blocks, so the post event has no block answer.
		if _, err := loadEvent(t, name, "post").Answer(ir.Outcome{Action: ir.Block, Reason: "x"}); err == nil {
			t.Errorf("%s post: a block has an answer", name)
		}
	}
}

func TestCodexReasonIsOneLineAsGuardCodexWritesIt(t *testing.T) {
	// guard-codex.sh: tabs, CRs, and newlines become spaces, other control
	// characters go, backslashes and quotes are escaped, trailing spaces go.
	tests := []struct{ reason, want string }{
		{"a\tb\rc\nd", `a b c d`},
		{"a\x00b\x01c\x1fd\x7fe", "abcd\x7fe"},
		{`back\slash "quoted"`, `back\\slash \"quoted\"`},
		{"trailing \t \n\n", `trailing`},
		{"é   \u0085 <&>", "é   \u0085 <&>"},
	}
	pre := load(t, "codex")
	for _, test := range tests {
		got, err := pre.Answer(ir.Outcome{Action: ir.Block, Reason: test.reason})
		if err != nil {
			t.Fatal(err)
		}
		want := `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny",` +
			`"permissionDecisionReason":"BLOCKED: ` + test.want + `"}}` + "\n"
		if got.Stdout != want || got.Exit != 0 || got.Stderr != "" {
			t.Errorf("reason %q: Answer = %+v, want stdout %s", test.reason, got, want)
		}
	}
}
