// Package load reads the rules' inputs from the repository: the port Source
// and its adapter Files.
package load

import (
	"bytes"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"

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
}

// Load reads one input.
func (f Files) Load(in rules.Input) (any, error) {
	path := filepath.Join(f.Root, filepath.FromSlash(in.Path))
	switch in.Format {
	case rules.Text:
		data, err := os.ReadFile(path) //nolint:gosec // G304: a fixed input path of a rule, under the repository root.
		if err != nil {
			return nil, fmt.Errorf("read %s: %w", in.Path, err)
		}
		return string(data), nil
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
