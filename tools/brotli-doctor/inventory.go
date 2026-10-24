package main

import (
	"context"
	"encoding/json/v2"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
)

type Inventory struct {
	Paths      []string `json:"paths"`
	Issues     []string `json:"issues"`
	Excluded   int      `json:"excluded"`
	Duplicates int      `json:"duplicates"`
}

type collector struct {
	result  Inventory
	seen    map[string]bool
	ctx     context.Context
	entries int
	limit   int
}

func within(root, path string) bool {
	rel, err := filepath.Rel(root, path)
	return err == nil && rel != ".." && !strings.HasPrefix(rel, ".."+string(filepath.Separator)) && !filepath.IsAbs(rel)
}

func safeRoot(root string) error {
	if !filepath.IsAbs(root) || filepath.Dir(root) == root {
		return errors.New("not a bounded absolute install root")
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return fmt.Errorf("home boundary: %w", err)
	}
	// Resolve aliases so /var -> /private/var cannot defeat the boundary.
	if canonical, err := filepath.EvalSymlinks(home); err == nil {
		home = canonical
	}
	if within(root, home) {
		return errors.New("install root contains the home directory")
	}
	return nil
}

func collect(ctx context.Context, roots, pathDirs []string) Inventory {
	c := collector{seen: map[string]bool{}, ctx: ctx}
	for _, root := range roots {
		if err := c.budget(); err != nil {
			c.issue(root, err)
			break
		}
		if err := c.walkRoot(root); err != nil {
			c.issue(root, err)
		}
	}
	for _, dir := range pathDirs {
		if err := c.budget(); err != nil {
			c.issue(dir, err)
			break
		}
		if err := c.readPATH(dir); err != nil {
			c.issue(dir, err)
		}
	}
	sort.Strings(c.result.Paths)
	return c.result
}

func (c *collector) issue(path string, err error) {
	c.result.Issues = append(c.result.Issues, fmt.Sprintf("%q: %v", path, err))
}

func (c *collector) budget() error {
	if err := c.ctx.Err(); err != nil {
		return err
	}
	if c.limit == 0 {
		c.limit = 200000
	}
	if c.entries >= c.limit {
		return fmt.Errorf("inventory entry limit reached (%d)", c.limit)
	}
	return nil
}

// Readdir is batched: caps apply before enumeration, not after allocation.
func (c *collector) enumerate(dir *os.File, visit func(fs.DirEntry) error) error {
	for {
		if err := c.budget(); err != nil {
			return err
		}
		entries, err := dir.ReadDir(min(128, c.limit-c.entries))
		for _, entry := range entries {
			if err := c.budget(); err != nil {
				return err
			}
			c.entries++
			if err := visit(entry); err != nil {
				return err
			}
		}
		if errors.Is(err, io.EOF) {
			return nil
		}
		if err != nil {
			return err
		}
	}
}

func (c *collector) walkRoot(raw string) error {
	if err := c.budget(); err != nil {
		return err
	}
	if !filepath.IsAbs(raw) {
		return errors.New("relative install root rejected")
	}
	root, err := filepath.EvalSymlinks(raw)
	if err != nil {
		return err
	}
	if err := safeRoot(root); err != nil {
		return err
	}
	boundary, err := os.OpenRoot(root)
	if err != nil {
		return err
	}
	defer boundary.Close()
	return c.walkDirectory(root, boundary, ".")
}

func (c *collector) walkDirectory(boundary string, root *os.Root, relative string) error {
	if err := c.budget(); err != nil {
		return err
	}
	dir, err := root.Open(relative)
	if err != nil {
		return err
	}
	defer dir.Close()
	return c.enumerate(dir, func(entry fs.DirEntry) error {
		child := filepath.Join(relative, entry.Name())
		path := filepath.Join(boundary, child)
		if entry.IsDir() {
			if err := c.walkDirectory(boundary, root, child); err != nil {
				if stopped := c.budget(); stopped != nil {
					return stopped
				}
				c.issue(path, err)
			}
		} else {
			c.add(path, boundary)
		}
		return nil
	})
}

func (c *collector) readPATH(dir string) error {
	if err := c.budget(); err != nil {
		return err
	}
	// Never inspect cwd implicitly through an empty or relative PATH component.
	if !filepath.IsAbs(dir) {
		return errors.New("empty/relative PATH directory excluded")
	}
	root, err := os.OpenRoot(dir)
	if err != nil {
		return err
	}
	defer root.Close()
	file, err := root.Open(".")
	if err != nil {
		return err
	}
	defer file.Close()
	return c.enumerate(file, func(entry fs.DirEntry) error {
		if !entry.IsDir() {
			c.add(filepath.Join(dir, entry.Name()), "")
		}
		return nil
	})
}

func (c *collector) add(path, root string) {
	canonical, err := filepath.EvalSymlinks(path)
	if err != nil {
		c.issue(path, err)
		return
	}
	if root != "" && !within(root, canonical) {
		c.result.Excluded++
		c.issue(path, errors.New("link outside mise install root excluded"))
		return
	}
	info, err := statCandidate(canonical, root)
	if err != nil {
		c.issue(path, err)
		return
	}
	if !info.Mode().IsRegular() {
		c.result.Excluded++
		return
	}
	if runtime.GOOS == "windows" && !strings.EqualFold(filepath.Ext(canonical), ".exe") && !strings.EqualFold(filepath.Ext(canonical), ".com") {
		c.result.Excluded++
		return
	}
	if runtime.GOOS != "windows" && info.Mode().Perm()&0o111 == 0 {
		c.result.Excluded++
		return
	}
	key := canonical
	if runtime.GOOS == "windows" {
		key = strings.ToLower(key)
	}
	if c.seen[key] {
		c.result.Duplicates++
		return
	}
	c.seen[key] = true
	c.result.Paths = append(c.result.Paths, canonical)
}

// Use os.Root for the final stat as well as lexical containment checks.
func statCandidate(path, boundary string) (fs.FileInfo, error) {
	if boundary == "" {
		boundary = filepath.Dir(path)
	}
	root, err := os.OpenRoot(boundary)
	if err != nil {
		return nil, err
	}
	defer root.Close()
	relative, err := filepath.Rel(boundary, path)
	if err != nil {
		return nil, err
	}
	return root.Stat(relative)
}

func parseMise(data []byte) ([]string, error) {
	var tools map[string][]struct {
		Installed bool   `json:"installed"`
		Path      string `json:"install_path"`
	}
	if err := json.Unmarshal(data, &tools); err != nil {
		return nil, fmt.Errorf("mise JSON: %w", err)
	}
	if tools == nil {
		return nil, errors.New("mise JSON must be an object")
	}
	seen := map[string]bool{}
	var roots []string
	for _, versions := range tools {
		for _, v := range versions {
			if v.Installed {
				if !filepath.IsAbs(v.Path) {
					return nil, errors.New("mise installed entry has no absolute install_path")
				}
				if !seen[v.Path] {
					seen[v.Path] = true
					roots = append(roots, v.Path)
				}
			}
		}
	}
	sort.Strings(roots)
	return roots, nil
}
