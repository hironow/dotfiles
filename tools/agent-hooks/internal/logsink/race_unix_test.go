//go:build unix

package logsink_test

import (
	"bytes"
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"sync"
	"testing"
	"time"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/logsink"
)

func awaitSalt(t *testing.T, sink *logsink.FileSink) []byte {
	t.Helper()
	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		if salt, ok := sink.Salt(); ok {
			if len(salt) != logsink.SaltSize {
				t.Fatalf("partial salt: %x", salt)
			}
			return salt
		}
		runtime.Gosched()
	}
	t.Fatal("salt never became available")
	return nil
}

func writeSaltHelper(t *testing.T, dir string) {
	t.Helper()
	executable, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	binary, err := os.ReadFile(executable)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "salt-helper.test"), binary, 0o700); err != nil {
		t.Fatal(err)
	}
}

func TestSaltConcurrentGoroutinesAndProcessesAgree(t *testing.T) {
	for _, processes := range []bool{false, true} {
		t.Run(map[bool]string{false: "goroutines", true: "processes"}[processes], func(t *testing.T) {
			base := t.TempDir()
			helperDir := t.TempDir()
			if processes {
				// argv[0] is caller-controlled. Helper processes must use the running binary.
				original := os.Args[0]
				os.Args[0] = filepath.Join(base, "untrusted-argv-zero")
				t.Cleanup(func() { os.Args[0] = original })
				t.Setenv("PATH", base)
				writeSaltHelper(t, helperDir)
			}
			start := make(chan struct{})
			salts := make(chan []byte, 48)
			var wg sync.WaitGroup
			for range 48 {
				wg.Go(func() {
					sink := openSink(t, base)
					<-start
					salts <- awaitSalt(t, sink)
				})
			}
			if processes {
				for range 6 {
					wg.Go(func() {
						<-start
						ctx, cancel := context.WithTimeout(t.Context(), 10*time.Second)
						defer cancel()
						command := exec.CommandContext(ctx, "./salt-helper.test", "-test.run=^TestSaltHelperProcess$")
						command.Dir = helperDir
						command.Env = append(os.Environ(), "AGENT_HOOK_LOGSINK_HELPER_BASE="+base)
						out, err := command.Output()
						if err != nil {
							t.Errorf("salt helper: %v; output %q", err, out)
							return
						}
						if len(out) != logsink.SaltSize {
							t.Errorf("helper salt length = %d", len(out))
							return
						}
						salts <- out
					})
				}
			}
			close(start)
			// Drain while writers finish; process results also use this channel.
			go func() { wg.Wait(); close(salts) }()
			var want []byte
			count := 0
			for salt := range salts {
				count++
				if want == nil {
					want = salt
				}
				if !bytes.Equal(salt, want) {
					t.Errorf("salt = %x, want %x", salt, want)
				}
			}
			expected := 48
			if processes {
				expected += 6
			}
			if count != expected {
				t.Fatalf("got %d salts, want %d", count, expected)
			}
			if got := readFile(t, filepath.Join(base, "dotfiles", "agent-hooks", "salt")); !bytes.Equal(got, want) {
				t.Fatalf("disk salt = %x, want %x", got, want)
			}
		})
	}
}

func TestSaltHelperProcess(t *testing.T) {
	base := os.Getenv("AGENT_HOOK_LOGSINK_HELPER_BASE")
	if base == "" {
		return
	}
	sink, err := logsink.OpenFileSink(base, os.Getuid())
	if err != nil {
		t.Fatal(err)
	}
	salt := awaitSalt(t, sink)
	if err := sink.Close(); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stdout.Write(salt); err != nil {
		t.Fatal(err)
	}
	os.Exit(0)
}
