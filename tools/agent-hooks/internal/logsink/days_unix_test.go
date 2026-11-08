//go:build unix

package logsink_test

import (
	"bytes"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/logsink"
)

func TestWriteRejectsInvalidLines(t *testing.T) {
	for _, line := range [][]byte{nil, {}, []byte("{}"), bytes.Repeat([]byte("\n"), logsink.MaxLine)} {
		t.Run(strconv.Itoa(len(line)), func(t *testing.T) {
			base := t.TempDir()
			sink := openSink(t, base)
			if err := sink.Write(time.Now(), line); err == nil {
				t.Fatalf("accepted line of length %d", len(line))
			}
			entries, err := os.ReadDir(filepath.Join(base, "dotfiles", "agent-hooks", "logs"))
			if err != nil || len(entries) != 0 {
				t.Fatalf("invalid line made a file: %v, %v", entries, err)
			}
		})
	}
}

func TestWriteUsesUTCAndAcceptsLineBelowLimit(t *testing.T) {
	base := t.TempDir()
	sink := openSink(t, base)
	now := time.Date(2026, 11, 6, 1, 0, 0, 0, time.FixedZone("JST", 9*60*60))
	line := append(bytes.Repeat([]byte("x"), logsink.MaxLine-2), '\n')
	if err := sink.Write(now, line); err != nil {
		t.Fatal(err)
	}
	if got := readFile(t, filepath.Join(base, "dotfiles", "agent-hooks", "logs", "2026-11-05.jsonl")); !bytes.Equal(got, line) {
		t.Fatalf("written line length = %d, want %d", len(got), len(line))
	}
}

func TestWriteDropsLineBeyondDayCap(t *testing.T) {
	base := t.TempDir()
	sink := openSink(t, base)
	now := time.Date(2026, 11, 5, 0, 0, 0, 0, time.UTC)
	path := filepath.Join(base, "dotfiles", "agent-hooks", "logs", "2026-11-05.jsonl")
	writeFile(t, path, nil)
	if err := os.Truncate(path, logsink.DayCap-3); err != nil {
		t.Fatal(err)
	}
	if err := sink.Write(now, []byte("{}\n")); err != nil {
		t.Fatalf("line ending exactly at cap: %v", err)
	}
	before := readFile(t, path)
	if err := sink.Write(now, []byte("{}\n")); err == nil {
		t.Fatal("accepted line beyond cap")
	}
	if after := readFile(t, path); !bytes.Equal(before, after) {
		t.Fatal("capped file changed")
	}
}

func TestWriteConcurrentLinesDoNotInterleaveAndCapIsBounded(t *testing.T) {
	for _, nearCap := range []bool{false, true} {
		t.Run(strconv.FormatBool(nearCap), func(t *testing.T) {
			const writers = 40
			base := t.TempDir()
			sink := openSink(t, base)
			now := time.Date(2026, 11, 5, 0, 0, 0, 0, time.UTC)
			path := filepath.Join(base, "dotfiles", "agent-hooks", "logs", "2026-11-05.jsonl")
			var prefix int64
			if nearCap {
				prefix = logsink.DayCap - logsink.MaxLine
				writeFile(t, path, nil)
				if err := os.Truncate(path, prefix); err != nil {
					t.Fatal(err)
				}
			}
			start := make(chan struct{})
			var wg sync.WaitGroup
			for i := range writers {
				wg.Go(func() {
					<-start
					line := strings.Repeat(fmt.Sprintf("%02d", i), 1000) + "\n"
					if err := sink.Write(now, []byte(line)); err != nil && !nearCap {
						t.Error(err)
					}
				})
			}
			close(start)
			wg.Wait()
			contents := readFile(t, path)
			if len(contents) > logsink.DayCap+writers*logsink.MaxLine {
				t.Fatalf("file exceeds soft cap: %d", len(contents))
			}
			lines := bytes.Split(contents[prefix:], []byte("\n"))
			if !nearCap && len(lines)-1 != writers {
				t.Fatalf("got %d lines, want %d", len(lines)-1, writers)
			}
			if len(lines) < 2 || len(lines[len(lines)-1]) != 0 {
				t.Fatal("missing complete newline-terminated lines")
			}
			for _, line := range lines[:len(lines)-1] {
				if len(line) != 2000 || !bytes.Equal(line, bytes.Repeat(line[:2], 1000)) {
					t.Fatalf("interleaved line: %q", line)
				}
			}
		})
	}
}

func TestRetentionKeepsOnlyValidDatesWithinBoundary(t *testing.T) {
	base := t.TempDir()
	sinks := []*logsink.FileSink{openSink(t, base), openSink(t, base)}
	logs := filepath.Join(base, "dotfiles", "agent-hooks", "logs")
	keep := []string{"2026-10-22.jsonl", "2026-11-05.jsonl", "2027-01-01.jsonl", "2026-02-30.jsonl", "2026-1-01.jsonl", "2026-10-01.jsonl.bak", "notes", "salt"}
	remove := []string{"2026-10-21.jsonl", "2024-02-29.jsonl", "2025-12-31.jsonl"}
	for _, name := range append(append([]string{}, keep...), remove...) {
		writeFile(t, filepath.Join(logs, name), nil)
	}
	if err := os.Mkdir(filepath.Join(logs, "2020-01-01.jsonl"), 0o700); err != nil {
		t.Fatal(err)
	}
	var wg sync.WaitGroup
	for _, sink := range sinks {
		wg.Go(func() {
			if err := sink.Write(time.Date(2026, 11, 6, 1, 0, 0, 0, time.FixedZone("JST", 9*60*60)), []byte("{}\n")); err != nil {
				t.Error(err)
			}
		})
	}
	wg.Wait()
	for _, name := range append(keep, "2020-01-01.jsonl") {
		if _, err := os.Lstat(filepath.Join(logs, name)); err != nil {
			t.Errorf("retained %s: %v", name, err)
		}
	}
	for _, name := range remove {
		if _, err := os.Lstat(filepath.Join(logs, name)); !os.IsNotExist(err) {
			t.Errorf("expired %s still present: %v", name, err)
		}
	}
}

func TestReadLastNDaysOldestFirstSkippingMissingDays(t *testing.T) {
	base := t.TempDir()
	sink := openSink(t, base)
	logs := filepath.Join(base, "dotfiles", "agent-hooks", "logs")
	for name, line := range map[string]string{"2026-11-01.jsonl": "old\n", "2026-11-03.jsonl": "first\n", "2026-11-05.jsonl": "last\n", "2026-11-06.jsonl": "future\n"} {
		writeFile(t, filepath.Join(logs, name), []byte(line))
	}
	now := time.Date(2026, 11, 6, 1, 0, 0, 0, time.FixedZone("JST", 9*60*60))
	got, err := sink.Read(now, 3)
	if err != nil || string(got) != "first\nlast\n" {
		t.Fatalf("Read = %q, %v; want first and last", got, err)
	}
	if got, err := sink.Read(now, 0); err != nil || len(got) != 0 {
		t.Fatalf("Read zero days = %q, %v", got, err)
	}
}
