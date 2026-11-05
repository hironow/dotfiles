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
	"strconv"
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
	// Pending lists tools the harness's docs name but no captured payload
	// showed. They are not mapped, so no hook is registered for them.
	Pending []string
	// HookCwd is where the harness runs its hooks (ir.HookCwd*).
	HookCwd string
	// Transport is how the harness reaches the binary (ir.Transport*).
	Transport string
	// PathResolution is how the harness turns a tool's path into the file it
	// touches (ir.Paths*).
	PathResolution string
	// Support holds each hook's level (Level*) for each tool, by the hook's
	// manifest id and the harness's tool name.
	Support map[string]map[string]Support
	// Registration describes the fragment render can write; nil means none.
	Registration *Registration
	events       map[string]Event
}

// Support is one hook's level for one tool, and why it is not supported.
type Support struct {
	Level  string               `json:"level"`
	Reason string               `json:"reason"`
	OS     map[string]OSSupport `json:"os,omitempty"`
}

// OSSupport is a known gap confined to one launcher's OS.
type OSSupport struct {
	Level  string `json:"level"`
	Reason string `json:"reason"`
}

// SupportOn returns an OS override, or the cell's ordinary level and reason.
func (d Definition) SupportOn(hook, tool, os string) OSSupport {
	support := d.Support[hook][tool]
	if override, ok := support.OS[os]; ok {
		return override
	}
	return OSSupport{Level: support.Level, Reason: support.Reason}
}

// The levels of a hook for a tool.
const (
	LevelSupported   = "supported"   // registered, and it does its whole job
	LevelDegraded    = "degraded"    // registered, with a known gap: the reason
	LevelUnsupported = "unsupported" // not registered: the reason says why
)

// Registered returns the tools a hook is registered for, sorted: those for
// which it is supported or degraded.
func (d Definition) Registered(hook string) []string {
	var tools []string
	for tool, support := range d.Support[hook] {
		if support.Level != LevelUnsupported {
			tools = append(tools, tool)
		}
	}
	slices.Sort(tools)
	return tools
}

// Event returns the definition of one event, such as "pre".
func (d Definition) Event(name string) (Event, bool) {
	event, ok := d.events[name]
	return event, ok
}

// Event is one event's part of a definition.
type Event struct {
	// Tool is the schema's "x-ir-tool": the JSON Pointer to the tool's name.
	Tool string
	// IR holds the schema's "x-ir": each IR field to its candidate JSON
	// Pointers, in order. Decode takes the first candidate that is present
	// and not null or false, as jq's `//` does. A list field has one pointer,
	// with one "*" token for every element of the array there.
	IR map[string][]string
	// Undeclared lists the x-ir pointers the schema does not declare: fields
	// the old guards read for every harness, though this one never sends them.
	Undeclared []string

	harness, name  string
	hookCwd        string // where the harness runs its hooks (ir.HookCwd*)
	transport      string // how the harness reaches the binary (ir.Transport*)
	pathResolution string // how the harness turns a path into a file (ir.Paths*)
	tools          map[string]string
	schema         any // the schema as parsed JSON, for Declares
	compiled       *compiledSchema
	envelope       *compiledSchema // the schema without its top-level allOf
	success        *successRule    // "x-success", or nil: how a post payload tells that the tool call succeeded
	answers        map[string]answer
}

// The outcomes an event has an answer for.
const (
	answerPass    = "pass"
	answerBlock   = "block"
	answerForward = "forward"
	answerRewrite = "rewrite"
)

// Answer is what the binary writes for one outcome.
type Answer struct {
	Exit   int
	Stdout string
	Stderr string
}

// harnessFile is harness.json.
type harnessFile struct {
	Name     string            `json:"name"`
	Versions []string          `json:"versions"`
	Tools    map[string]string `json:"tools"`
	Pending  []string          `json:"pending"`
	HookCwd  string            `json:"hookCwd"`
	// Transport and PathResolution are required: each names an ir constant.
	Transport      string                        `json:"transport"`
	PathResolution string                        `json:"pathResolution"`
	Support        map[string]map[string]Support `json:"support"`
	Events         map[string]eventFile          `json:"events"`
	Registration   *Registration                 `json:"registration"`
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
	Tool       string              `json:"x-ir-tool"`
	IR         map[string][]string `json:"x-ir"`
	Success    jsontext.Value      `json:"x-success"`
	Undeclared struct {
		Pointers []string `json:"pointers"`
	} `json:"x-ir-undeclared"`
}

