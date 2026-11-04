package project_test

import (
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/project"
)

func TestDirectoryPicksTheLongestWorkspaceThenTheGitRootThenTheFilesDirectory(t *testing.T) {
	gitRoot := func(path string) project.Lookup { return project.Lookup{Path: path} }
	tests := []struct {
		name string
		in   project.Candidates
		want string
	}{
		{
			"a workspace holds the file",
			project.Candidates{File: "/ws/a.py", Workspaces: []string{"/ws"}, GitRoot: gitRoot("/")},
			"/ws",
		},
		{
			"the longest of nested workspaces",
			project.Candidates{File: "/ws/sub/a.py", Workspaces: []string{"/ws", "/ws/sub"}},
			"/ws/sub",
		},
		{
			"nested workspaces in the other order",
			project.Candidates{File: "/ws/sub/a.py", Workspaces: []string{"/ws/sub", "/ws"}},
			"/ws/sub",
		},
		{
			"the outer of nested workspaces",
			project.Candidates{File: "/ws/a.py", Workspaces: []string{"/ws/sub", "/ws"}},
			"/ws",
		},
		{
			"several workspaces, one holds the file",
			project.Candidates{File: "/b/x/a.py", Workspaces: []string{"/a", "/b", "/c"}},
			"/b",
		},
		{
			"a prefix that is not a parent",
			project.Candidates{File: "/ws2/a.py", Workspaces: []string{"/ws"}, GitRoot: gitRoot("/ws2")},
			"/ws2",
		},
		{
			"a workspace that is the file itself",
			project.Candidates{File: "/ws/a.py", Workspaces: []string{"/ws/a.py"}},
			"/ws",
		},
		{
			"the root as a workspace",
			project.Candidates{File: "/a.py", Workspaces: []string{"/"}},
			"/",
		},
		{
			"outside every workspace: the git root",
			project.Candidates{File: "/repo/sub/a.py", Workspaces: []string{"/ws"}, GitRoot: gitRoot("/repo")},
			"/repo",
		},
		{
			"no workspace: the git root",
			project.Candidates{File: "/repo/a.py", GitRoot: gitRoot("/repo")},
			"/repo",
		},
		{
			"no git root: the file's directory",
			project.Candidates{File: "/tmp/x/a.py", Workspaces: []string{"/ws"}},
			"/tmp/x",
		},
		{
			"a failed git lookup: the file's directory",
			project.Candidates{File: "/tmp/x/a.py", GitRoot: project.Lookup{Failed: true}},
			"/tmp/x",
		},
		{
			"a failed lookup that found a path is still failed",
			project.Candidates{File: "/tmp/x/a.py", GitRoot: project.Lookup{Path: "/tmp", Failed: true}},
			"/tmp/x",
		},
		{
			"a file in the root",
			project.Candidates{File: "/a.py"},
			"/",
		},
	}
	for _, test := range tests {
		if got := project.Directory(test.in); got != test.want {
			t.Errorf("%s: Directory(%+v) = %q, want %q", test.name, test.in, got, test.want)
		}
	}
}
