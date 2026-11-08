//go:build windows

package logsink_test

import (
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/logsink"
)

var _ logsink.Sink = (*logsink.FileSink)(nil)

func TestWindowsFileLogIsUnsupported(t *testing.T) {
	sink, err := logsink.OpenFileSink(t.TempDir(), 0)
	if sink != nil || !errors.Is(err, errors.ErrUnsupported) || !strings.Contains(err.Error(), "not on Windows yet") {
		t.Fatalf("OpenFileSink = %v, %v", sink, err)
	}
	var unopened logsink.FileSink
	if err := unopened.Close(); err != nil {
		t.Fatal(err)
	}
	if salt, ok := unopened.Salt(); salt != nil || ok {
		t.Fatalf("Salt = %x, %v", salt, ok)
	}
	if err := unopened.Write(time.Time{}, []byte("{}\n")); !errors.Is(err, errors.ErrUnsupported) {
		t.Fatalf("Write = %v", err)
	}
	if _, err := unopened.Read(time.Time{}, 1); !errors.Is(err, errors.ErrUnsupported) {
		t.Fatalf("Read = %v", err)
	}
}
