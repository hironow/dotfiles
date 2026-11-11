package main

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

// checkout is the Repo adapter for the dotfiles working tree.
type checkout struct{ root string }

func (c checkout) abs(p string) string { return filepath.Join(c.root, filepath.FromSlash(p)) }

func (c checkout) Read(p string) (string, error) {
	b, err := os.ReadFile(c.abs(p))
	return string(b), err
}

func (c checkout) Write(p, content string) error {
	info, err := os.Stat(c.abs(p))
	if err != nil {
		return err
	}
	return os.WriteFile(c.abs(p), []byte(content), info.Mode().Perm())
}

// LinkedWorktree reports whether the root is a linked worktree rather than
// the main checkout: there git keeps its own dir apart from the common one.
func (c checkout) LinkedWorktree() (bool, error) {
	// G204: the root is the --root the just recipe passes, as one argv entry.
	out, err := exec.CommandContext(context.Background(), "git", "-C", c.root, //nolint:gosec // G204: audited above
		"rev-parse", "--path-format=absolute", "--git-dir", "--git-common-dir").Output()
	if err != nil {
		return false, err
	}
	dirs := strings.Fields(string(out))
	if len(dirs) != 2 {
		return false, fmt.Errorf("git rev-parse printed %q", out)
	}
	return filepath.Clean(dirs[0]) != filepath.Clean(dirs[1]), nil
}

func (c checkout) Dirty(paths []string) ([]string, error) {
	if len(paths) == 0 {
		return nil, nil
	}
	args := append([]string{"-C", c.root, "status", "--porcelain=v1", "--"}, paths...)
	out, err := exec.CommandContext(context.Background(), "git", args...).Output()
	if err != nil {
		return nil, err
	}
	var dirty []string
	for _, line := range strings.Split(strings.TrimRight(string(out), "\n"), "\n") {
		if len(line) > 3 {
			dirty = append(dirty, line[3:])
		}
	}
	return dirty, nil
}
