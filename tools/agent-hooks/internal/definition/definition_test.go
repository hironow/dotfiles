package definition_test

import (
	"errors"
	"io/fs"
	"maps"
	"path"
	"slices"
	"strings"
	"testing"

	json "github.com/goccy/go-json/v2"

	"github.com/hironow/dotfiles/tools/agent-hooks/harnesses"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/definition"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
)

// The harnesses this PR defines.
var names = []string{"claude", "codex"}

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

func TestEveryHarnessMapsTheFieldsTheScriptsRead(t *testing.T) {
	// The old scripts read these fields whatever the harness, the event, and
	// the tool; the rtk hook reads the payload's cwd.
	want := map[string][]string{
		ir.FieldCommand:  {"/tool_input/command"},
		ir.FieldFilePath: {"/tool_input/file_path"},
		ir.FieldContent:  {"/tool_input/content", "/tool_input/new_string", "/tool_input/new_source"},
		ir.FieldCwd:      {"/cwd"},
	}
	for _, name := range names {
		for _, event := range events {
			t.Run(name+"/"+event, func(t *testing.T) {
				if got := loadEvent(t, name, event).IR; !maps.EqualFunc(got, want, slices.Equal) {
					t.Errorf("x-ir = %v, want %v", got, want)
				}
			})
		}
	}
}

func TestEveryIRPointerIsDeclaredInItsSchema(t *testing.T) {
	// Except those listed as undeclared: Codex never sends file_path or
	// content, but the old guards read them for every harness.
	wantUndeclared := map[string][]string{
		"claude": nil,
		"codex":  {"/tool_input/file_path", "/tool_input/content", "/tool_input/new_string", "/tool_input/new_source"},
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
}

// expectedCall is a fixture's hand-written IR.
type expectedCall struct {
	Tool   string                   `json:"tool"`
	Kind   string                   `json:"kind"`
	Fields map[string]expectedValue `json:"fields"`
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
				if got.Harness != name || got.Event != event || got.Tool != want.Tool || got.Kind != want.Kind ||
					!maps.Equal(got.Fields, wantFields) {
					t.Errorf("Decode = %+v, want tool %q kind %q fields %+v", got, want.Tool, want.Kind, wantFields)
				}
			})
		}
		if found == 0 {
			t.Errorf("%s: no fixtures", name)
		}
	}
}

func TestValidateRejectsAPayloadOutsideTheSchema(t *testing.T) {
	for _, name := range names {
		pre := load(t, name)
		if err := pre.Validate([]byte(`{}`)); err == nil {
			t.Errorf("%s: Validate({}) = nil, want an error", name)
		}
		// A Bash call whose command is not a string.
		var payload map[string]any
		if err := json.Unmarshal(read(t, path.Join(name, "fixtures", "pre-bash.json")), &payload); err != nil {
			t.Fatal(err)
		}
		payload["tool_input"] = map[string]any{"command": 1}
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
	}
	for _, test := range tests {
		got, err := load(t, test.harness).Decode([]byte(`{"tool_name":"` + test.tool + `"}`))
		if err != nil {
			t.Fatal(err)
		}
		if got.Tool != test.tool || got.Kind != test.kind {
			t.Errorf("%s %s: tool %q kind %q, want kind %q", test.harness, test.tool, got.Tool, got.Kind, test.kind)
		}
	}
}

// nested is a payload with n levels of nesting in all: the root object, then
// n-1 arrays.
func nested(n int) string {
	return `{"x":` + strings.Repeat("[", n-1) + "1" + strings.Repeat("]", n-1) + "}"
}

func TestDecodeReadsOneJSONValueAndNothingElse(t *testing.T) {
	pre := load(t, "claude")
	readable := []string{
		`{"tool_input":{"command":"x"}}`,
		"{\"a\":1}\n",
		`{"a":1e400}`,
		"{\"a\":\"\U0001F600\"}",
		"{\"a\":\"\uffff\"}",
		nested(10000),
	}
	for _, payload := range readable {
		if _, err := pre.Decode([]byte(payload)); err != nil {
			t.Errorf("Decode(%.40q): %v, want it read", payload, err)
		}
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
	for _, payload := range unreadable {
		if _, err := pre.Decode([]byte(payload)); !errors.Is(err, definition.ErrUnreadable) {
			t.Errorf("Decode(%.40q) = %v, want ErrUnreadable", payload, err)
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
	for _, name := range names {
		// rtk's edited answer goes to stdout as it is, with a newline (print()).
		got, err := load(t, name).Answer(forward)
		if err != nil || got != (definition.Answer{Stdout: native + "\n"}) {
			t.Errorf("%s pre forward: Answer = %+v, %v", name, got, err)
		}
		// The formatter's report goes to stderr; it exits 0 (a pass).
		got, err = loadEvent(t, name, "post").Answer(notice)
		if err != nil || got != (definition.Answer{Stderr: notice.Notice}) {
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
