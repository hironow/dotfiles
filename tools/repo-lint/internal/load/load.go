// Package load reads the rules' inputs from the repository: the port Source
// and its adapter Files.
package load

import (
	"bytes"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"syscall"

	"github.com/goccy/go-json"
	"github.com/hironow/dotfiles/tools/repo-lint/internal/jsonc"
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
	if in.FilesystemGlob {
		return f.filesystemGlob(in)
	}
	if in.Glob {
		return f.glob(in)
	}
	return f.one(in)
}

func (f Files) filesystemGlob(in rules.Input) (any, error) {
	return f.filesystemGlobCase(in, runtime.GOOS != "windows")
}

func (f Files) filesystemGlobCase(in rules.Input, caseSensitive bool) (any, error) {
	dir, pattern := filepath.Split(filepath.FromSlash(in.Path))
	if strings.ContainsAny(dir, "*?[") {
		return nil, fmt.Errorf("%s: filesystem glob must name one directory", in.Path)
	}
	names, err := filepath.Glob(filepath.Join(f.Root, dir, pattern))
	if err != nil {
		return nil, fmt.Errorf("glob %s: %w", in.Path, err)
	}
	if !caseSensitive {
		entries, err := os.ReadDir(filepath.Join(f.Root, dir))
		if err != nil && !os.IsNotExist(err) {
			return nil, fmt.Errorf("glob %s: %w", in.Path, err)
		}
		names = nil
		for _, entry := range entries {
			// pathlib uses case-insensitive matching on Windows. These
			// globs have a literal ASCII extension. Upper then lower also
			// folds the long s in *.ps1, as Python's re.IGNORECASE does.
			folded := strings.ToLower(strings.ToUpper(entry.Name()))
			matched, err := filepath.Match(strings.ToLower(pattern), folded)
			if err != nil {
				return nil, fmt.Errorf("glob %s: %w", in.Path, err)
			}
			if matched {
				names = append(names, filepath.Join(f.Root, dir, entry.Name()))
			}
		}
	}
	files := map[string]any{}
	for _, name := range names {
		rel, err := filepath.Rel(f.Root, name)
		if err != nil {
			return nil, fmt.Errorf("glob %s: %w", in.Path, err)
		}
		rel = filepath.ToSlash(rel)
		value, err := f.one(rules.Input{Path: rel, Format: in.Format})
		if err != nil {
			return nil, err
		}
		files[rel] = value
	}
	return files, nil
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
	case rules.Directories:
		return directoryNames(path)
	case rules.Text:
		if in.Optional {
			info, err := os.Stat(path)
			if os.IsNotExist(err) || errors.Is(err, syscall.ENOTDIR) || err == nil && !info.Mode().IsRegular() {
				return nil, nil
			}
			if err != nil {
				return nil, fmt.Errorf("stat %s: %w", in.Path, err)
			}
		}
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
	case rules.JSONC:
		data, err := os.ReadFile(path) //nolint:gosec // G304: as above.
		if err != nil {
			return nil, fmt.Errorf("read %s: %w", in.Path, err)
		}
		v, err := jsonc.Decode(string(data))
		if err != nil {
			return nil, fmt.Errorf("%s: %w", in.Path, err)
		}
		return v, nil
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

func directoryNames(path string) ([]string, error) {
	entries, err := os.ReadDir(path)
	if err != nil {
		return nil, fmt.Errorf("list %s: %w", path, err)
	}
	names := []string{}
	for _, entry := range entries {
		// Path.is_dir follows symlinks and treats a failed stat as false.
		info, err := os.Stat(filepath.Join(path, entry.Name()))
		if err == nil && info.IsDir() {
			names = append(names, entry.Name())
		}
	}
	return names, nil
}

func decode(path string, data []byte) (any, error) {
	var v any
	if err := json.Unmarshal(data, &v); err != nil {
		return nil, fmt.Errorf("decode %s: %w", path, err)
	}
	return v, nil
}
