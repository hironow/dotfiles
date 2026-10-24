package main

import (
	"runtime/debug"
	"strings"
	"testing"
)

func TestGoModulesIncludeMainAndReplacementEvidence(t *testing.T) {
	info := &debug.BuildInfo{GoVersion: "go1.27.3", Main: debug.Module{Path: "example.org/brotli-cli", Version: "v1"}, Deps: []*debug.Module{
		{Path: "example.org/compression", Version: "v1", Replace: &debug.Module{Path: "github.com/andybalholm/brotli", Version: "v1.2.0"}},
		{Path: "github.com/google/brotli", Version: "v0.1", Replace: &debug.Module{Path: "../local", Version: "(devel)"}},
	}}
	got := moduleEvidence(info)
	if len(got) != 4 || !strings.Contains(got[2].Detail, "=> github.com/andybalholm/brotli@v1.2.0") || !strings.Contains(got[3].Detail, "../local") {
		t.Fatalf("%+v", got)
	}
}
