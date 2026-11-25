// Package fake holds the in-memory Source for tests.
package fake

import (
	"fmt"
	"io/fs"

	"github.com/hironow/dotfiles/tools/repo-lint/internal/rules"
)

// Source maps an input path to its decoded value.
type Source map[string]any

// Load returns the value for the path, or fs.ErrNotExist.
func (s Source) Load(in rules.Input) (any, error) {
	v, ok := s[in.Path]
	if !ok {
		return nil, fmt.Errorf("%s: %w", in.Path, fs.ErrNotExist)
	}
	return v, nil
}
