// Package repo is an in-memory stand-in for the dotfiles checkout.
package repo

import "fmt"

// Fake holds file contents by repo-relative path.
type Fake struct {
	Files     map[string]string
	FailWrite map[string]bool // path -> its write fails
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
	if f.FailWrite[path] {
		return fmt.Errorf("%s: write failed", path)
	}
	f.Files[path] = content
	return nil
}
