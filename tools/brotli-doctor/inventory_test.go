package main

import (
	"context"
	"encoding/json/v2"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func putFile(t *testing.T, path string, data string) {
	t.Helper()
	if err := os.WriteFile(path, []byte(data), 0o700); err != nil {
		t.Fatal(err)
	}
}

func linkFile(t *testing.T, old, new string) {
	t.Helper()
	if err := os.Symlink(old, new); err != nil {
		t.Skipf("symlinks unavailable: %v", err)
	}
}

func TestInventoryKeepsMiseTargetsInsideRootAndDeduplicatesPATH(t *testing.T) {
	root := t.TempDir()
	outside := t.TempDir()
	own := filepath.Join(root, "own.exe")
	external := filepath.Join(outside, "external.exe")
	putFile(t, own, "hello")
	putFile(t, external, "hello")
	linkFile(t, external, filepath.Join(root, "escape.exe"))
	linkFile(t, outside, filepath.Join(root, "directory-escape"))
	linkFile(t, own, filepath.Join(root, "alias.exe"))
	got := collect(context.Background(), []string{root}, []string{root})
	if len(got.Paths) != 2 || got.Duplicates < 1 || len(got.Issues) == 0 || got.Excluded < 1 {
		t.Fatalf("inventory %+v", got)
	}
	miseOnly := collect(context.Background(), []string{root}, nil)
	if len(miseOnly.Paths) != 1 {
		t.Fatalf("mise escaped: %+v", miseOnly)
	}
}

func TestInventoryRejectsBroadRootsRelativePATHAndMissingRoots(t *testing.T) {
	home, err := os.UserHomeDir()
	if err != nil {
		t.Fatal(err)
	}
	if safeRoot(home) == nil || safeRoot(filepath.VolumeName(home)+string(filepath.Separator)) == nil {
		t.Fatal("broad root accepted")
	}
	got := collect(context.Background(), []string{filepath.Join(t.TempDir(), "missing")}, []string{"", "."})
	if len(got.Issues) != 3 {
		t.Fatalf("issues: %+v", got)
	}
	if within("/a/tool", "/a/tool-sibling/bin") {
		t.Fatal("sibling-prefix accepted")
	}
}

func TestInventoryCancellationAndNonRecursivePATH(t *testing.T) {
	root := t.TempDir()
	if err := os.Mkdir(filepath.Join(root, "nested"), 0o700); err != nil {
		t.Fatal(err)
	}
	putFile(t, filepath.Join(root, "nested", "hidden"), "hello")
	got := collect(context.Background(), nil, []string{root})
	if len(got.Paths) != 0 {
		t.Fatal("PATH scanned recursively")
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	got = collect(ctx, []string{root}, nil)
	if !strings.Contains(strings.Join(got.Issues, " "), "canceled") {
		t.Fatalf("cancellation hidden: %+v", got)
	}
}

func TestInventoryDoesNotOpenSpecialFiles(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("Unix device path")
	}
	dir, err := os.MkdirTemp("", "br-sock")
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = os.RemoveAll(dir) })
	listener, err := net.Listen("unix", filepath.Join(dir, "socket"))
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	got := collect(context.Background(), nil, []string{dir})
	if len(got.Paths) != 0 || got.Excluded != 1 {
		t.Fatalf("accepted nonregular file: %+v", got)
	}
}

func TestParseMiseReportsInvalidOrEmptyRoots(t *testing.T) {
	path := filepath.Join(t.TempDir(), "go")
	encoded, err := json.Marshal(path)
	if err != nil {
		t.Fatal(err)
	}
	roots, err := parseMise(fmt.Appendf(nil, `{"go":[{"installed":true,"install_path":%s},{"installed":false,"install_path":"/ignore"}]}`, encoded))
	if err != nil || len(roots) != 1 || roots[0] != path {
		t.Fatalf("%v %v", roots, err)
	}
	for _, raw := range []string{`{`, `{"go":[{"installed":true}]}`, `null`} {
		if _, err := parseMise([]byte(raw)); err == nil {
			t.Fatalf("accepted %s", raw)
		}
	}
}
