package main_test

import (
	"bytes"
	"errors"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/toolhookcorpus"
)

func TestOnAgyTheFormatterRunsInTheFilesProjectAsARealProcess(t *testing.T) {
	// agy runs a hook in the directory that holds hooks.json (plugin here),
	// so the formatter finds the project itself, on the real file system:
	//   ws/c.py              in the workspace: uv runs in ws
	//   ws/link -> other/sub  a symlink out of the workspace
	//   ws/link/../a.go      is other/a.go: gofmt runs in other, its git root
	//   other/deep/b.go      outside the workspace, no .git beside it: other
	skipWithoutPOSIXShell(t)
	root, err := filepath.EvalSymlinks(t.TempDir())
	mustDo(t, err)
	sub := func(text string) string { return strings.ReplaceAll(text, toolhookcorpus.Root, root) }
	reported := &toolhookcorpus.Answer{Stdout: []byte("c.py:1:1: F401 unused\n"), Exit: 1}
	build(t, root, toolhookcorpus.Environment{
		Dirs:  []string{"ws", "other/sub", "other/deep", "other/.git", "plugin"},
		Files: map[string]string{"ws/c.py": "import os\n", "other/a.go": "package a\n", "other/deep/b.go": "package b\n"},
		Links: map[string]string{"ws/link": toolhookcorpus.Root + "/other/sub"},
		Fakes: map[string]toolhookcorpus.Rule{
			"fake-bin/gofmt": {},
			"fake-bin/uv":    {Default: reported},
		},
	}, sub)
	tests := []struct {
		file        string
		stderr      string
		invocations []toolhookcorpus.Invocation
	}{
		{
			file:   "@ROOT@/ws/c.py",
			stderr: "ruff still reports issues in @ROOT@/ws/c.py:\nc.py:1:1: F401 unused\n",
			invocations: []toolhookcorpus.Invocation{
				uvIn("@ROOT@/ws", "format", "@ROOT@/ws/c.py"),
				uvIn("@ROOT@/ws", "check", "--fix", "@ROOT@/ws/c.py"),
				uvIn("@ROOT@/ws", "check", "@ROOT@/ws/c.py"),
			},
		},
		{
			file: "@ROOT@/ws/link/../a.go",
			invocations: []toolhookcorpus.Invocation{{
				Tool: "fake-bin/gofmt", Path: "@ROOT@/fake-bin/gofmt", Args: []string{"-w", "@ROOT@/other/a.go"},
				Cwd: "@ROOT@/other",
			}},
		},
		{
			file: "@ROOT@/other/deep/b.go",
			invocations: []toolhookcorpus.Invocation{{
				Tool: "fake-bin/gofmt", Path: "@ROOT@/fake-bin/gofmt", Args: []string{"-w", "@ROOT@/other/deep/b.go"},
				Cwd: "@ROOT@/other",
			}},
		},
	}
	for _, test := range tests {
		mustDo(t, removeLog(root))
		payload := `{"toolCall":{"name":"write_file","args":{"Path":"` + test.file + `","Content":""}},` +
			`"workspacePaths":["@ROOT@/ws"],"error":""}`
		// Audited: binary is the agent-hook this test built, with fixed
		// arguments.
		// nosemgrep: go.lang.security.audit.dangerous-exec-command.dangerous-exec-command
		command := exec.Command(binary, "agy", "post", "--hook", "formatter")
		command.Dir = filepath.Join(root, "plugin")
		command.Env = []string{
			"PATH=" + filepath.Join(root, "fake-bin") + ":" + filepath.Join(root, "sys-bin"),
			"HOME=" + filepath.Join(root, "home"), "LC_ALL=C.UTF-8",
		}
		command.Stdin = strings.NewReader(sub(payload))
		var stdout, stderr bytes.Buffer
		command.Stdout, command.Stderr = &stdout, &stderr
		if err := command.Run(); err != nil {
			t.Fatalf("%s: run: %v (stderr %q)", test.file, err, stderr.String())
		}
		if stdout.String() != "{}\n" || stderr.String() != sub(test.stderr) {
			t.Errorf("%s: answer %q, stderr %q; want {} and %q", test.file, stdout.String(), stderr.String(), sub(test.stderr))
		}
		checkInvocations(t, test.file, root, test.invocations, sub)
	}
}

// removeLog clears faketool's log, so each run in one root reads its own.
func removeLog(root string) error {
	if err := os.Remove(filepath.Join(root, "invocations.jsonl")); err != nil && !errors.Is(err, fs.ErrNotExist) {
		return err
	}
	return nil
}

// uvIn is the fake uv's invocation running ruff with args, in dir.
func uvIn(dir string, args ...string) toolhookcorpus.Invocation {
	return toolhookcorpus.Invocation{
		Tool: "fake-bin/uv", Path: "@ROOT@/fake-bin/uv",
		Args: append([]string{"run", "--frozen", "--only-group", "lint", "ruff"}, args...),
		Cwd:  dir,
	}
}
