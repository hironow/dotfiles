// Package conformance runs the same scenarios through every harness the
// binary answers, and reads each answer as that harness reads it
// (reader_test.go). It holds tests only.
package conformance

import (
	"bytes"
	"io/fs"
	"maps"
	"path"
	"slices"
	"strconv"
	"strings"
	"testing"

	json "github.com/goccy/go-json/v2"

	"github.com/hironow/dotfiles/tools/agent-hooks/harnesses"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/definition"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/fake"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/launch"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/process"
)

// The roles a scenario's value plays in a tool call.
const (
	roleCommand = "command" // the shell command
	rolePath    = "path"    // the file written or edited
	roleContent = "content" // the text written, or an edit's replacement
	rolePatch   = "patch"   // a patch naming files and their new lines
)

// members says where each harness's tools carry each role: the real input
// members, from docs/plan/agent-hooks-go-contracts.md and the captured
// payloads, not from the definitions' x-ir, which these scenarios test.
var members = map[string]map[string]map[string]string{
	"claude": {
		"Bash":         {roleCommand: "/tool_input/command"},
		"Write":        {rolePath: "/tool_input/file_path", roleContent: "/tool_input/content"},
		"Edit":         {rolePath: "/tool_input/file_path", roleContent: "/tool_input/new_string"},
		"NotebookEdit": {rolePath: "/tool_input/notebook_path", roleContent: "/tool_input/new_source"},
	},
	"codex": {
		"Bash":        {roleCommand: "/tool_input/command"},
		"apply_patch": {rolePatch: "/tool_input/command"},
	},
	"agy": {
		"run_command": {roleCommand: "/toolCall/args/CommandLine"},
		"write_file":  {rolePath: "/toolCall/args/Path", roleContent: "/toolCall/args/Content"},
		"edit_file":   {rolePath: "/toolCall/args/Path", roleContent: "/toolCall/args/Replacement"},
	},
	// The shim's request carries the tool's input as Pi hands it over.
	"pi": {
		"bash":  {roleCommand: "/input/command"},
		"write": {rolePath: "/input/path", roleContent: "/input/content"},
		"edit":  {rolePath: "/input/path", roleContent: "/input/edits/0/newText"},
	},
}

// fixtures names each harness's captured payload for an event and a tool.
var fixtures = map[string]map[string]string{
	"claude": {
		"pre/Bash": "pre-bash.json", "pre/Write": "pre-write.json", "pre/Edit": "pre-edit.json",
		"pre/NotebookEdit": "pre-notebookedit.json", "post/Write": "post-write.json", "post/Edit": "post-edit.json",
	},
	"codex": {
		"pre/Bash": "pre-bash.json", "pre/apply_patch": "pre-apply-patch.json", "post/apply_patch": "post-apply-patch.json",
	},
	"agy": {
		"pre/run_command": "pre-run-command.json", "pre/write_file": "pre-write-file.json",
		"pre/edit_file": "pre-edit-file.json", "post/write_file": "post-write-file.json",
		"post/edit_file": "post-edit-file.json",
	},
	"pi": {
		"pre/bash": "pre-bash.json", "pre/write": "pre-write.json", "pre/edit": "pre-edit.json",
		"pre/edit-two": "pre-edit-two.json", "post/write": "post-write.json", "post/edit": "post-edit.json",
	},
}

// project is the project directory the fixtures name.
const project = "/home/user/project"

// key is a synthetic AWS-style access key id, built from pieces so that no
// scanner reads the source as holding one.
var key = "AKIA" + strings.Repeat("Q", 16)

// guardCase is one guard scenario: the value for a role, and whether the
// guard blocks it.
type guardCase struct {
	role, value string
	blocks      bool
}

// guardCases holds each guard's scenarios, by the role the tool carries.
var guardCases = map[string][]guardCase{
	"command-guard": {
		{roleCommand, "npm install", true},
		{roleCommand, "bun install", false},
	},
	"files-guard": {
		{rolePath, project + "/x.yml", true},
		{rolePath, project + "/x.yaml", false},
		{rolePatch, "*** Begin Patch\n*** Add File: x.yml\n+a: 1\n*** End Patch\n", true},
		{rolePatch, "*** Begin Patch\n*** Add File: x.yaml\n+a: 1\n*** End Patch\n", false},
	},
	"secrets-guard": {
		{roleContent, "aws_access_key_id = " + key + "\n", true},
		{roleContent, "hello\n", false},
		{rolePatch, "*** Begin Patch\n*** Add File: creds.txt\n+" + key + "\n*** End Patch\n", true},
		{rolePatch, "*** Begin Patch\n*** Add File: notes.txt\n+hello\n*** End Patch\n", false},
	},
}

