//go:build unix

package logsink

import (
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
	"time"
)

func TestOpenFileRejectsReadableNonregularFilesAtOnce(t *testing.T) {
	for _, kind := range []string{"fifo", "directory"} {
		t.Run(kind, func(t *testing.T) {
			base := t.TempDir()
			path := filepath.Join(base, "entry")
			if kind == "fifo" {
				if err := syscall.Mkfifo(path, 0o600); err != nil {
					t.Fatal(err)
				}
			} else if err := os.Mkdir(path, 0o700); err != nil {
				t.Fatal(err)
			}
			root, err := os.OpenRoot(base)
			if err != nil {
				t.Fatal(err)
			}
			defer root.Close()
			// Read-only opens succeed for both, so the type check must reject them.
			done := make(chan error, 1)
			go func() {
				file, err := openFile(root, "entry", os.O_RDONLY, os.Getuid(), false)
				if file != nil {
					file.Close()
				}
				done <- err
			}()
			select {
			case err := <-done:
				if err == nil || !strings.Contains(err.Error(), "file owner or type is unsafe") {
					t.Fatalf("openFile = %v; want the regular-file check to refuse %s", err, kind)
				}
			case <-time.After(750 * time.Millisecond):
				t.Fatalf("openFile blocked on %s", kind)
			}
		})
	}
}