var knownKinds = []string{ir.KindShell, ir.KindWrite, ir.KindEdit, ir.KindNotebook, ir.KindPatch}

// reservedNames are the binary's own commands (`agent-hook log`, `version`,
// `selftest`, `render`), which no harness can be named.
var reservedNames = []string{"log", "version", "selftest", "render"}

// Load reads the definition of the named harness from fsys, which holds one
// directory per harness.
func Load(fsys fs.FS, name string) (Definition, error) {
	if slices.Contains(reservedNames, name) {
		return Definition{}, fmt.Errorf("%q is the binary's own command, not a harness", name)
	}
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
	if err := checkHarness(file); err != nil {
		return Definition{}, fmt.Errorf("%s/harness.json: %w", name, err)
	}
	def := Definition{
		Name:     name,
		Versions: file.Versions,
		Tools:    file.Tools,
		Pending:  file.Pending,
		HookCwd:  file.HookCwd,
		// Checked by checkHarness: each is one of its ir constants.
		Transport:      file.Transport,
		PathResolution: file.PathResolution,
		Support:        file.Support,
		Registration:   file.Registration,
		events:         map[string]Event{},
	}
	for eventName, eventDef := range file.Events {
		event, err := loadEvent(fsys, name, eventName, eventDef, file)
		if err != nil {
			return Definition{}, fmt.Errorf("%s %s: %w", name, eventName, err)
		}
		def.events[eventName] = event
	}
	return def, nil
}

// checkHarness checks what harness.json says beyond its tools: where hooks
// run, the pending tools (never mapped), and each support level (a known
// level, on a mapped tool, with a reason unless supported).
func checkHarness(file harnessFile) error {
	if file.HookCwd != ir.HookCwdSession && file.HookCwd != ir.HookCwdRegistration {
		return fmt.Errorf("hookCwd %q is neither %q nor %q", file.HookCwd, ir.HookCwdSession, ir.HookCwdRegistration)
	}
	if file.Transport != ir.TransportCommand && file.Transport != ir.TransportShim {
		return fmt.Errorf("transport %q is neither %q nor %q", file.Transport, ir.TransportCommand, ir.TransportShim)
	}
	if file.PathResolution != ir.PathsAsGiven && file.PathResolution != ir.PathsPi {
		return fmt.Errorf("pathResolution %q is neither %q nor %q", file.PathResolution, ir.PathsAsGiven, ir.PathsPi)
	}
	for _, tool := range file.Pending {
		if _, mapped := file.Tools[tool]; mapped {
			return fmt.Errorf("pending tool %s is mapped", tool)
		}
	}
	for hook, tools := range file.Support {
		for tool, support := range tools {
			if _, mapped := file.Tools[tool]; !mapped {
				return fmt.Errorf("support for %s names %s, which is not a mapped tool", hook, tool)
			}
			switch support.Level {
			case LevelSupported:
			case LevelDegraded, LevelUnsupported:
				if support.Reason == "" {
					return fmt.Errorf("support for %s on %s is %s with no reason", hook, tool, support.Level)
				}
			default:
				return fmt.Errorf("support for %s on %s has unknown level %q", hook, tool, support.Level)
			}
		}
	}
	return checkRegistration(file)
}