// gaps pins what each degraded cell does today. The definitions must call
// exactly these cells degraded. None is left: Claude's NotebookEdit cell was
// one until the binary fixed the old files guard (fixed-notebook-path).
var gaps = map[[3]string][]guardCase{}

// notCovered names the hooks these scenarios leave to other tests.
var notCovered = map[string]string{
	"rtk": "a delegate to rtk's own adapters; the tool-hooks corpus (internal/toolhookcorpus) covers it",
}

func TestEveryHarnessDoesWhatItsSupportSays(t *testing.T) {
	entries, err := fs.ReadDir(harnesses.FS, ".")
	if err != nil {
		t.Fatal(err)
	}
	for _, entry := range entries {
		name := entry.Name()
		if members[name] == nil || fixtures[name] == nil || readers[name] == nil {
			t.Errorf("%s: the suite has no members, fixtures, or readers for it", name)
			continue
		}
		def, err := definition.Load(harnesses.FS, name)
		if err != nil {
			t.Fatal(err)
		}
		for _, hook := range slices.Sorted(maps.Keys(def.Support)) {
			for _, tool := range def.Registered(hook) {
				cell := [3]string{name, hook, tool}
				degraded := def.Support[hook][tool].Level == definition.LevelDegraded
				if _, pinned := gaps[cell]; degraded != pinned {
					t.Errorf("%v: degraded %v, but the suite pins a gap: %v", cell, degraded, pinned)
					continue
				}
				t.Run(strings.Join(cell[:], "/"), func(t *testing.T) {
					switch {
					case notCovered[hook] != "":
						t.Skip(notCovered[hook])
					case hook == "formatter":
						checkFormatter(t, name, def, tool)
					case degraded:
						checkGuard(t, name, hook, tool, gaps[cell])
					default:
						checkGuard(t, name, hook, tool, guardCases[hook])
					}
				})
			}
		}
	}
}

// checkGuard runs a guard's scenarios on a tool: each case whose role the
// tool carries must block, with a reason, or pass.
func checkGuard(t *testing.T, harness, hook, tool string, cases []guardCase) {
	t.Helper()
	ran := 0
	for _, test := range cases {
		pointer, carried := members[harness][tool][test.role]
		if !carried {
			continue
		}
		ran++
		payload := scenario(t, harness, "pre", tool, map[string]any{pointer: test.value})
		got := runBinary(t, &fake.Machine{}, payload, harness, "pre", hook)
		switch {
		case test.blocks && (got.kind != block || !strings.HasPrefix(got.reason, "BLOCKED: ")):
			t.Errorf("%s %q: %+v, want a block with its reason", test.role, test.value, got)
		case !test.blocks && got != passed(""):
			t.Errorf("%s %q: %+v, want the neutral answer", test.role, test.value, got)
		}
	}
	if ran == 0 {
		t.Errorf("no scenario of %s fits %s's roles %v", hook, tool, slices.Sorted(maps.Keys(members[harness][tool])))
	}
}

// formatCase is one formatter scenario: the file, and the commands its
// suffix's formatter runs on it.
type formatCase struct {
	file     string
	commands func(path, dir string) []fake.Invocation
}

var uvArgs = []string{"uv", "run", "--frozen", "--only-group", "lint", "ruff"}

// ruffReport is what the fake ruff still finds.
const ruffReport = "a.py:1:1: F401 unused\n"

var formatCases = []formatCase{
	{project + "/a.py", func(file, dir string) []fake.Invocation {
		return []fake.Invocation{
			{Command: process.Command{Path: "/b/uv", Args: append(slices.Clone(uvArgs), "format", file), Dir: dir}},
			{Command: process.Command{Path: "/b/uv", Args: append(slices.Clone(uvArgs), "check", "--fix", file), Dir: dir}},
			{
				Command: process.Command{Path: "/b/uv", Args: append(slices.Clone(uvArgs), "check", file), Combined: true, Dir: dir},
				Result:  process.Result{Stdout: []byte(ruffReport), Exit: 1},
			},
		}
	}},
	{project + "/b.go", func(file, dir string) []fake.Invocation {
		return []fake.Invocation{{Command: process.Command{Path: "/b/gofmt", Args: []string{"gofmt", "-w", file}, Dir: dir}}}
	}},
}

