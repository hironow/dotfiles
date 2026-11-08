//go:build unix

package logsink

import (
	"errors"
	"os"
	"testing"
)

func TestSaltRandomFailureLeavesNoPublishedOrTemporarySalt(t *testing.T) {
	sink, err := OpenFileSink(t.TempDir(), os.Getuid())
	if err != nil {
		t.Fatal(err)
	}
	defer sink.Close()
	wantErr := errors.New("randomness unavailable")
	called := false
	sink.random = func(p []byte) error {
		called = true
		p[0] = 7
		return wantErr
	}
	if salt, ok := sink.Salt(); ok || salt != nil {
		t.Fatalf("Salt = %x, %v; want no salt on random failure", salt, ok)
	}
	if !called {
		t.Error("Salt did not use the injected random source")
	}
	if salt, err := sink.readSalt(); salt != nil || !errors.Is(err, os.ErrNotExist) {
		t.Errorf("readSalt = %x, %v; want no salt", salt, err)
	}
	for _, name := range []string{"salt", "salt.new"} {
		if _, err := sink.hooks.Lstat(name); !errors.Is(err, os.ErrNotExist) {
			t.Errorf("%s remains after random failure: %v", name, err)
		}
	}
}
