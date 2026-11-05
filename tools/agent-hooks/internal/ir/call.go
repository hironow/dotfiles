package ir

// The IR fields a harness definition maps (its "x-ir"), by name.
const (
	FieldCommand  = "command"  // a shell command, or Codex's apply_patch patch
	FieldFilePath = "filePath" // the path a write or edit names
	// FieldNotebookPath is NotebookEdit's notebook_path, which the old files
	// guard never read (fixed-notebook-path).
	FieldNotebookPath = "notebookPath"
	FieldContent      = "content" // the text a write, edit, or notebook edit puts in
	FieldCwd          = "cwd"     // the tool call's working directory, as the harness gave it
	// FieldSessionID and FieldCallID are the session's id and the tool call's
	// id, as the harness gave them. No hook reads them; the log hashes them
	// into a trace id that a call's pre and post lines share.
	FieldSessionID = "sessionId"
	FieldCallID    = "callId"
)

// The IR list fields a harness definition maps: a pointer with a "*" in its
// "x-ir", read for every element of an array.
const (
	ListWorkspaces = "workspaces" // the session's workspace directories, as the harness gave them
	// ListContents is each text an edit puts in, for a tool that makes several
	// replacements in one call (Pi's edit: each newText).
	ListContents = "contents"
)

// The kinds of tool a harness definition maps its tool names to.
const (
	KindShell    = "shell"    // runs a shell command
	KindWrite    = "write"    // writes a whole file
	KindEdit     = "edit"     // replaces text in a file
	KindNotebook = "notebook" // edits a notebook cell
	KindPatch    = "patch"    // applies a patch to one or more files
)

// Where a harness runs its hooks (a harness definition's "hookCwd").
const (
	HookCwdSession      = "session"      // in the session's directory
	HookCwdRegistration = "registration" // in the directory of the file that registers the hook
)

// How a harness reaches the binary (a harness definition's "transport").
const (
	TransportCommand = "command" // the harness runs the binary as a command, with its own payload
	TransportShim    = "shim"    // an extension inside the harness sends a shim protocol request (tools/agent-hooks/shim)
)

// How a harness turns a tool's path into the file the tool touches (a
// harness definition's "pathResolution").
const (
	PathsAsGiven = "as-given" // the path names the file as it is
	PathsPi      = "pi"       // Pi resolves the path first, against the call's cwd (internal/pipath)
)

// Call is one tool call as the hooks see it, the same for every harness.
type Call struct {
	Harness string // the harness's name, such as "claude"
	Event   string // the event, such as "pre"
	HookCwd string // where the harness runs the hook (HookCwd*)
	// Transport is how the harness reaches the binary (Transport*).
	Transport string
	// PathResolution is how the harness turns a tool's path into the file it
	// touches (Paths*).
	PathResolution string
	Tool           string // the harness's own tool name, such as "Bash"
	Kind           string // what the tool does (Kind*); empty when the definition does not map the tool
	// Fields holds the IR fields the definition maps, by name (Field*). A
	// field whose candidates are all absent, null, or false is missing.
	Fields map[string]Value
	// Lists holds the IR list fields the definition maps, by name (List*):
	// every element taken, in order. A list with no element taken is missing.
	Lists map[string][]Value
	// ToolFailed is set on a post call whose payload the definition's success
	// signal ("x-success") reads as a failed tool call.
	ToolFailed bool
	// PathUnresolved is set by the shell on a harness that resolves a tool's
	// path before it writes (PathsPi), when the file path cannot be resolved
	// as the harness resolves it: no hook can tell which file the tool
	// touches.
	PathUnresolved bool
	// Native is the payload as the harness wrote it. Only a delegate hook,
	// which hands the payload to the delegate, reads it.
	Native []byte
}

// Value is one IR field's value. Text is the string itself, or, for any other
// JSON value, the value printed as compact JSON text, with its strings escaped
// as jq escapes them: a control character stays escaped (a NUL is \u0000).
type Value struct {
	Text     string
	IsString bool
}
