// Package definition loads the harness definitions (the harnesses package):
// for each harness, its tools' kinds and, per event, the JSON Schema of the
// native payload with its map to IR fields ("x-ir") and the answers. With a
// definition it decodes a native payload to an ir.Call and renders an
// ir.Outcome as the harness's answer, so a field that moves upstream is a
// change to data, not to Go.
package definition

import (
	"bytes"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"maps"
	"path"
	"slices"
	"strings"
	"sync"
	"text/template"

	"github.com/goccy/go-json/jsontext"
	json "github.com/goccy/go-json/v2"
	"github.com/google/jsonschema-go/jsonschema"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
)

// ErrUnreadable is what Decode returns for a payload that is not exactly one
// JSON value: RFC 8259, UTF-8, unique member names, no escape of an unpaired
// surrogate, at most 10,000 levels deep. No guard runs on such a payload.
var ErrUnreadable = errors.New("the hook input is not one JSON value")

// Definition is one harness's definition.
type Definition struct {
	Name     string
	Versions []string          // the harness versions it was written for
	Tools    map[string]string // the harness's tool names, each to its kind (ir.Kind*)
	events   map[string]Event
}

// Event returns the definition of one event, such as "pre".
func (d Definition) Event(name string) (Event, bool) {
	event, ok := d.events[name]
	return event, ok
}

// Event is one event's part of a definition.
type Event struct {
	// IR holds the schema's "x-ir": each IR field to its candidate JSON
	// Pointers, in order. Decode takes the first candidate that is present
	// and not null or false, as jq's `//` does.
	IR map[string][]string
	// Undeclared lists the x-ir pointers the schema does not declare: fields
	// the old guards read for every harness, though this one never sends them.
	Undeclared []string

	harness, name string
	tools         map[string]string
	schema        any // the schema as parsed JSON, for Declares
	compiled      *compiledSchema
	answers       map[string]answer
}

// The outcomes an event has an answer for.
const (
	answerPass  = "pass"
	answerBlock = "block"
)

// Answer is what the binary writes for one outcome.
type Answer struct {
	Exit   int
	Stdout string
	Stderr string
}

// harnessFile is harness.json.
type harnessFile struct {
	Name     string               `json:"name"`
	Versions []string             `json:"versions"`
	Tools    map[string]string    `json:"tools"`
	Events   map[string]eventFile `json:"events"`
}

type eventFile struct {
	Schema  string                `json:"schema"`
	Answers map[string]answerFile `json:"answers"`
}

// answerFile is one answer's template. Stdout and Stderr are text/templates;
// in StdoutJSON, every string is one, and the value is written as compact
// JSON and a newline.
type answerFile struct {
	Exit       int            `json:"exit"`
	Stdout     string         `json:"stdout"`
	StdoutJSON jsontext.Value `json:"stdoutJSON"`
	Stderr     string         `json:"stderr"`
}

// schemaFile is the part of a schema the loader reads itself.
type schemaFile struct {
	IR         map[string][]string `json:"x-ir"`
	Undeclared struct {
		Pointers []string `json:"pointers"`
	} `json:"x-ir-undeclared"`
}

var knownKinds = []string{ir.KindShell, ir.KindWrite, ir.KindEdit, ir.KindNotebook, ir.KindPatch}

// Load reads the definition of the named harness from fsys, which holds one
// directory per harness.
func Load(fsys fs.FS, name string) (Definition, error) {
	var file harnessFile
	if err := readJSON(fsys, path.Join(name, "harness.json"), &file); err != nil {
		return Definition{}, err
	}
	if file.Name != name {
		return Definition{}, fmt.Errorf("%s/harness.json names %q", name, file.Name)
	}
	for tool, kind := range file.Tools {
		if !slices.Contains(knownKinds, kind) {
			return Definition{}, fmt.Errorf("%s: tool %s has unknown kind %q", name, tool, kind)
		}
	}
	def := Definition{Name: name, Versions: file.Versions, Tools: file.Tools, events: map[string]Event{}}
	for eventName, eventDef := range file.Events {
		event, err := loadEvent(fsys, name, eventName, eventDef, file.Tools)
		if err != nil {
			return Definition{}, fmt.Errorf("%s %s: %w", name, eventName, err)
		}
		def.events[eventName] = event
	}
	return def, nil
}

