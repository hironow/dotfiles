//go:build unix

package logsink_test

import (
	"path/filepath"
	"testing"
	"time"
)

func TestReadSeparatesUnterminatedDayFiles(t *testing.T) {
	for _, first := range []string{"{", "{\n", ""} {
		t.Run(first, func(t *testing.T) {
			base := t.TempDir()
			sink := openSink(t, base)
			logs := filepath.Join(base, "dotfiles", "agent-hooks", "logs")
			writeFile(t, filepath.Join(logs, "2026-11-04.jsonl"), []byte(first))
			writeFile(t, filepath.Join(logs, "2026-11-05.jsonl"), []byte("{}\n"))
			want := "{}\n"
			if first != "" {
				want = "{\n{}\n"
			}
			got, err := sink.Read(time.Date(2026, 11, 5, 0, 0, 0, 0, time.UTC), 2)
			if err != nil || string(got) != want {
				t.Fatalf("Read = %q, %v; want %q", got, err, want)
			}
		})
	}
}
