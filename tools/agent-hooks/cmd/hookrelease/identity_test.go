package main

import (
	"reflect"
	"strings"
	"testing"
)

func TestReleaseIDTracksOnlyBuildInputs(t *testing.T) {
	target := buildTarget{OS: "linux", Arch: "amd64"}
	files := []fileDigest{{Path: "go.mod", SHA256: "aaa"}, {Path: "cmd/agent-hook/main.go", SHA256: "bbb"}}
	id := releaseID("go1.27.3", target, "example.test/hooks", files)
	if len(id) != 16 {
		t.Fatalf("release ID = %q, want 16 lowercase hex characters", id)
	}
	if strings.Trim(id, "0123456789abcdef") != "" {
		t.Fatalf("release ID is not lowercase hex: %q", id)
	}
	reversed := []fileDigest{files[1], files[0]}
	if got := releaseID("go1.27.3", target, "example.test/hooks", reversed); got != id {
		t.Fatalf("input ordering changes ID: %s != %s", got, id)
	}
	for _, tc := range []struct {
		name, version string
		target        buildTarget
		files         []fileDigest
	}{
		{"Go version", "go1.27.4", target, files},
		{"OS", "go1.27.3", buildTarget{OS: "windows", Arch: "amd64"}, files},
		{"architecture", "go1.27.3", buildTarget{OS: "linux", Arch: "arm64"}, files},
		{"file bytes", "go1.27.3", target, []fileDigest{{Path: "go.mod", SHA256: "changed"}, files[1]}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			if got := releaseID(tc.version, tc.target, "example.test/hooks", tc.files); got == id {
				t.Fatalf("%s did not change ID %s", tc.name, got)
			}
		})
	}
	if !reflect.DeepEqual(files, []fileDigest{{Path: "go.mod", SHA256: "aaa"}, {Path: "cmd/agent-hook/main.go", SHA256: "bbb"}}) {
		t.Fatal("release ID mutated its inputs")
	}
}