// checkFormatter runs the formatter on a tool for a .py and a .go file. On a
// harness that runs hooks in the session's directory the commands run there
// with the path as given; on one that does not, in the project (the
// fixture's workspace), with the file's real path.
func checkFormatter(t *testing.T, harness string, def definition.Definition, tool string) {
	t.Helper()
	roles := members[harness][tool]
	for _, test := range formatCases {
		value, pointer := test.file, roles[rolePath]
		if patchPointer, ok := roles[rolePatch]; ok {
			value, pointer = "*** Begin Patch\n*** Add File: "+test.file+"\n+x\n*** End Patch\n", patchPointer
		}
		dir := ""
		if def.HookCwd != ir.HookCwdSession {
			dir = project
		}
		m := machineFor(test.file, test.commands(test.file, dir))
		got := runBinary(t, m, scenario(t, harness, "post", tool, map[string]any{pointer: value}), harness, "post", "formatter")
		notice := ""
		if strings.HasSuffix(test.file, ".py") {
			notice = "ruff still reports issues in " + test.file + ":\n" + ruffReport
		}
		if got != passed(notice) {
			t.Errorf("%s: %+v, want a pass reporting %q", test.file, got, notice)
		}
		for _, problem := range m.Done() {
			t.Errorf("%s: %s", test.file, problem)
		}
	}
	switch harness {
	case "agy":
		checkAgyPostFailure(t, tool)
	case "pi":
		checkPiPostFailure(t, tool)
	}
}

// machineFor is a machine where file is a regular file in the project, uv
// and gofmt are on PATH, and the commands are what may run.
func machineFor(file string, commands []fake.Invocation) *fake.Machine {
	return &fake.Machine{
		Programs:  map[string]process.Program{"uv": {Path: "/b/uv"}, "gofmt": {Path: "/b/gofmt"}},
		Files:     map[string]bool{file: true},
		RealPaths: map[string]string{file: file, project: project},
		// The binary runs in the project, as the session harnesses and Pi's
		// shim run it.
		Cwd:    project,
		Replay: commands,
	}
}

// checkPiPostFailure: after a call that failed (ok false), Pi's formatter
// answers the pass and runs nothing.
func checkPiPostFailure(t *testing.T, tool string) {
	t.Helper()
	file := project + "/a.py"
	m := machineFor(file, nil)
	payload := scenario(t, "pi", "post", tool, map[string]any{members["pi"][tool][rolePath]: file, "/ok": false})
	if got := runBinary(t, m, payload, "pi", "post", "formatter"); got != passed("") {
		t.Errorf("ok false: %+v, want the pass and nothing run", got)
	}
	for _, problem := range m.Done() {
		t.Errorf("ok false: %s", problem)
	}
}

func TestPiJudgesTheFileItWrites(t *testing.T) {
	// Pi's model names paths relative to the session (the fixtures do), and
	// Pi writes the file resolveToCwd names: the guard judges that file.
	cases := []guardCase{
		{rolePath, "x.yml", true},
		{rolePath, "x.yaml", false},
		{rolePath, "@docker-compose.yaml", true},
		{rolePath, "docs/agents/x.yml", false},
		{rolePath, "sub/../docs/agents/x.yml", false},
	}
	for _, tool := range []string{"write", "edit"} {
		checkGuard(t, "pi", "files-guard", tool, cases)
	}
}

func TestPiChecksEveryReplacementOfAnEdit(t *testing.T) {
	// One edit call may make several replacements; a key in a later one
	// blocks as one in the first does.
	for value, blocks := range map[string]bool{"aws_access_key_id = " + key + "\n": true, "two": false} {
		payload := scenario(t, "pi", "pre", "edit-two", map[string]any{"/input/edits/1/newText": value})
		got := runBinary(t, &fake.Machine{}, payload, "pi", "pre", "secrets-guard")
		if blocks != (got.kind == block) || (blocks && !strings.HasPrefix(got.reason, "BLOCKED: ")) ||
			(!blocks && got != passed("")) {
			t.Errorf("second newText %q: %+v, want blocked %v", value, got, blocks)
		}
	}
}

