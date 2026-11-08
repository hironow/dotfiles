//go:build unix

package logsink

import (
	"os"
	"testing"
)

func TestRemoveIfPresentAcceptsAnAlreadyRemovedName(t *testing.T) {
	root, err := os.OpenRoot(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	defer root.Close()
	file, err := root.Create("2026-10-01.jsonl")
	if err != nil {
		t.Fatal(err)
	}
	if err := file.Close(); err != nil {
		t.Fatal(err)
	}
	if err := root.Remove("2026-10-01.jsonl"); err != nil {
		t.Fatal(err)
	}
	if err := removeIfPresent(root, "2026-10-01.jsonl"); err != nil {
		t.Fatalf("removing an already removed file: %v", err)
	}
}
