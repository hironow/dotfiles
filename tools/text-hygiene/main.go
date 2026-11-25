// text-hygiene checks repository text without rewriting it (ADR 0085).
package main

import (
	"bytes"
	"errors"
	"flag"
	"fmt"
	"io"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"unicode/utf8"
)

// Match the existing prek global exclusion expression, plus the retired
// fixers' vendor exclusion. In particular, changelogs.md is a prefix match.
var excluded = regexp.MustCompile(`^(emulator/|gcloud/|knowledge-work-plugins/|protocols/|skills/|/private/|output/|node_modules/|\.venv/|tools/rttm/\.venv/|docs/changelogs\.md|site/vendor/)`)

func main() {
	os.Exit(run(os.Args[1:], os.Stderr))
}

func run(args []string, stderr io.Writer) int {
	flags := flag.NewFlagSet("text-hygiene", flag.ContinueOnError)
	flags.SetOutput(stderr)
	rootArg := flags.String("root", ".", "Git root to check (default: discover from current directory)")
	if err := flags.Parse(args); err != nil {
		return 1
	}
	exactRoot := false
	flags.Visit(func(f *flag.Flag) {
		if f.Name == "root" {
			exactRoot = true
		}
	})
	root, err := gitRoot(*rootArg, exactRoot)
	if err != nil {
		fmt.Fprintln(stderr, err)
		return 1
	}
	paths := flags.Args()
	explicit := len(paths) > 0
	if !explicit {
		paths, err = trackedFiles(root)
		if err != nil {
			fmt.Fprintln(stderr, err)
			return 1
		}
	}
	tree, err := os.OpenRoot(root)
	if err != nil {
		fmt.Fprintln(stderr, err)
		return 1
	}
	defer tree.Close()
	failed := false
	for _, name := range paths {
		messages, scanErr := scanFile(tree, name, explicit)
		if scanErr != nil {
			fmt.Fprintf(stderr, "text hygiene: %v\n", scanErr)
			failed = true
		}
		for _, message := range messages {
			fmt.Fprintln(stderr, message)
			failed = true
		}
	}
	if failed {
		fmt.Fprintln(stderr, "text hygiene: fix the reported files explicitly; this gate never rewrites source files or the Git index (ADR 0085)")
		return 1
	}
	return 0
}

func gitRoot(dir string, exact bool) (string, error) {
	cmd := exec.Command("git", "rev-parse", "--show-toplevel")
	cmd.Dir = dir
	out, err := cmd.Output()
	if err != nil {
		return "", fmt.Errorf("text hygiene: discover Git root: %w", err)
	}
	root := filepath.Clean(strings.TrimRight(string(out), "\r\n"))
	if exact {
		requested, statErr := os.Stat(dir)
		if statErr != nil {
			return "", statErr
		}
		top, statErr := os.Stat(root)
		if statErr != nil {
			return "", statErr
		}
		if !os.SameFile(requested, top) {
			return "", errors.New("text hygiene: --root must name the Git top-level directory")
		}
	}
	return root, nil
}

func trackedFiles(root string) ([]string, error) {
	cmd := exec.Command("git", "ls-files", "-z")
	cmd.Dir = root
	out, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("text hygiene: list tracked files: %w", err)
	}
	if len(out) == 0 {
		return nil, nil
	}
	return strings.Split(strings.TrimSuffix(string(out), "\x00"), "\x00"), nil
}

// os.Root constrains reads even if a path changes after its symlink checks.
func scanFile(tree *os.Root, name string, explicit bool) ([]string, error) {
	if !filepath.IsLocal(name) {
		return nil, fmt.Errorf("path must be relative and inside the Git root: %q", name)
	}
	name = filepath.Clean(name)
	if excluded.MatchString(filepath.ToSlash(name)) {
		return nil, nil
	}
	var info fs.FileInfo
	var err error
	prefix := ""
	for _, part := range strings.Split(name, string(filepath.Separator)) {
		prefix = filepath.Join(prefix, part)
		info, err = tree.Lstat(prefix)
		if err != nil {
			if !explicit && errors.Is(err, fs.ErrNotExist) {
				return nil, nil // A tracked file removed from the working tree.
			}
			return nil, fmt.Errorf("inspect %q: %w", name, err)
		}
		if info.Mode()&os.ModeSymlink != 0 {
			return nil, nil
		}
	}
	if !info.Mode().IsRegular() {
		if explicit {
			return nil, fmt.Errorf("not a regular file: %q", name)
		}
		return nil, nil // Gitlinks are directories, not parent-repo text.
	}
	data, err := tree.ReadFile(name)
	if err != nil {
		return nil, fmt.Errorf("read %q: %w", name, err)
	}
	return violations(filepath.ToSlash(name), data), nil
}

func violations(name string, data []byte) []string {
	if len(data) == 0 || bytes.IndexByte(data, 0) >= 0 || !utf8.Valid(data) {
		return nil
	}
	var result []string
	text := bytes.ReplaceAll(data, []byte("\r\n"), []byte("\n"))
	for i, line := range bytes.Split(text, []byte("\n")) {
		if len(line) > 0 && (line[len(line)-1] == ' ' || line[len(line)-1] == '\t') {
			result = append(result, fmt.Sprintf("%s:%d: trailing whitespace", name, i+1))
		}
	}
	if !bytes.HasSuffix(text, []byte("\n")) {
		result = append(result, name+": missing final newline")
	} else if bytes.Equal(text, []byte("\n")) || bytes.HasSuffix(text, []byte("\n\n")) {
		result = append(result, name+": blank line(s) at end of file")
	}
	return result
}