func loadEvent(fsys fs.FS, harness, name string, file eventFile, owner harnessFile) (Event, error) {
	schemaPath := path.Join(harness, file.Schema)
	raw, err := fs.ReadFile(fsys, schemaPath)
	if err != nil {
		return Event{}, err
	}
	var schema schemaFile
	if err := json.Unmarshal(raw, &schema); err != nil {
		return Event{}, fmt.Errorf("%s: %w", schemaPath, err)
	}
	if err := checkIR(schema); err != nil {
		return Event{}, fmt.Errorf("%s: %w", schemaPath, err)
	}
	success, err := parseSuccess(name, schema.Success)
	if err != nil {
		return Event{}, fmt.Errorf("%s: %w", schemaPath, err)
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
	// Every event can pass; which other outcomes it has answers for depends
	// on its hooks (a post hook never blocks).
	if _, ok := answers[answerPass]; !ok {
		return Event{}, fmt.Errorf("no %s answer", answerPass)
	}
	event := Event{
		Tool:           schema.Tool,
		IR:             schema.IR,
		Undeclared:     schema.Undeclared.Pointers,
		harness:        harness,
		name:           name,
		hookCwd:        owner.HookCwd,
		transport:      owner.Transport,
		pathResolution: owner.PathResolution,
		tools:          owner.Tools,
		schema:         tree,
		compiled:       &compiledSchema{raw: raw},
		envelope:       &compiledSchema{raw: raw, envelope: true},
		success:        success,
		answers:        answers,
	}
	// Render each answer once, so a template that fails to run fails here.
	for _, outcome := range []ir.Outcome{
		{Notice: "check"},
		{Action: ir.Block, Rule: "check", Reason: "check"},
		{Action: ir.Forward, Native: "{}"},
		{Action: ir.Rewrite, Set: ir.Assignment{Field: ir.FieldCommand, Value: "check"}},
	} {
		if _, ok := answers[answerKey(outcome.Action)]; !ok {
			continue
		}
		rendered, err := event.Answer(outcome)
		if err != nil {
			return Event{}, err
		}
		// A shim reads the answer by the shim protocol (package shim).
		if owner.Transport == ir.TransportShim {
			if err := checkShimAnswer(rendered); err != nil {
				return Event{}, fmt.Errorf("answer %s: %w", answerKey(outcome.Action), err)
			}
		}
	}
	return event, nil
}

// successFile is a post schema's "x-success": the member that tells whether
// the tool call succeeded, the values that mean it did, and whether an
// absent member means it did.
type successFile struct {
	Description string           `json:"description"`
	Pointer     string           `json:"pointer"`
	Values      []jsontext.Value `json:"values"`
	Absent      *bool            `json:"absent"`
}

// successRule is a parsed "x-success".
type successRule struct {
	pointer string
	values  []jsontext.Value // each a string, true, false, or null
	absent  bool
}

// parseSuccess reads a post event's "x-success". Only a post event has one,
// since only after the call is there an outcome to read. The values are
// strings, booleans, or null, compared exactly; a number would need a
// representation that every reader agrees on, and no harness signals with
// one.
func parseSuccess(event string, raw jsontext.Value) (*successRule, error) {
	if len(raw) == 0 {
		return nil, nil
	}
	if event != "post" {
		return nil, fmt.Errorf("x-success on the %s event: only a post event has a tool call's outcome", event)
	}
	var file successFile
	if err := json.Unmarshal(raw, &file, json.RejectUnknownMembers(true)); err != nil {
		return nil, fmt.Errorf("x-success: %w", err)
	}
	tokens, ok := pointerTokens(file.Pointer)
	if file.Pointer == "" || !ok || slices.Contains(tokens, wildcard) {
		return nil, fmt.Errorf("x-success: pointer %q is not a JSON Pointer from the root to one value", file.Pointer)
	}
	if len(file.Values) == 0 {
		return nil, errors.New("x-success: no values")
	}
	for _, value := range file.Values {
		if !slices.Contains([]jsontext.Kind{'"', 't', 'f', 'n'}, value.Kind()) {
			return nil, fmt.Errorf("x-success: value %s is not a string, a boolean, or null", value)
		}
	}
	if file.Absent == nil {
		return nil, errors.New("x-success: absent does not say what an absent member means")
	}
	return &successRule{pointer: file.Pointer, values: file.Values, absent: *file.Absent}, nil
}

// succeeded reads the rule's member from the payload as written, so a number
// anywhere is read like any other value.
func (s successRule) succeeded(objects objectReader, root jsontext.Value) bool {
	value, found := objects.resolve(root, s.pointer)
	if !found {
		return s.absent
	}
	for _, want := range s.values {
		if sameLiteral(value, want) {
			return true
		}
	}
	return false
}

// sameLiteral reports whether a JSON value is the string, boolean, or null
// want: a string compared after decoding, so its escapes do not matter.
func sameLiteral(value, want jsontext.Value) bool {
	if value.Kind() != want.Kind() {
		return false
	}
	if want.Kind() != '"' {
		return true
	}
	var got, wanted string
	return json.Unmarshal(value, &got) == nil && json.Unmarshal(want, &wanted) == nil && got == wanted
}

// wildcard is the reference token that selects every element of an array.
const wildcard = "*"

// checkIR checks that the schema says where the tool's name is, and that every
// x-ir pointer is one Decode can read: a JSON Pointer from the root, with at
// most one "*", which makes it its field's only candidate.
func checkIR(schema schemaFile) error {
	tokens, ok := pointerTokens(schema.Tool)
	if schema.Tool == "" || !ok || slices.Contains(tokens, wildcard) {
		return fmt.Errorf("x-ir-tool %q is not a JSON Pointer from the root to one value", schema.Tool)
	}
	for field, pointers := range schema.IR {
		for _, pointer := range pointers {
			tokens, ok := pointerTokens(pointer)
			if pointer == "" || !ok {
				return fmt.Errorf("x-ir %s: %q is not a JSON Pointer from the root", field, pointer)
			}
			switch stars := countWildcards(tokens); {
			case stars > 1:
				return fmt.Errorf("x-ir %s: %q has more than one %q", field, pointer, wildcard)
			case stars == 1 && len(pointers) > 1:
				return fmt.Errorf("x-ir %s: the list pointer %q is not the field's only candidate", field, pointer)
			}
		}
	}
	return nil
}

// countWildcards counts a pointer's "*" tokens.
func countWildcards(tokens []string) int {
	count := 0
	for _, token := range tokens {
		if token == wildcard {
			count++
		}
	}
	return count
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
// Validate and Conform need it.
type compiledSchema struct {
	raw []byte
	// envelope drops the schema's top-level allOf, where every definition
	// keeps its per-tool branches: what is left checks the envelope.
	envelope bool
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
		if c.envelope {
			schema.AllOf = nil
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

// Conformance is how a payload fits its event's schema. Only the log reads
// it: no answer depends on it.
type Conformance int

const (
	// Conforms is a payload that fits the whole schema.
	Conforms Conformance = iota
	// EnvelopeMismatch is a payload that fails the schema without its
	// top-level allOf, which holds every per-tool branch: the envelope (the
	// ids, the event, the tool's name).
	EnvelopeMismatch
	// InputMismatch is a payload that fits the envelope but not the whole
	// schema: a tool's input.
	InputMismatch
	// Unchecked is a payload the validator could not read. It reads numbers
	// as float64, so a number past that range fails it, though Decode takes
	// the payload.
	Unchecked
)

func (c Conformance) String() string {
	switch c {
	case Conforms:
		return "conforms"
	case EnvelopeMismatch:
		return "envelope"
	case InputMismatch:
		return "input"
	case Unchecked:
		return "unchecked"
	default:
		return "Conformance(" + strconv.Itoa(int(c)) + ")"
	}
}

// Conform checks a payload against the event's envelope, then against the
// whole schema. The validator's messages are not kept: the log takes only
// which part failed.
func (e Event) Conform(payload []byte) Conformance {
	var value any
	if err := json.Unmarshal(payload, &value); err != nil {
		return Unchecked
	}
	envelope, err := e.envelope.get()
	if err != nil {
		return Unchecked
	}
	if envelope.Validate(value) != nil {
		return EnvelopeMismatch
	}
	whole, err := e.compiled.get()
	if err != nil {
		return Unchecked
	}
	if whole.Validate(value) != nil {
		return InputMismatch
	}
	return Conforms
}

// Declares reports whether the schema declares a property at the pointer:
// a chain of "properties", through allOf, anyOf, and oneOf members, the then
// and else of an if, and local $refs. A "*" is declared by an array's
// "items".
func (e Event) Declares(pointer string) bool {
	tokens, ok := pointerTokens(pointer)
	return ok && declares(e.schema, e.schema, tokens)
}

func declares(root, node any, tokens []string) bool {
	if len(tokens) == 0 {
		return true
	}
	for _, schema := range subschemas(root, node) {
		var child any
		var ok bool
		if tokens[0] == wildcard {
			child, ok = schema["items"].(map[string]any)
		} else {
			properties, _ := schema["properties"].(map[string]any)
			child, ok = properties[tokens[0]]
		}
		if ok && declares(root, child, tokens[1:]) {
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
	call := ir.Call{
		Harness: e.harness, Event: e.name, HookCwd: e.hookCwd,
		Transport: e.transport, PathResolution: e.pathResolution, Fields: map[string]ir.Value{},
	}
	var root jsontext.Value
	if err := json.Unmarshal(payload, &root); err != nil {
		return call, fmt.Errorf("%w: %w", ErrUnreadable, err)
	}
	objects := objectReader{}
	if e.success != nil {
		call.ToolFailed = !e.success.succeeded(objects, root)
	}
	if tool, ok := objects.resolve(root, e.Tool); ok && tool.Kind() == '"' {
		if err := json.Unmarshal(tool, &call.Tool); err != nil {
			return call, err
		}
		call.Kind = e.tools[call.Tool]
	}
	for _, field := range slices.Sorted(maps.Keys(e.IR)) {
		pointers := e.IR[field]
		if before, after, ok := cutWildcard(pointers[0]); ok {
			list, err := objects.resolveEach(root, before, after)
			if err != nil {
				return call, err
			}
			if len(list) > 0 {
				if call.Lists == nil {
					call.Lists = map[string][]ir.Value{}
				}
				call.Lists[field] = list
			}
			continue
		}
		for _, pointer := range pointers {
			value, ok := objects.resolve(root, pointer)
			if !taken(value, ok) {
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

// taken reports whether jq's `//` takes a value: one that is present and not
// null or false.
func taken(value jsontext.Value, present bool) bool {
	return present && value.Kind() != 'n' && value.Kind() != 'f'
}

// cutWildcard splits a list pointer at its "*": the pointer to the array, and
// the pointer from each element on ("" for the element itself).
func cutWildcard(pointer string) (before, after string, ok bool) {
	if pointer == "/"+wildcard {
		return "", "", true
	}
	if before, after, ok = strings.Cut(pointer, "/"+wildcard+"/"); ok {
		return before, "/" + after, true
	}
	before, ok = strings.CutSuffix(pointer, "/"+wildcard)
	return before, "", ok
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

// resolveEach reads a list pointer, split at its "*" (cutWildcard): for every
// element of the array at before, the value after points to in it, when jq's
// `//` would take it. Past anything but an array it finds nothing.
func (o objectReader) resolveEach(root jsontext.Value, before, after string) ([]ir.Value, error) {
	array, ok := o.resolve(root, before)
	if !ok || array.Kind() != '[' {
		return nil, nil
	}
	var elements []jsontext.Value
	if err := json.Unmarshal(array, &elements); err != nil {
		return nil, err
	}
	var list []ir.Value
	for _, element := range elements {
		// Each element is read once, so it needs no shared cache.
		value, ok := objectReader{}.resolve(element, after)
		if !taken(value, ok) {
			continue
		}
		irValue, err := toIRValue(value)
		if err != nil {
			return nil, err
		}
		list = append(list, irValue)
	}
	return list, nil
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
	Native  string // a forwarded answer, as the delegate wrote it
	Notice  string // what a pass reports
	// Set maps the field a rewrite changes to its new value ({{.Set.command}}).
	Set map[string]string
}

var templateFuncs = template.FuncMap{"oneLine": oneLine}

func parseAnswer(file answerFile) (answer, error) {
	return parseAnswerWithFuncs(file, templateFuncs)
}

func parseAnswerWithFuncs(file answerFile, funcs template.FuncMap) (answer, error) {
	parsed := answer{exit: file.Exit, stdoutJSON: file.StdoutJSON, strings: map[string]*template.Template{}}
	parse := func(text string) (*template.Template, error) {
		return template.New("").Funcs(funcs).Option("missingkey=error").Parse(text)
	}
	var err error
	if parsed.stdout, err = parse(file.Stdout); err != nil {
		return answer{}, err
	}
	if parsed.stderr, err = parse(file.Stderr); err != nil {
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
			if parsed.strings[text], err = parse(text); err != nil {
				return answer{}, err
			}
		}
	}
}

// Answer renders the harness's answer to an outcome.
func (e Event) Answer(outcome ir.Outcome) (Answer, error) {
	key := answerKey(outcome.Action)
	data := answerData{Notice: outcome.Notice}
	switch outcome.Action {
	case ir.Block:
		data = answerData{Rule: outcome.Rule, Reason: outcome.Reason, Message: "BLOCKED: " + outcome.Reason}
	case ir.Forward:
		data = answerData{Native: outcome.Native}
	case ir.Rewrite:
		data = answerData{Set: map[string]string{outcome.Set.Field: outcome.Set.Value}}
	}
	chosen, ok := e.answers[key]
	if !ok {
		return Answer{}, fmt.Errorf("the %s %s event has no %s answer", e.harness, e.name, key)
	}
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

// answerKey is the name of an action's answer in harness.json.
func answerKey(action ir.Action) string {
	switch action {
	case ir.Block:
		return answerBlock
	case ir.Forward:
		return answerForward
	case ir.Rewrite:
		return answerRewrite
	default:
		return answerPass
	}
}

// renderJSON writes StdoutJSON as compact JSON and a newline, each string
// rendered as a template and escaped again.
func (a answer) renderJSON(data any) (string, error) {
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

func execute(t *template.Template, data any) (string, error) {
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
