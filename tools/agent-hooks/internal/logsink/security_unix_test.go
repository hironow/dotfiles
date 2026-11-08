//go:build unix

package logsink

import (
	"bytes"
	"os"
	"path/filepath"
	"testing"
)

var _ Sink = (*FileSink)(nil)

func TestOpenFileRejectsAnotherOwnerWithoutChanges(t *testing.T) {
	for _, name := range []string{"salt", "salt.lock", "salt.new", "2026-11-05.jsonl"} {
		t.Run(name, func(t *testing.T) {
			base := t.TempDir()
			path := filepath.Join(base, name)
			want := bytes.Repeat([]byte("s"), SaltSize)
			if err := os.WriteFile(path, want, 0o644); err != nil {
				t.Fatal(err)
			}
			if err := os.Chmod(path, 0o644); err != nil {
				t.Fatal(err)
			}
			root, err := os.OpenRoot(base)
			if err != nil {
				t.Fatal(err)
			}
			defer root.Close()
			file, err := openFile(root, name, os.O_RDWR, os.Getuid()+1, false)
			if err == nil {
				file.Close()
				t.Fatal("accepted file owned by another uid")
			}
			got, err := os.ReadFile(path)
			if err != nil || !bytes.Equal(got, want) {
				t.Fatalf("target = %q, %v; want unchanged", got, err)
			}
			info, err := os.Stat(path)
			if err != nil || info.Mode().Perm() != 0o644 {
				t.Fatalf("target mode changed: %v, %v", info, err)
			}
		})
	}
}

func TestOpenedNamesMustStillMatchHandles(t *testing.T) {
	for _, directory := range []bool{false, true} {
		t.Run(map[bool]string{false: "file", true: "directory"}[directory], func(t *testing.T) {
			base := t.TempDir()
			path := filepath.Join(base, "entry")
			if directory {
				if err := os.Mkdir(path, 0o700); err != nil {
					t.Fatal(err)
				}
			} else if err := os.WriteFile(path, []byte("original"), 0o600); err != nil {
				t.Fatal(err)
			}
			root, err := os.OpenRoot(base)
			if err != nil {
				t.Fatal(err)
			}
			defer root.Close()
			opened, err := root.Open("entry")
			if err != nil {
				t.Fatal(err)
			}
			defer opened.Close()
			info, err := opened.Stat()
			if err != nil {
				t.Fatal(err)
			}
			if err := os.Rename(path, path+"-old"); err != nil {
				t.Fatal(err)
			}
			if err := os.WriteFile(path, []byte("replacement"), 0o644); err != nil {
				t.Fatal(err)
			}
			if err := checkName(root, "entry", info); err == nil {
				t.Fatal("accepted a name replaced after open")
			}
		})
	}
}