func loadEvent(fsys fs.FS, harness, name string, file eventFile, tools map[string]string) (Event, error) {
	schemaPath := path.Join(harness, file.Schema)
	raw, err := fs.ReadFile(fsys, schemaPath)
	if err != nil {
		return Event{}, err
	}
	var schema schemaFile
	if err := json.Unmarshal(raw, &schema); err != nil {
		return Event{}, fmt.Errorf("%s: %w", schemaPath, err)
	}
	for field, pointers := range schema.IR {
		for _, pointer := range pointers {
			if !strings.HasPrefix(pointer, "/") {
				return Event{}, fmt.Errorf("%s: x-ir %s: %q is not a JSON Pointer from the root", schemaPath, field, pointer)
			}
		}
	}
	var tree any
	if err := json.Unmarshal(raw, &tree); err != nil {
		return Event{}, fmt.Errorf("%s: %w", schemaPath, err)
	}
	answers := map[string]answer{}
	for outcome, answerDef := range file.Answers {
		parsed, err := parseAnswer(answerDef)
		if err != nil {
			return Event{}, fmt.Errorf("answer %s: %w", outcome, err)
		}
		answers[outcome] = parsed
	}
	for _, outcome := range []string{answerPass, answerBlock} {
		if _, ok := answers[outcome]; !ok {
			return Event{}, fmt.Errorf("no %s answer", outcome)
		}
	}
	event := Event{
		IR:         schema.IR,
		Undeclared: schema.Undeclared.Pointers,
		harness:    harness,
		name:       name,
		tools:      tools,
		schema:     tree,
		compiled:   &compiledSchema{raw: raw},
		answers:    answers,
	}
	// Render a block once, so a template that fails to run fails here.
	if _, err := event.Answer(ir.Outcome{Action: ir.Block, Rule: "check", Reason: "check"}); err != nil {
		return Event{}, err
	}
	return event, nil
}

func readJSON(fsys fs.FS, name string, v any) error {
	data, err := fs.ReadFile(fsys, name)
	if err != nil {
		return err
	}
	if err := json.Unmarshal(data, v, json.RejectUnknownMembers(true)); err != nil {
		return fmt.Errorf("%s: %w", name, err)
	}
	return nil
}

// compiledSchema is the event's JSON Schema, resolved on first use: only
// Validate needs it.
type compiledSchema struct {
	raw      []byte
	once     sync.Once
	resolved *jsonschema.Resolved
	err      error
}

func (c *compiledSchema) get() (*jsonschema.Resolved, error) {
	c.once.Do(func() {
		var schema jsonschema.Schema
		if err := json.Unmarshal(c.raw, &schema); err != nil {
			c.err = err
			return
		}
		c.resolved, c.err = schema.Resolve(nil)
	})
	return c.resolved, c.err
}

// Validate checks a payload against the event's schema.
func (e Event) Validate(payload []byte) error {
	resolved, err := e.compiled.get()
	if err != nil {
		return fmt.Errorf("the %s %s schema: %w", e.harness, e.name, err)
	}
	var value any
	if err := json.Unmarshal(payload, &value); err != nil {
		return fmt.Errorf("%w: %w", ErrUnreadable, err)
	}
	return resolved.Validate(value)
}

// Declares reports whether the schema declares a property at the pointer:
// a chain of "properties", through allOf, anyOf, and oneOf members, the then
// and else of an if, and local $refs.
func (e Event) Declares(pointer string) bool {
	tokens, ok := pointerTokens(pointer)
	return ok && declares(e.schema, e.schema, tokens)
}

func declares(root, node any, tokens []string) bool {
	if len(tokens) == 0 {
		return true
	}
	for _, schema := range subschemas(root, node) {
		properties, _ := schema["properties"].(map[string]any)
		if child, ok := properties[tokens[0]]; ok && declares(root, child, tokens[1:]) {
			return true
		}
	}
	return false
}

