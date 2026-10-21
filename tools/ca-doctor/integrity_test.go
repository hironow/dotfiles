package main

import (
	"io/fs"
	"os"
	"path/filepath"
	"testing"
)

func TestBinaryRejectsChangedOrMissingSourceAndExtraPolicy(t *testing.T) {
	dir := t.TempDir()
	err := fs.WalkDir(buildSource, ".", func(name string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		target := filepath.Join(dir, filepath.FromSlash(name))
		if entry.IsDir() {
			return os.MkdirAll(target, 0o700)
		}
		data, err := buildSource.ReadFile(name)
		if err != nil {
			return err
		}
		return os.WriteFile(target, data, 0o600)
	})
	if err != nil {
		t.Fatal(err)
	}
	if !SourceMatches(dir) {
		t.Fatal("identical source rejected")
	}
	extra := filepath.Join(dir, "unreviewed.go")
	if err := os.WriteFile(extra, []byte("package main"), 0o600); err != nil {
		t.Fatal(err)
	}
	if SourceMatches(dir) {
		t.Fatal("extra policy source accepted")
	}
	if err := os.Remove(extra); err != nil {
		t.Fatal(err)
	}
	original, err := os.ReadFile(filepath.Join(dir, "policy.go"))
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "policy.go"), append(original, '\n'), 0o600); err != nil {
		t.Fatal(err)
	}
	if SourceMatches(dir) {
		t.Fatal("stale binary accepted")
	}
	if err := os.Remove(filepath.Join(dir, "policy.go")); err != nil {
		t.Fatal(err)
	}
	if SourceMatches(dir) {
		t.Fatal("missing source accepted")
	}
	if err := os.WriteFile(filepath.Join(dir, "policy.go"), original, 0o600); err != nil {
		t.Fatal(err)
	}
	manifest := filepath.Join(dir, "incidents", "emudhra-2026.json")
	data, err := os.ReadFile(manifest)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(manifest, append(data, '\n'), 0o600); err != nil {
		t.Fatal(err)
	}
	if SourceMatches(dir) {
		t.Fatal("changed incident data accepted by stale binary")
	}
}
