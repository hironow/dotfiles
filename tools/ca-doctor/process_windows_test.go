package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestTaskkillComesFromTheSystemDirectoryNotTheEnvironment(t *testing.T) {
	// A SystemRoot pointed at a folder anyone can fill must not choose the
	// binary that cleanup runs.
	planted := t.TempDir()
	t.Setenv("SystemRoot", planted)
	path, ok := systemTaskkill()
	if !ok {
		t.Fatal("no taskkill.exe in the system directory")
	}
	if !strings.EqualFold(filepath.Base(path), "taskkill.exe") ||
		strings.HasPrefix(strings.ToLower(path), strings.ToLower(planted)) {
		t.Fatalf("taskkill path %q follows the environment", path)
	}
	if info, err := os.Stat(path); err != nil || info.IsDir() {
		t.Fatalf("taskkill path %q: %v", path, err)
	}
}
