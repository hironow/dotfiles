package fake_test

import (
	"bytes"
	"sync"
	"testing"
	"time"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/fake"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/logsink"
)

var _ logsink.Sink = (*fake.LogSink)(nil)

func TestLogSinkRecordsIndependentCopies(t *testing.T) {
	sink := &fake.LogSink{SaltBytes: []byte("salt")}
	salt, ok := sink.Salt()
	if !ok || string(salt) != "salt" {
		t.Fatalf("Salt = %q, %v", salt, ok)
	}
	salt[0] = 'x'
	if got, _ := sink.Salt(); string(got) != "salt" {
		t.Fatal("returned salt aliases the configured salt")
	}
	now := time.Date(2026, 11, 5, 0, 0, 0, 0, time.UTC)
	line := []byte("{}\n")
	if err := sink.Write(now, line); err != nil {
		t.Fatal(err)
	}
	line[0] = 'x'
	lines := sink.Lines()
	if len(lines) != 1 || !lines[0].Time.Equal(now) || !bytes.Equal(lines[0].Line, []byte("{}\n")) {
		t.Fatalf("Lines = %+v", lines)
	}
	lines[0].Line[0] = 'y'
	lines[0].Time = time.Time{}
	if got := sink.Lines(); string(got[0].Line) != "{}\n" || !got[0].Time.Equal(now) {
		t.Fatal("accessor aliases stored entries")
	}
	if got, ok := (&fake.LogSink{}).Salt(); ok || got != nil {
		t.Fatalf("unset salt = %q, %v", got, ok)
	}
}

func TestLogSinkConcurrentUse(t *testing.T) {
	sink := &fake.LogSink{SaltBytes: []byte("salt")}
	var wg sync.WaitGroup
	for range 100 {
		wg.Go(func() {
			if err := sink.Write(time.Time{}, []byte("{}\n")); err != nil {
				t.Error(err)
			}
			sink.Salt()
			sink.Lines()
		})
	}
	wg.Wait()
	if got := len(sink.Lines()); got != 100 {
		t.Fatalf("recorded %d lines, want 100", got)
	}
}
