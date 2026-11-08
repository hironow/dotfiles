//go:build unix

package logsink_test

import (
	"bytes"
	"os"
	"path/filepath"
	"syscall"
	"testing"
	"time"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/logsink"
)

func TestFileSinkRejectsLinksWithoutChangingTargets(t *testing.T) {
	for _, name := range []string{"logs alias", "day alias", "outside alias", "day hard link"} {
		t.Run(name, func(t *testing.T) {
			base := t.TempDir()
			hooks := filepath.Join(base, "dotfiles", "agent-hooks")
			logs := filepath.Join(hooks, "logs")
			if err := os.MkdirAll(logs, 0o700); err != nil {
				t.Fatal(err)
			}
			now := time.Date(2026, time.November, 5, 0, 0, 0, 0, time.UTC)
			day := filepath.Join(logs, "2026-11-05.jsonl")
			target := filepath.Join(logs, "target")
			switch name {
			case "logs alias":
				target = filepath.Join(hooks, "salt")
				if err := os.Remove(logs); err != nil {
					t.Fatal(err)
				}
				if err := os.Symlink(".", logs); err != nil {
					t.Fatal(err)
				}
				if err := os.Symlink("salt", filepath.Join(hooks, "2026-11-05.jsonl")); err != nil {
					t.Fatal(err)
				}
			case "outside alias":
				target = filepath.Join(t.TempDir(), "target")
			}
			original := bytes.Repeat([]byte("x"), logsink.SaltSize)
			if err := os.WriteFile(target, original, 0o644); err != nil {
				t.Fatal(err)
			}
			if err := os.Chmod(target, 0o644); err != nil {
				t.Fatal(err)
			}
			if name == "day hard link" {
				if err := os.Link(target, day); err != nil {
					t.Fatal(err)
				}
			} else if name != "logs alias" {
				link := target
				if name == "day alias" {
					link = filepath.Base(target)
				}
				if err := os.Symlink(link, day); err != nil {
					t.Fatal(err)
				}
			}
			sink, err := logsink.OpenFileSink(base, os.Getuid())
			if name == "logs alias" {
				if err == nil {
					sink.Close()
					t.Fatal("accepted a linked logs directory")
				}
			} else {
				if err != nil {
					t.Fatal(err)
				}
				defer sink.Close()
				if err := sink.Write(now, []byte("{}\n")); err == nil {
					t.Fatal("accepted a linked day file")
				}
			}
			got, err := os.ReadFile(target)
			if err != nil || !bytes.Equal(got, original) {
				t.Fatalf("target = %q, %v; want unchanged bytes", got, err)
			}
			info, err := os.Stat(target)
			if err != nil || info.Mode().Perm() != 0o644 {
				t.Fatalf("target mode changed: %v, %v", info, err)
			}
		})
	}
}

func openSink(t *testing.T, base string) *logsink.FileSink {
	t.Helper()
	sink, err := logsink.OpenFileSink(base, os.Getuid())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := sink.Close(); err != nil {
			t.Error(err)
		}
	})
	return sink
}

func writeFile(t *testing.T, path string, contents []byte) {
	t.Helper()
	if err := os.WriteFile(path, contents, 0o600); err != nil {
		t.Fatal(err)
	}
}

func readFile(t *testing.T, path string) []byte {
	t.Helper()
	contents, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	return contents
}

func TestFileSinkRepairsPermissions(t *testing.T) {
	base := t.TempDir()
	hooks := filepath.Join(base, "dotfiles", "agent-hooks")
	logs := filepath.Join(hooks, "logs")
	if err := os.MkdirAll(logs, 0o700); err != nil {
		t.Fatal(err)
	}
	salt := filepath.Join(hooks, "salt")
	day := filepath.Join(logs, "2026-11-05.jsonl")
	writeFile(t, salt, bytes.Repeat([]byte("s"), logsink.SaltSize))
	writeFile(t, day, nil)
	for _, path := range []string{hooks, logs, salt, day} {
		if err := os.Chmod(path, 0o777); err != nil {
			t.Fatal(err)
		}
	}
	sink := openSink(t, base)
	if _, ok := sink.Salt(); !ok {
		t.Fatal("usable salt was refused")
	}
	if err := sink.Write(time.Date(2026, 11, 5, 0, 0, 0, 0, time.UTC), []byte("{}\n")); err != nil {
		t.Fatal(err)
	}
	for _, path := range []string{hooks, logs, salt, day} {
		info, err := os.Stat(path)
		if err != nil {
			t.Fatal(err)
		}
		want := os.FileMode(0o600)
		if info.IsDir() {
			want = 0o700
		}
		if info.Mode().Perm() != want {
			t.Errorf("%s mode = %o, want %o", path, info.Mode().Perm(), want)
		}
	}
}

