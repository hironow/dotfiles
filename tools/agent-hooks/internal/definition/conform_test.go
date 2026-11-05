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
)

func TestEveryFixtureConformsAndHoldsWhatItsKindPromises(t *testing.T) {
	for _, name := range names {
		dir := path.Join(name, "fixtures")
		entries, err := fs.ReadDir(harnesses.FS, dir)
		if err != nil {
			t.Fatal(err)
		}
		for _, entry := range entries {
			if !strings.HasSuffix(entry.Name(), ".json") || strings.HasSuffix(entry.Name(), ".ir.json") {
				continue
			}
			t.Run(name+"/"+entry.Name(), func(t *testing.T) {
				// given a fixture, a payload the harness sends
				event, _, _ := strings.Cut(entry.Name(), "-")
				loaded := loadEvent(t, name, event)
				payload := read(t, path.Join(dir, entry.Name()))
				// when the log checks it against the definition
				// then it fits the schema, and its IR holds what its kind promises
				if got := loaded.Conform(payload); got != definition.Conforms {
					t.Errorf("Conform = %v, want %v", got, definition.Conforms)
				}
				call, err := loaded.Decode(payload)
				if err != nil {
					t.Fatalf("Decode: %v", err)
				}
				if call.MappingMismatch() {
					t.Errorf("MappingMismatch() = true for %+v", call)
				}
			})
		}
	}
}

func TestConformTellsTheEnvelopeFromAToolsInput(t *testing.T) {
	pre := load(t, "claude")
	fixture := read(t, "claude/fixtures/pre-bash.json")
	edit := func(change func(payload map[string]any)) []byte {
		t.Helper()
		var payload map[string]any
		if err := json.Unmarshal(fixture, &payload); err != nil {
			t.Fatal(err)
		}
		change(payload)
		data, err := json.Marshal(payload)
		if err != nil {
			t.Fatal(err)
		}
		return data
	}
	cases := []struct {
		name    string
		payload []byte
		want    definition.Conformance
	}{
		{"the fixture", fixture, definition.Conforms},
		{"an unknown member", edit(func(p map[string]any) { p["new_field"] = 1 }), definition.Conforms},
		{"a number for the tool's name", edit(func(p map[string]any) { p["tool_name"] = 5 }), definition.EnvelopeMismatch},
		{"no session id", edit(func(p map[string]any) { delete(p, "session_id") }), definition.EnvelopeMismatch},
		{"a number for Bash's command", edit(func(p map[string]any) {
			p["tool_input"] = map[string]any{"command": 1}
		}), definition.InputMismatch},
		// An unmapped tool's input is not checked: its command passes.
		{"a number for an unknown tool's command", edit(func(p map[string]any) {
			p["tool_name"] = "FutureTool"
			p["tool_input"] = map[string]any{"command": 123}
		}), definition.Conforms},
		// The validator reads numbers as float64, so a number past its range
		// fails it, though Decode takes the payload.
		{
			"a number past float64's range", []byte(strings.Replace(string(fixture), "{", `{"x": 1e400,`, 1)),
			definition.Unchecked,
		},
		{"not JSON", []byte("{"), definition.Unchecked},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			// given a payload, when the log checks it against Claude's pre schema
			got := pre.Conform(c.payload)
			// then the envelope, a tool's input, and an unreadable payload are told apart
			if got != c.want {
				t.Fatalf("Conform = %v, want %v", got, c.want)
			}
		})
	}
	if _, err := pre.Decode([]byte(strings.Replace(string(fixture), "{", `{"x": 1e400,`, 1))); err != nil {
		t.Fatalf("Decode of the 1e400 payload: %v; the case needs a payload Decode takes", err)
	}
}

func TestEveryDefinitionKeepsItsToolBranchesInTheTopLevelAllOf(t *testing.T) {
	// The envelope is the schema without its top-level allOf, so a branch
	// anywhere else would be checked as part of the envelope.
	branching := []string{"if", "then", "else", "allOf", "anyOf", "oneOf", "not", "dependentSchemas"}
	for _, name := range names {
		for _, event := range events {
			t.Run(name+"/"+event, func(t *testing.T) {
				var schema map[string]any
				if err := json.Unmarshal(read(t, path.Join(name, event+".schema.json")), &schema); err != nil {
					t.Fatal(err)
				}
				delete(schema, "allOf")
				var walk func(node any, at string)
				walk = func(node any, at string) {
					switch node := node.(type) {
					case map[string]any:
						for key, child := range node {
							for _, keyword := range branching {
								if key == keyword {
									t.Errorf("%s: %q at %s, outside the top-level allOf", name, key, at)
								}
							}
							walk(child, at+"/"+key)
						}
					case []any:
						for _, child := range node {
							walk(child, at+"/*")
						}
					}
				}
				walk(schema, "")
			})
		}
	}
}

func TestLoadRefusesTheNameOfTheBinarysOwnCommand(t *testing.T) {
	// given a well-formed definition named "log", the name of `agent-hook log`
	harness := []byte(`{"name":"log","versions":["1"],"tools":{"T":"shell"},"transport":"command",` +
		`"pathResolution":"as-given","hookCwd":"session",` +
		`"events":{"pre":{"schema":"pre.schema.json","answers":{"pass":{"exit":0}}}}}`)
	files := func(name string) fstest.MapFS {
		return fstest.MapFS{
			name + "/harness.json":    {Data: []byte(strings.Replace(string(harness), `"log"`, `"`+name+`"`, 1))},
			name + "/pre.schema.json": {Data: []byte(`{"x-ir-tool":"/tool","x-ir":{}}`)},
		}
	}
	// when it is loaded, or one named after another of the binary's own
	// commands, then it is refused; the control under another name loads
	for _, name := range []string{"log", "version", "selftest"} {
		if _, err := definition.Load(files(name), name); err == nil {
			t.Errorf("Load(%q) = nil error; want the name refused", name)
		}
	}
	if _, err := definition.Load(files("h"), "h"); err != nil {
		t.Fatalf(`the control: Load("h") = %v`, err)
	}
}
