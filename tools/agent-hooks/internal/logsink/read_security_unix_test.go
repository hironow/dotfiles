//go:build unix

package logsink_test

import (
	"os"
	"path/filepath"
	"syscall"
	"testing"
	"time"
)

func TestReadRejectsFIFOAndSymlinkAtOnce(t *testing.T) {
	for _, kind := range []string{"fifo", "symlink"} {
		t.Run(kind, func(t *testing.T) {
			base := t.TempDir()
			sink := openSink(t, base)
			logs := filepath.Join(base, "dotfiles", "agent-hooks", "logs")
			day := filepath.Join(logs, "2026-11-05.jsonl")
			if kind == "fifo" {
				if err := syscall.Mkfifo(day, 0o600); err != nil {
					t.Fatal(err)
				}
			} else {
				writeFile(t, filepath.Join(logs, "target"), []byte("{}\n"))
				if err := os.Symlink("target", day); err != nil {
					t.Fatal(err)
				}
			}
			done := make(chan error, 1)
			go func() {
				_, err := sink.Read(time.Date(2026, 11, 5, 0, 0, 0, 0, time.UTC), 1)
				done <- err
			}()
			select {
			case err := <-done:
				if err == nil {
					t.Fatalf("Read accepted %s", kind)
				}
			case <-time.After(750 * time.Millisecond):
				t.Fatalf("Read blocked on %s", kind)
			}
		})
	}
}
