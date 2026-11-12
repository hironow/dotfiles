// Package repo is an in-memory stand-in for the dotfiles checkout.
package repo

import (
	"fmt"
	"slices"
)

// Fake holds file contents by repo-relative path and the paths git would
// report as changed.
type Fake struct {
	Files      map[string]string
	DirtyPaths []string
}

func (f *Fake) Read(path string) (string, error) {
	content, ok := f.Files[path]
	if !ok {
		return "", fmt.Errorf("%s: no such file", path)
	}
	return content, nil
}

// Write only replaces a file that exists, like the real checkout.
func (f *Fake) Write(path, content string) error {
	if _, ok := f.Files[path]; !ok {
		return fmt.Errorf("%s: no such file", path)
	}
	f.Files[path] = content
	return nil
}

func (f *Fake) Dirty(paths []string) ([]string, error) {
	var out []string
	for _, p := range paths {
		if slices.Contains(f.DirtyPaths, p) {
			out = append(out, p)
		}
	}
	return out, nil
}
