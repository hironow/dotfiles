package main

import (
	"bytes"
	"embed"
	"io/fs"
	"os"
	"path/filepath"
)

// Include tests too: a stale build must not silently bypass a changed policy
// or oracle. There is no generated hash constant that can itself drift.
//
//go:embed *.go go.mod incidents/*.json
var buildSource embed.FS

// SourceMatches compares bytes and file sets before any finding is accepted.
// This is freshness detection, not authentication of an untrusted executable.
//
// The comparison is byte-exact, so the embedded files must be pinned to LF in
// .gitattributes: otherwise a CRLF checkout on Windows reports a stale build
// for an unchanged commit.
func SourceMatches(dir string) bool {
	var embedded []string
	names := map[string]bool{}
	for _, pattern := range []string{"*.go", "go.mod", "incidents/*.json"} {
		matches, err := fs.Glob(buildSource, pattern)
		if err != nil {
			return false
		}
		embedded = append(embedded, matches...)
		current, err := filepath.Glob(filepath.Join(dir, filepath.FromSlash(pattern)))
		if err != nil {
			return false
		}
		for _, name := range current {
			relative, err := filepath.Rel(dir, name)
			if err != nil {
				return false
			}
			names[filepath.ToSlash(relative)] = true
		}
	}
	if len(names) != len(embedded) {
		return false
	}
	for _, name := range embedded {
		if !names[name] {
			return false
		}
		expected, err := buildSource.ReadFile(name)
		if err != nil {
			return false
		}
		actual, err := os.ReadFile(filepath.Join(dir, filepath.FromSlash(name)))
		if err != nil || !bytes.Equal(actual, expected) {
			return false
		}
	}
	return true
}
