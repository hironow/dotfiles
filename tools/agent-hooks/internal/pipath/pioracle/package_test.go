package pioracle_test

import (
	"path/filepath"
	"testing"

	json "github.com/goccy/go-json/v2"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/pipath/pioracle"
)

func TestFindUsesTheSharedPiPackage(t *testing.T) {
	node, root, err := pioracle.FindPackage()
	if err != nil {
		t.Skip(err)
	}
	pathNode, module, err := pioracle.Find()
	if err != nil {
		t.Fatal(err)
	}
	if pathNode != node || module != filepath.Join(root, "dist", "core", "tools", "path-utils.js") {
		t.Fatalf("path oracle found %q, %q outside the shared package", pathNode, module)
	}
}

func TestASCIILineEscapesWhatLineSplittersBreakOn(t *testing.T) {
	// U+2028, U+0085, and others end a line for some tools; every
	// non-ASCII character is escaped, and the line still reads back the same.
	value := "a b\u0085c d\U0001F600e雪"
	line, err := json.Marshal(map[string]string{"k": value})
	if err != nil {
		t.Fatal(err)
	}
	escaped := pioracle.ASCIILine(line)
	for _, b := range escaped {
		if b > 0x7f {
			t.Fatalf("ASCIILine left a non-ASCII byte: %q", escaped)
		}
	}
	var back map[string]string
	if err := json.Unmarshal(escaped, &back); err != nil || back["k"] != value {
		t.Errorf("read back %q, %v; want %q", back["k"], err, value)
	}
}