// checkAgyPostFailure: after a failed call agy's formatter answers {} and
// runs nothing; with error omitted, the call succeeded.
func checkAgyPostFailure(t *testing.T, tool string) {
	t.Helper()
	file := project + "/a.py"
	pointer := members["agy"][tool][rolePath]
	for _, failure := range []any{"write failed", nil} {
		m := machineFor(file, nil)
		payload := scenario(t, "agy", "post", tool, map[string]any{pointer: file, "/error": failure})
		if got := runBinary(t, m, payload, "agy", "post", "formatter"); got != passed("") {
			t.Errorf("error %#v: %+v, want {} and nothing run", failure, got)
		}
		for _, problem := range m.Done() {
			t.Errorf("error %#v: %s", failure, problem)
		}
	}
	m := machineFor(file, formatCases[0].commands(file, project))
	payload := scenario(t, "agy", "post", tool, map[string]any{pointer: file, "/error": omitted})
	if got := runBinary(t, m, payload, "agy", "post", "formatter"); got.kind != pass || got.notice == "" {
		t.Errorf("error omitted: %+v, want the file formatted", got)
	}
	for _, problem := range m.Done() {
		t.Errorf("error omitted: %s", problem)
	}
}

// omitted, as a scenario's value, removes the member.
var omitted = &struct{}{}

// scenario is the harness's fixture for the tool with each value written at
// its pointer. A pointer must name a member the fixture has: a scenario
// changes the tool's own input, and never adds a member that the binary
// might read instead.
func scenario(t *testing.T, harness, event, tool string, values map[string]any) []byte {
	t.Helper()
	file, ok := fixtures[harness][event+"/"+tool]
	if !ok {
		t.Fatalf("%s: no %s fixture for %s", harness, event, tool)
	}
	data, err := fs.ReadFile(harnesses.FS, path.Join(harness, "fixtures", file))
	if err != nil {
		t.Fatal(err)
	}
	var payload any
	if err := json.Unmarshal(data, &payload); err != nil {
		t.Fatal(err)
	}
	before := pointers(payload, "")
	for pointer, value := range values {
		if !slices.Contains(before, pointer) {
			t.Fatalf("%s %s: the fixture has no member at %s", harness, file, pointer)
		}
		set(t, payload, pointer, value)
	}
	if after := pointers(payload, ""); !isSubset(after, before) {
		t.Fatalf("%s %s: a scenario added members: %v", harness, file, after)
	}
	out, err := json.Marshal(payload)
	if err != nil {
		t.Fatal(err)
	}
	return out
}

// set writes value at an object member's pointer, through objects and
// arrays; omitted removes it.
func set(t *testing.T, payload any, pointer string, value any) {
	t.Helper()
	tokens := strings.Split(strings.TrimPrefix(pointer, "/"), "/")
	node := payload
	for _, token := range tokens[:len(tokens)-1] {
		node = child(t, node, token)
	}
	parent, ok := node.(map[string]any)
	if !ok {
		t.Fatalf("%s does not name an object member", pointer)
	}
	if value == omitted {
		delete(parent, tokens[len(tokens)-1])
		return
	}
	parent[tokens[len(tokens)-1]] = value
}

// child is the member or the array element a pointer's token names.
func child(t *testing.T, node any, token string) any {
	t.Helper()
	switch node := node.(type) {
	case map[string]any:
		return node[token]
	case []any:
		i, err := strconv.Atoi(token)
		if err != nil || i < 0 || i >= len(node) {
			t.Fatalf("no element %s", token)
		}
		return node[i]
	default:
		t.Fatalf("no member %s", token)
		return nil
	}
}

// pointers lists the JSON Pointers of every object member under node.
func pointers(node any, at string) []string {
	var found []string
	switch node := node.(type) {
	case map[string]any:
		for name, child := range node {
			here := at + "/" + name
			found = append(found, here)
			found = append(found, pointers(child, here)...)
		}
	case []any:
		for i, child := range node {
			found = append(found, pointers(child, at+"/"+strconv.Itoa(i))...)
		}
	}
	return found
}

func isSubset(sub, of []string) bool {
	for _, item := range sub {
		if !slices.Contains(of, item) {
			return false
		}
	}
	return true
}

// runBinary runs the binary in-process and reads its answer as the harness
// does.
func runBinary(t *testing.T, m *fake.Machine, payload []byte, harness, event, hook string) verdict {
	t.Helper()
	var stdout, stderr bytes.Buffer
	exit := launch.Run([]string{harness, event, "--hook", hook}, bytes.NewReader(payload), &stdout, &stderr, m)
	return readers[harness][event](answer{exit: exit, stdout: stdout.String(), stderr: stderr.String()})
}
