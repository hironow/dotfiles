package ir

// The IR fields a harness definition maps (its "x-ir"), by name.
const (
	FieldCommand  = "command"  // a shell command, or Codex's apply_patch patch
	FieldFilePath = "filePath" // the path a write or edit names
	FieldContent  = "content"  // the text a write, edit, or notebook edit puts in
)

// The kinds of tool a harness definition maps its tool names to.
const (
	KindShell    = "shell"    // runs a shell command
	KindWrite    = "write"    // writes a whole file
	KindEdit     = "edit"     // replaces text in a file
	KindNotebook = "notebook" // edits a notebook cell
	KindPatch    = "patch"    // applies a patch to one or more files
)

// Call is one tool call as the hooks see it, the same for every harness.
type Call struct {
	Harness string // the harness's name, such as "claude"
	Event   string // the event, such as "pre"
	Tool    string // the harness's own tool name, such as "Bash"
	Kind    string // what the tool does (Kind*); empty when the definition does not map the tool
	// Fields holds the IR fields the definition maps, by name (Field*). A
	// field whose candidates are all absent, null, or false is missing.
	Fields map[string]Value
}

// Value is one IR field's value. Text is the string itself, or, for any other
// JSON value, the value printed as compact JSON text, with its strings escaped
// as jq escapes them: a control character stays escaped (a NUL is \u0000).
type Value struct {
	Text     string
	IsString bool
}
