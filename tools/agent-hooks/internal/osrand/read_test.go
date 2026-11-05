package osrand_test

import (
	"bytes"
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/osrand"
)

func TestReadFillsTheBuffer(t *testing.T) {
	buffer := make([]byte, 32)
	if err := osrand.Read(buffer); err != nil {
		t.Fatal(err)
	}
	if bytes.Equal(buffer, make([]byte, len(buffer))) {
		t.Fatal("random buffer is still all zero")
	}
	if err := osrand.Read(nil); err != nil {
		t.Fatalf("empty read: %v", err)
	}
}