// subschemas returns node and every schema that applies along with it. Each
// local $ref is followed once, so a recursive schema ends.
func subschemas(root, node any) []map[string]any {
	var found []map[string]any
	followed := map[string]bool{}
	var visit func(node any)
	visit = func(node any) {
		schema, ok := node.(map[string]any)
		if !ok {
			return
		}
		found = append(found, schema)
		if ref, ok := schema["$ref"].(string); ok && !followed[ref] {
			followed[ref] = true
			if local, ok := strings.CutPrefix(ref, "#"); ok {
				if tokens, ok := pointerTokens(local); ok {
					if target, ok := lookup(root, tokens); ok {
						visit(target)
					}
				}
			}
		}
		for _, key := range []string{"allOf", "anyOf", "oneOf"} {
			members, _ := schema[key].([]any)
			for _, member := range members {
				visit(member)
			}
		}
		visit(schema["then"])
		visit(schema["else"])
	}
	visit(node)
	return found
}

// lookup follows a JSON Pointer's tokens through parsed JSON objects.
func lookup(node any, tokens []string) (any, bool) {
	for _, token := range tokens {
		object, ok := node.(map[string]any)
		if !ok {
			return nil, false
		}
		if node, ok = object[token]; !ok {
			return nil, false
		}
	}
	return node, true
}

// pointerTokens splits a JSON Pointer ("/a/b", or "" for the root) into its
// reference tokens, with "~1" read as "/" and "~0" as "~".
func pointerTokens(pointer string) ([]string, bool) {
	if pointer == "" {
		return nil, true
	}
	rest, ok := strings.CutPrefix(pointer, "/")
	if !ok {
		return nil, false
	}
	tokens := strings.Split(rest, "/")
	for i, token := range tokens {
		tokens[i] = strings.ReplaceAll(strings.ReplaceAll(token, "~1", "/"), "~0", "~")
	}
	return tokens, true
}

// Decode reads a native payload as the definition maps it. A payload that is
// not one JSON value gives ErrUnreadable. A payload that is one, whatever its
// shape, decodes: a field the payload lacks is missing from the call.
func (e Event) Decode(payload []byte) (ir.Call, error) {
	call := ir.Call{Harness: e.harness, Event: e.name, Fields: map[string]ir.Value{}}
	var root jsontext.Value
	if err := json.Unmarshal(payload, &root); err != nil {
		return call, fmt.Errorf("%w: %w", ErrUnreadable, err)
	}
	objects := objectReader{}
	if tool, ok := objects.member(root, "", "tool_name"); ok && tool.Kind() == '"' {
		if err := json.Unmarshal(tool, &call.Tool); err != nil {
			return call, err
		}
		call.Kind = e.tools[call.Tool]
	}
	for _, field := range slices.Sorted(maps.Keys(e.IR)) {
		for _, pointer := range e.IR[field] {
			value, ok := objects.resolve(root, pointer)
			if !ok || value.Kind() == 'n' || value.Kind() == 'f' {
				continue
			}
			irValue, err := toIRValue(value)
			if err != nil {
				return call, err
			}
			call.Fields[field] = irValue
			break
		}
	}
	return call, nil
}

// toIRValue keeps a string as it is, and prints any other value as compact
// JSON with its strings in their shortest escaping, as jq prints them.
func toIRValue(value jsontext.Value) (ir.Value, error) {
	if value.Kind() == '"' {
		var text string
		if err := json.Unmarshal(value, &text); err != nil {
			return ir.Value{}, err
		}
		return ir.Value{Text: text, IsString: true}, nil
	}
	printed := value.Clone()
	if err := printed.Format(); err != nil {
		return ir.Value{}, err
	}
	return ir.Value{Text: string(printed)}, nil
}

// objectReader reads the members of a payload's objects, each object once.
type objectReader map[string]map[string]jsontext.Value

// resolve follows a JSON Pointer from the root; it finds nothing past a value
// that is not an object.
func (o objectReader) resolve(root jsontext.Value, pointer string) (jsontext.Value, bool) {
	tokens, ok := pointerTokens(pointer)
	if !ok {
		return nil, false
	}
	value := root
	at := ""
	for _, token := range tokens {
		if value, ok = o.member(value, at, token); !ok {
			return nil, false
		}
		at += "/" + strings.ReplaceAll(strings.ReplaceAll(token, "~", "~0"), "/", "~1")
	}
	return value, true
}

// member returns the named member of value, the object at the JSON Pointer at.
func (o objectReader) member(value jsontext.Value, at, name string) (jsontext.Value, bool) {
	if value.Kind() != '{' {
		return nil, false
	}
	members, ok := o[at]
	if !ok {
		if err := json.Unmarshal(value, &members); err != nil {
			return nil, false
		}
		o[at] = members
	}
	member, ok := members[name]
	return member, ok
}

