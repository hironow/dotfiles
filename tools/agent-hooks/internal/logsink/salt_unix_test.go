//go:build unix

package logsink_test

import (
	"bytes"
	"os"
	"path/filepath"
	"strconv"
	"syscall"
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/logsink"
)

func TestSaltRecoversDeadMakers(t *testing.T) {
	for size := 0; size <= logsink.SaltSize; size++ {
		t.Run(strconv.Itoa(size), func(t *testing.T) {
			base := t.TempDir()
			sink := openSink(t, base)
			hooks := filepath.Join(base, "dotfiles", "agent-hooks")
			pending := filepath.Join(hooks, "salt.new")
			writeFile(t, pending, bytes.Repeat([]byte("x"), size))
			salt, ok := sink.Salt()
			if !ok || len(salt) != logsink.SaltSize {
				t.Fatalf("Salt = %x, %v; want 32 bytes", salt, ok)
			}
			if got := readFile(t, filepath.Join(hooks, "salt")); !bytes.Equal(salt, got) {
				t.Fatalf("salt on disk = %x, want %x", got, salt)
			}
			if _, err := os.Lstat(pending); !os.IsNotExist(err) {
				t.Fatalf("salt.new remains: %v", err)
			}
		})
	}
	t.Run("published with second link", func(t *testing.T) {
		base := t.TempDir()
		sink := openSink(t, base)
		hooks := filepath.Join(base, "dotfiles", "agent-hooks")
		want := bytes.Repeat([]byte("s"), logsink.SaltSize)
		writeFile(t, filepath.Join(hooks, "salt.new"), want)
		if err := os.Link(filepath.Join(hooks, "salt.new"), filepath.Join(hooks, "salt")); err != nil {
			t.Fatal(err)
		}
		got, ok := sink.Salt()
		if !ok || !bytes.Equal(got, want) {
			t.Fatalf("Salt = %x, %v; want %x", got, ok, want)
		}
		if _, err := os.Lstat(filepath.Join(hooks, "salt.new")); !os.IsNotExist(err) {
			t.Fatalf("salt.new remains: %v", err)
		}
	})
}

func TestSaltLeavesInvalidLengthsAlone(t *testing.T) {
	for _, size := range []int{0, 1, logsink.SaltSize - 1, logsink.SaltSize + 1, 4096} {
		t.Run(strconv.Itoa(size), func(t *testing.T) {
			base := t.TempDir()
			sink := openSink(t, base)
			path := filepath.Join(base, "dotfiles", "agent-hooks", "salt")
			want := bytes.Repeat([]byte("x"), size)
			writeFile(t, path, want)
			if got, ok := sink.Salt(); ok || got != nil {
				t.Fatalf("Salt = %x, %v; want no salt", got, ok)
			}
			if got := readFile(t, path); !bytes.Equal(got, want) {
				t.Fatalf("invalid salt changed: %x", got)
			}
		})
	}
}

func TestSaltContendedLockChangesNothing(t *testing.T) {
	base := t.TempDir()
	sink := openSink(t, base)
	hooks := filepath.Join(base, "dotfiles", "agent-hooks")
	lock, err := os.OpenFile(filepath.Join(hooks, "salt.lock"), os.O_CREATE|os.O_RDWR, 0o600)
	if err != nil {
		t.Fatal(err)
	}
	defer lock.Close()
	if err := syscall.Flock(int(lock.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); err != nil {
		t.Fatal(err)
	}
	pending := filepath.Join(hooks, "salt.new")
	writeFile(t, pending, []byte("unfinished"))
	if got, ok := sink.Salt(); ok || got != nil {
		t.Fatalf("Salt with held lock = %x, %v", got, ok)
	}
	if got := readFile(t, pending); string(got) != "unfinished" {
		t.Fatalf("salt.new changed: %q", got)
	}
	if _, err := os.Lstat(filepath.Join(hooks, "salt")); !os.IsNotExist(err) {
		t.Fatalf("salt was created: %v", err)
	}
	if got := readFile(t, filepath.Join(hooks, "salt.lock")); len(got) != 0 {
		t.Fatalf("salt.lock was written: %q", got)
	}
}

func TestSaltRejectsLinksWithoutChangingTargets(t *testing.T) {
	for _, name := range []string{"salt", "salt.lock"} {
		for _, hardLink := range []bool{false, true} {
			t.Run(name+"/"+strconv.FormatBool(hardLink), func(t *testing.T) {
				base := t.TempDir()
				sink := openSink(t, base)
				hooks := filepath.Join(base, "dotfiles", "agent-hooks")
				target := filepath.Join(hooks, "target")
				want := bytes.Repeat([]byte("s"), logsink.SaltSize)
				writeFile(t, target, want)
				if err := os.Chmod(target, 0o644); err != nil {
					t.Fatal(err)
				}
				var err error
				if hardLink {
					err = os.Link(target, filepath.Join(hooks, name))
				} else {
					err = os.Symlink("target", filepath.Join(hooks, name))
				}
				if err != nil {
					t.Fatal(err)
				}
				if salt, ok := sink.Salt(); salt != nil || ok {
					t.Fatalf("linked salt or lock used: %x, %v", salt, ok)
				}
				if got := readFile(t, target); !bytes.Equal(got, want) {
					t.Fatalf("target changed: %x", got)
				}
				info, err := os.Stat(target)
				if err != nil || info.Mode().Perm() != 0o644 {
					t.Fatalf("target mode changed: %v, %v", info, err)
				}
			})
		}
	}
}
