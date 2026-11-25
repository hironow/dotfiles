// Package load reads the rules' inputs from the repository: the port Source
// and its adapter Files.
package load

import (
	"bytes"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"github.com/goccy/go-json"
	"github.com/hironow/dotfiles/tools/repo-lint/internal/rules"
)

// Source gives each input of a rule as a decoded value.
type Source interface {
	Load(in rules.Input) (any, error)
}

// Files reads inputs from the repository at Root. YQ is the yq executable
// (mikefarah/yq, pinned by mise) that turns TOML and YAML into JSON, so no
// TOML or YAML library enters this module.
type Files struct {
	Root string
	YQ   string
	Git  string
}

// Load reads one input. A glob input becomes a map from each tracked file
// the pathspec matches to its decoded value: `git ls-files` lists the files,
// so nothing untracked (a scratch copy, a dependency folder) is read.
func (f Files) Load(in rules.Input) (any, error) {
	if in.Glob {
		return f.glob(in)
	}
	return f.one(in)
}

func (f Files) glob(in rules.Input) (any, error) {
	git := f.Git
	if git == "" {
		git = "git"
	}
	var stderr bytes.Buffer
	// Audited: git with fixed arguments and a rule's pathspec. No shell runs.
	// nosemgrep: dangerous-exec-command, go.lang.security.audit.dangerous-exec-command.dangerous-exec-command
	cmd := exec.Command(git, "-C", f.Root, "ls-files", "-z", "--", ":(glob)"+in.Path) //nolint:gosec // G204: audited above.
	cmd.Stderr = &stderr
	out, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("git ls-files %s: %w: %s", in.Path, err, bytes.TrimSpace(stderr.Bytes()))
	}
	files := map[string]any{}
	for name := range strings.SplitSeq(strings.TrimSuffix(string(out), "\x00"), "\x00") {
		if name == "" {
			continue
		}
		v, err := f.one(rules.Input{Path: name, Format: in.Format})
		if err != nil {
			return nil, err
		}
		files[name] = v
	}
	return files, nil
}

func (f Files) one(in rules.Input) (any, error) {
	path := filepath.Join(f.Root, filepath.FromSlash(in.Path))
	switch in.Format {
	case rules.Text:
		data, err := os.ReadFile(path) //nolint:gosec // G304: a fixed input path of a rule, under the repository root.
		if err != nil {
			return nil, fmt.Errorf("read %s: %w", in.Path, err)
		}
		// A Windows checkout may have CRLF line ends (core.autocrlf); the
		// rules read the text as git stores it.
		return strings.ReplaceAll(string(data), "\r\n", "\n"), nil
	case rules.JSON:
		data, err := os.ReadFile(path) //nolint:gosec // G304: as above.
		if err != nil {
			return nil, fmt.Errorf("read %s: %w", in.Path, err)
		}
		return decode(in.Path, data)
	case rules.TOML, rules.YAML:
		var stderr bytes.Buffer
		// Audited: the executable is the pinned yq the gate names (--yq), and
		// the arguments are fixed apart from a rule's input path. No shell runs.
		// nosemgrep: dangerous-exec-command, go.lang.security.audit.dangerous-exec-command.dangerous-exec-command
		cmd := exec.Command(f.YQ, "-p", string(in.Format), "-o", "json", ".", path) //nolint:gosec // G204: audited above.
		cmd.Stderr = &stderr
		out, err := cmd.Output()
		if err != nil {
			return nil, fmt.Errorf("yq %s: %w: %s", in.Path, err, bytes.TrimSpace(stderr.Bytes()))
		}
		return decode(in.Path, out)
	default:
		return nil, fmt.Errorf("%s: unknown format %q", in.Path, in.Format)
	}
}

func decode(path string, data []byte) (any, error) {
	var v any
	if err := json.Unmarshal(data, &v); err != nil {
		return nil, fmt.Errorf("decode %s: %w", path, err)
	}
	return v, nil
}
