// Package releases is an in-memory stand-in for GitHub's repositories and tags.
package releases

import (
	"context"
	"fmt"
	"slices"
	"strings"

	"github.com/hironow/dotfiles/tools/agent-bump/internal/bump"
)

// Tag is one ref: its commit, its files, and the SHA of each directory.
type Tag struct {
	Commit string
	Files  map[string]string
	Dirs   map[string]string
}

// Repo is one repository: its newest release and its refs.
type Repo struct {
	Latest string
	Tags   map[string]Tag
}

// Fake holds the repositories it knows by owner/repo.
type Fake struct{ Repos map[string]Repo }

func (f *Fake) tag(repo, ref string) (Tag, error) {
	r, ok := f.Repos[repo]
	if !ok {
		return Tag{}, fmt.Errorf("%s: no such repository", repo)
	}
	t, ok := r.Tags[ref]
	if !ok {
		return Tag{}, fmt.Errorf("%s: no ref %s", repo, ref)
	}
	return t, nil
}

func (f *Fake) Latest(_ context.Context, repo string) (string, error) {
	r, ok := f.Repos[repo]
	if !ok || r.Latest == "" {
		return "", fmt.Errorf("%s: no release", repo)
	}
	return r.Latest, nil
}

func (f *Fake) Commit(_ context.Context, repo, ref string) (string, error) {
	t, err := f.tag(repo, ref)
	return t.Commit, err
}

func (f *Fake) Tree(_ context.Context, repo, ref string) ([]bump.TreeEntry, error) {
	t, err := f.tag(repo, ref)
	if err != nil {
		return nil, err
	}
	var out []bump.TreeEntry
	for p := range t.Files {
		out = append(out, bump.TreeEntry{Path: p})
	}
	for p, sha := range t.Dirs {
		out = append(out, bump.TreeEntry{Path: p, Dir: true, SHA: sha})
	}
	slices.SortFunc(out, func(a, b bump.TreeEntry) int { return strings.Compare(a.Path, b.Path) })
	return out, nil
}

func (f *Fake) File(_ context.Context, repo, ref, path string) ([]byte, error) {
	t, err := f.tag(repo, ref)
	if err != nil {
		return nil, err
	}
	content, ok := t.Files[path]
	if !ok {
		return nil, fmt.Errorf("%s@%s: no file %s", repo, ref, path)
	}
	return []byte(content), nil
}
