package launch_test

import (
	"testing"

	json "github.com/goccy/go-json/v2"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/fake"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/process"
)

// piProject is the cwd of the Pi requests here.
const piProject = "/home/user/project"

// piWrite is Pi's write of a path, as its shim sends it.
func piWrite(t *testing.T, event, path string) string {
	t.Helper()
	input, err := json.Marshal(map[string]string{"path": path, "content": "x\n"})
	if err != nil {
		t.Fatal(err)
	}
	return piRequest(event, "write", string(input))
}

const (
	composeReason    = "BLOCKED: 'docker-compose.yaml' is the deprecated Compose v1 name. Use 'compose.yaml' (Compose Spec v2+)."
	ymlReasonFor     = "BLOCKED: 'x.yml' uses '.yml'. This project uses '.yaml' exclusively. Rename to 'x.yaml'."
	unresolvedPrefix = "BLOCKED: agent-hook cannot tell which file Pi writes for the path "
)

// shimBlock is the block answer, its members in the order the answer
// template writes them.
func shimBlock(reason string) string {
	quoted, _ := json.Marshal(reason)
	return `{"v":1,"action":"block","reason":` + string(quoted) + "}\n"
}

func TestPiResolvesAPathBeforeTheFilesGuardReadsIt(t *testing.T) {
	// Pi writes the file resolveToCwd names (internal/pipath), so the files
	// guard judges that file: the cwd joins a relative path, one leading @
	// goes, ~ is the home directory, and a plain file: URL is its path.
	home := &fake.Machine{Home: "/home/user", HasHome: true}
	cases := []struct {
		path string
		want string // the answer's stdout
	}{
		{"x.yml", shimBlock(ymlReasonFor)},
		{"x.yaml", shimPass},
		{"@docker-compose.yaml", shimBlock(composeReason)},
		// resolved, it is under a docs/agents/ directory
		{"docs/agents/x.yml", shimPass},
		{"../project/docs/agents/x.yml", shimPass},
		{"~/x.yml", shimBlock(ymlReasonFor)},
		{"file:///home/user/project/x.yml", shimBlock(ymlReasonFor)},
		{"/elsewhere/AGENTS.md", shimPass},
	}
	for _, c := range cases {
		if got := run(t, home, piWrite(t, "pre", c.path), "pi", "pre", "--hook", "files-guard"); got != (result{stdout: c.want}) {
			t.Errorf("%q: %+v, want stdout %q", c.path, got, c.want)
		}
	}
}

func TestPiPathThatCannotBeResolvedAsPiDoesBlocks(t *testing.T) {
	// The port refuses what it cannot match Pi on: a file: URL outside the
	// plain form, and ~ where the home directory is unknown. The files
	// guard then cannot judge the file, so it blocks.
	cases := []struct {
		machine *fake.Machine
		path    string
	}{
		{&fake.Machine{}, "~/x.md"},
		{&fake.Machine{Home: "/home/user", HasHome: true}, "file:///w/a.md?x"},
		{&fake.Machine{Home: "/home/user", HasHome: true}, "file://host/w/a.md"},
	}
	for _, c := range cases {
		got := run(t, c.machine, piWrite(t, "pre", c.path), "pi", "pre", "--hook", "files-guard")
		var answer struct {
			V      int    `json:"v"`
			Action string `json:"action"`
			Reason string `json:"reason"`
		}
		if err := json.Unmarshal([]byte(got.stdout), &answer); err != nil || answer.Action != "block" ||
			len(answer.Reason) < len(unresolvedPrefix) || answer.Reason[:len(unresolvedPrefix)] != unresolvedPrefix {
			t.Errorf("%q: %+v, want a block for a path that cannot be resolved", c.path, got)
		}
	}
	// A path that is not a string names no file: nothing to resolve.
	payload := piRequest("pre", "write", `{"path":1,"content":"x"}`)
	if got := run(t, &fake.Machine{}, payload, "pi", "pre", "--hook", "files-guard"); got != (result{stdout: shimPass}) {
		t.Errorf("a path that is not a string: %+v, want the pass", got)
	}
}

// piGofmt is a machine where gofmt is on PATH, the Go file is a regular
// file, and the binary runs in the project.
func piGofmt(cwd string, replay ...fake.Invocation) *fake.Machine {
	return &fake.Machine{
		Programs:  map[string]process.Program{"gofmt": {Path: "/b/gofmt"}},
		Files:     map[string]bool{piProject + "/a.go": true},
		RealPaths: map[string]string{piProject + "/a.go": piProject + "/a.go", piProject: piProject},
		Cwd:       cwd,
		Home:      "/home/user",
		HasHome:   true,
		Replay:    replay,
	}
}

func TestPiFormatsTheResolvedFileInTheRequestsCwd(t *testing.T) {
	// The shim runs the binary in the request's cwd; the formatter checks it
	// does (physically), so that ruff and gofmt never run against another
	// project, and formats the file Pi wrote, by its resolved path.
	gofmt := fake.Invocation{Command: process.Command{Path: "/b/gofmt", Args: []string{"gofmt", "-w", piProject + "/a.go"}}}
	for _, path := range []string{"a.go", "@a.go", piProject + "/a.go", "file://" + piProject + "/a.go"} {
		m := piGofmt(piProject, gofmt)
		if got := run(t, m, piWrite(t, "post", path), "pi", "post", "--hook", "formatter"); got != (result{stdout: shimPass}) {
			t.Errorf("%q: %+v, want the pass", path, got)
		}
		checkReplay(t, m)
	}
	// Run anywhere else, or where the cwd does not resolve, it runs nothing.
	for _, m := range []*fake.Machine{piGofmt("/elsewhere"), piGofmt("")} {
		if got := run(t, m, piWrite(t, "post", "a.go"), "pi", "post", "--hook", "formatter"); got != (result{stdout: shimPass}) {
			t.Errorf("cwd %q: %+v, want the pass and nothing run", m.Cwd, got)
		}
		checkReplay(t, m)
	}
	m := piGofmt(piProject)
	delete(m.RealPaths, piProject)
	if got := run(t, m, piWrite(t, "post", "a.go"), "pi", "post", "--hook", "formatter"); got != (result{stdout: shimPass}) {
		t.Errorf("a cwd that does not resolve: %+v, want the pass and nothing run", got)
	}
	checkReplay(t, m)
	// A path that cannot be resolved as Pi does names no file to format, not
	// even the file its text names from the binary's cwd: Pi writes under
	// its own home, which the binary could not find.
	m = piGofmt(piProject)
	m.HasHome = false
	m.Files["~/a.go"] = true
	if got := run(t, m, piWrite(t, "post", "~/a.go"), "pi", "post", "--hook", "formatter"); got != (result{stdout: shimPass}) {
		t.Errorf("~ with no home: %+v, want the pass and nothing run", got)
	}
	checkReplay(t, m)
	// After a failed call, nothing runs.
	m = piGofmt(piProject)
	failed := piRequest("post", "write", `{"path":"a.go","content":"x"}`)
	failed = failed[:len(failed)-len(`"ok":true}`)] + `"ok":false}`
	if got := run(t, m, failed, "pi", "post", "--hook", "formatter"); got != (result{stdout: shimPass}) {
		t.Errorf("a failed call: %+v, want the pass and nothing run", got)
	}
	checkReplay(t, m)
}
