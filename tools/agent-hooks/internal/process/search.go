// Package process holds what the binary's shell asks of the machine about
// programs: how a program is found on PATH, a command to run, and its result.
// The launch.Machine port speaks in these values, so that its fake (in
// internal/fake) and its real adapter (in launch) share them.
package process

import (
	"strings"
	"time"
)

// Program is a program found on PATH. Relative is true when the PATH entry
// it was found through is relative (empty, ".", or not starting with "/"):
// the old scripts ran it from the current directory. The binary never runs
// such a program, and does not look for another copy in its place either.
type Program struct {
	Path     string
	Relative bool
}

// Search finds name on pathEnv as Python's shutil.which and bash do on
// Unix: each entry in order, joined to the name as os.path.join joins them,
// without cleaning, so that the kernel resolves "link/.." through the link,
// as it did for the scripts. The first executable non-directory wins. An
// empty PATH finds nothing.
func Search(pathEnv, name string, isExecutable func(string) bool) (Program, bool) {
	if pathEnv == "" {
		return Program{}, false
	}
	for dir := range strings.SplitSeq(pathEnv, ":") {
		path := joinAsPython(dir, name)
		if isExecutable(path) {
			return Program{Path: path, Relative: !strings.HasPrefix(dir, "/")}, true
		}
	}
	return Program{}, false
}

// joinAsPython is os.path.join(dir, name) for a name without a slash: the
// name alone for an empty dir, no second slash after one that ends dir.
func joinAsPython(dir, name string) string {
	if dir == "" || strings.HasSuffix(dir, "/") {
		return dir + name
	}
	return dir + "/" + name
}

// Command is one program to run. Args is the whole argv, the program's own
// name first, as the old scripts passed it. The command always runs in the
// binary's own environment, as the scripts' commands did, so there is no
// field to change it.
type Command struct {
	Path    string
	Args    []string
	Stdin   []byte
	Timeout time.Duration // zero: no timeout
	// Combined puts stdout and stderr on one pipe, as `2>&1` does;
	// Result.Stdout then holds both, in the order they were written.
	Combined bool
	// Dir is the directory to run in; "" is the binary's own, where the old
	// scripts ran theirs. Only a harness that runs its hooks outside the
	// session's directory (agy) sets it.
	Dir string
}

// Result is what a command did.
type Result struct {
	Stdout, Stderr []byte
	Exit           int
	// Signaled is set when a signal ended the program; Exit is then -1.
	Signaled bool
}