func TestFileSinkRejectsAnotherDirectoryOwner(t *testing.T) {
	base := t.TempDir()
	sink, err := logsink.OpenFileSink(base, os.Getuid()+1)
	if err == nil {
		sink.Close()
		t.Fatal("accepted directories owned by another uid")
	}
}

func TestFileSinkRejectsFIFOAtOnce(t *testing.T) {
	base := t.TempDir()
	sink := openSink(t, base)
	day := filepath.Join(base, "dotfiles", "agent-hooks", "logs", "2026-11-05.jsonl")
	if err := syscall.Mkfifo(day, 0o600); err != nil {
		t.Fatal(err)
	}
	done := make(chan error, 1)
	go func() { done <- sink.Write(time.Date(2026, 11, 5, 0, 0, 0, 0, time.UTC), []byte("{}\n")) }()
	select {
	case err := <-done:
		if err == nil {
			t.Fatal("accepted a FIFO")
		}
	case <-time.After(time.Second):
		t.Fatal("FIFO open blocked")
	}
}

func TestFileSinkKeepsHandlesAfterDirectorySwap(t *testing.T) {
	base := t.TempDir()
	sink := openSink(t, base)
	hooks := filepath.Join(base, "dotfiles", "agent-hooks")
	renamed := hooks + "-old"
	if err := os.Rename(hooks, renamed); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(hooks, 0o700); err != nil {
		t.Fatal(err)
	}
	if err := sink.Write(time.Date(2026, 11, 5, 0, 0, 0, 0, time.UTC), []byte("{}\n")); err != nil {
		t.Fatal(err)
	}
	if got := readFile(t, filepath.Join(renamed, "logs", "2026-11-05.jsonl")); string(got) != "{}\n" {
		t.Fatalf("renamed directory holds %q", got)
	}
	entries, err := os.ReadDir(hooks)
	if err != nil || len(entries) != 0 {
		t.Fatalf("replacement directory = %v, %v; want empty", entries, err)
	}
}

func TestFileSinkRejectsLinkedDirectoryLevels(t *testing.T) {
	for _, level := range []string{"dotfiles", "agent-hooks", "logs"} {
		for _, outside := range []bool{false, true} {
			t.Run(level+"/"+map[bool]string{false: "inside", true: "outside"}[outside], func(t *testing.T) {
				base := t.TempDir()
				parent := base
				if level != "dotfiles" {
					parent = filepath.Join(parent, "dotfiles")
				}
				if level == "logs" {
					parent = filepath.Join(parent, "agent-hooks")
				}
				if err := os.MkdirAll(parent, 0o700); err != nil {
					t.Fatal(err)
				}
				target := filepath.Join(parent, "target")
				link := "target"
				if outside {
					target = t.TempDir()
					link = target
				} else if err := os.Mkdir(target, 0o700); err != nil {
					t.Fatal(err)
				}
				if err := os.Chmod(target, 0o755); err != nil {
					t.Fatal(err)
				}
				if err := os.Symlink(link, filepath.Join(parent, level)); err != nil {
					t.Fatal(err)
				}
				sink, err := logsink.OpenFileSink(base, os.Getuid())
				if err == nil {
					sink.Close()
					t.Fatal("accepted directory symlink")
				}
				info, err := os.Stat(target)
				if err != nil || info.Mode().Perm() != 0o755 {
					t.Fatalf("target mode changed: %v, %v", info, err)
				}
				entries, err := os.ReadDir(target)
				if err != nil || len(entries) != 0 {
					t.Fatalf("target changed: %v, %v", entries, err)
				}
			})
		}
	}
}