// answer is one parsed answer template.
type answer struct {
	exit       int
	stdout     *template.Template
	stdoutJSON jsontext.Value
	strings    map[string]*template.Template // StdoutJSON's strings
	stderr     *template.Template
}

// answerData is what an answer template reads.
type answerData struct {
	Rule    string // the rule that blocked
	Reason  string // why, as the hook says it
	Message string // "BLOCKED: " and the reason: what the old guards wrote
}

var templateFuncs = template.FuncMap{"oneLine": oneLine}

func parseAnswer(file answerFile) (answer, error) {
	parsed := answer{exit: file.Exit, stdoutJSON: file.StdoutJSON, strings: map[string]*template.Template{}}
	var err error
	if parsed.stdout, err = parseTemplate(file.Stdout); err != nil {
		return answer{}, err
	}
	if parsed.stderr, err = parseTemplate(file.Stderr); err != nil {
		return answer{}, err
	}
	if len(file.StdoutJSON) == 0 {
		return parsed, nil
	}
	if file.Stdout != "" {
		return answer{}, errors.New("both stdout and stdoutJSON")
	}
	decoder := jsontext.NewDecoder(bytes.NewReader(file.StdoutJSON))
	for {
		token, err := decoder.ReadToken()
		if errors.Is(err, io.EOF) {
			return parsed, nil
		}
		if err != nil {
			return answer{}, err
		}
		if token.Kind() == '"' {
			text := token.String()
			if parsed.strings[text], err = parseTemplate(text); err != nil {
				return answer{}, err
			}
		}
	}
}

func parseTemplate(text string) (*template.Template, error) {
	return template.New("").Funcs(templateFuncs).Option("missingkey=error").Parse(text)
}

// Answer renders the harness's answer to an outcome.
func (e Event) Answer(outcome ir.Outcome) (Answer, error) {
	key := answerPass
	data := answerData{}
	if outcome.Action == ir.Block {
		key = answerBlock
		data = answerData{Rule: outcome.Rule, Reason: outcome.Reason, Message: "BLOCKED: " + outcome.Reason}
	}
	chosen := e.answers[key]
	stdout, err := execute(chosen.stdout, data)
	if err != nil {
		return Answer{}, err
	}
	stderr, err := execute(chosen.stderr, data)
	if err != nil {
		return Answer{}, err
	}
	if len(chosen.stdoutJSON) > 0 {
		if stdout, err = chosen.renderJSON(data); err != nil {
			return Answer{}, err
		}
	}
	return Answer{Exit: chosen.exit, Stdout: stdout, Stderr: stderr}, nil
}

// renderJSON writes StdoutJSON as compact JSON and a newline, each string
// rendered as a template and escaped again.
func (a answer) renderJSON(data answerData) (string, error) {
	decoder := jsontext.NewDecoder(bytes.NewReader(a.stdoutJSON))
	var out bytes.Buffer
	encoder := jsontext.NewEncoder(&out)
	for {
		token, err := decoder.ReadToken()
		if errors.Is(err, io.EOF) {
			return out.String(), nil
		}
		if err != nil {
			return "", err
		}
		if token.Kind() == '"' {
			text, err := execute(a.strings[token.String()], data)
			if err != nil {
				return "", err
			}
			token = jsontext.String(text)
		}
		if err := encoder.WriteToken(token); err != nil {
			return "", err
		}
	}
}

func execute(t *template.Template, data answerData) (string, error) {
	var out strings.Builder
	if err := t.Execute(&out, data); err != nil {
		return "", err
	}
	return out.String(), nil
}

// oneLine is the reason as guard-codex.sh puts it in Codex's deny JSON: tabs,
// carriage returns, and newlines become spaces, every other control character
// (byte 0x00 to 0x1f) goes, and trailing spaces go. The JSON encoder then
// escapes backslashes and quotes, as its sed does.
func oneLine(text string) string {
	var out strings.Builder
	for i := range len(text) {
		switch c := text[i]; {
		case c == '\t' || c == '\r' || c == '\n':
			out.WriteByte(' ')
		case c < 0x20:
		default:
			out.WriteByte(c)
		}
	}
	return strings.TrimRight(out.String(), " ")
}
