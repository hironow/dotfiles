package launch

import (
	"path"
	"strings"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/project"
)

// locate places a file named by a call on a harness that runs its hooks
// outside the session's directory: the file's real path, and the project
// directory to run its programs in (project.Directory). It finds the
// candidates on the machine, each resolved physically, so a symlink cannot
// lead the file out of a workspace unseen. ok is false for a file it cannot
// place: a relative path (agy's payload has no cwd to read it against), a
// path that does not resolve, or any path on Windows, which 2d does not cover.
func locate(call ir.Call, file string, machine Machine) (dir, real string, ok bool) {
	if machine.IsWindows() || !strings.HasPrefix(file, "/") {
		return "", "", false
	}
	real, err := machine.RealPath(file)
	if err != nil {
		return "", "", false
	}
	var workspaces []string
	for _, workspace := range call.Lists[ir.ListWorkspaces] {
		if !workspace.IsString || !strings.HasPrefix(workspace.Text, "/") {
			continue
		}
		if resolved, err := machine.RealPath(workspace.Text); err == nil {
			workspaces = append(workspaces, resolved)
		}
	}
	return project.Directory(project.Candidates{
		File:       real,
		Workspaces: workspaces,
		GitRoot:    gitRoot(path.Dir(real), machine),
	}), real, true
}

// gitRoot looks for the nearest directory, from dir up, that holds a .git
// entry (a directory, or the file a worktree or submodule has).
func gitRoot(dir string, machine Machine) project.Lookup {
	for {
		found, err := machine.Exists(path.Join(dir, ".git"))
		if err != nil {
			return project.Lookup{Failed: true}
		}
		if found {
			return project.Lookup{Path: dir}
		}
		parent := path.Dir(dir)
		if parent == dir {
			return project.Lookup{}
		}
		dir = parent
	}
}
