package main

import (
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"runtime"
	"strings"
	"testing"
)

func TestForeignInputsUseNormalizedTargetTags(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("test process uses a POSIX executable path")
	}
	module := isolatedModule(t)
	tool := filepath.Join(t.TempDir(), "hookrelease")
	if out, err := exec.Command("go", "build", "-o", tool, "./cmd/hookrelease").CombinedOutput(); err != nil {
		t.Fatalf("build hookrelease: %v: %s", err, out)
	}
	id := func() string {
		t.Helper()
		// Audited: tool is hookrelease built above in this test's temporary directory.
		// Arguments are fixed and no shell runs.
		// nosemgrep: dangerous-exec-command, go.lang.security.audit.dangerous-exec-command.dangerous-exec-command
		cmd := exec.Command(tool, "id", "--goos", "linux", "--goarch", "amd64") //nolint:gosec // G204: audited above
		cmd.Env = append(os.Environ(), "GOARCH=amd64", "GOAMD64=v4")
		out, err := cmd.CombinedOutput()
		if err != nil {
			t.Fatalf("id with ambient v4: %v: %s", err, out)
		}
		return strings.TrimSpace(string(out))
	}
	before := id()
	mustWrite(t, filepath.Join(module, "cmd", "agent-hook", "unsupported.c"), []byte("//go:build amd64.v4\n\nvoid unsupported(void) {}\n"))
	if after := id(); after != before {
		t.Fatalf("excluded v4 C file changed v1 ID: %s != %s", after, before)
	}
}

func TestReleaseIDRefusesCgo(t *testing.T) {
	module := isolatedModule(t)
	mustWrite(t, filepath.Join(module, "cmd", "agent-hook", "unsupported.go"), []byte("package main\nimport \"C\"\n"))
	if code, _, stderr := releaseCommand(t, "id"); code != 2 || !strings.Contains(stderr, "C source files") {
		t.Fatalf("cgo id exit %d, want 2 and refusal: %s", code, stderr)
	}
}

func TestReleaseIDReadsGoVersionFromToolchain(t *testing.T) {
	isolatedModule(t)
	code, before, stderr := releaseCommand(t, "id")
	if code != 0 {
		t.Fatalf("id exit %d: %s", code, stderr)
	}
	installGoWrapper(t, `if [ "$1" = env ] && [ "$2" = -json ]; then
  "$real_go" "$@" | sed 's/"GOVERSION": "[^"]*"/"GOVERSION": "go1.27.999"/'
  exit $?
fi`)
	code, after, stderr := releaseCommand(t, "id")
	if code != 0 || after == before {
		t.Fatalf("changed go env GOVERSION: exit %d, ID %q, original %q: %s", code, after, before, stderr)
	}
}

func TestReleaseIDIncludesNonGoInputs(t *testing.T) {
	module := isolatedModule(t)
	code, before, stderr := releaseCommand(t, "id")
	if code != 0 {
		t.Fatalf("id exit %d: %s", code, stderr)
	}
	for _, name := range []string{"asm.s", "x.h", "x.syso"} {
		t.Run(name, func(t *testing.T) {
			file := filepath.Join(module, "cmd", "agent-hook", name)
			mustWrite(t, file, []byte("release input\n"))
			t.Cleanup(func() { os.Remove(file) })
			code, after, stderr := releaseCommand(t, "id")
			if code != 0 || after == before {
				t.Fatalf("%s id exit %d, ID %q, original %q: %s", name, code, after, before, stderr)
			}
		})
	}
}

func TestReleaseIDCommand(t *testing.T) {
	isolatedModule(t)
	code, host, stderr := releaseCommand(t, "id")
	if code != 0 || !releaseDir.MatchString(host) {
		t.Fatalf("id exit %d, output %q: %s", code, host, stderr)
	}
	otherOS := "windows"
	if runtime.GOOS == otherOS {
		otherOS = "linux"
	}
	code, other, stderr := releaseCommand(t, "id", "--goos", otherOS, "--goarch", "amd64")
	if code != 0 || !releaseDir.MatchString(other) || other == host {
		t.Fatalf("target id exit %d, output %q, host %q: %s", code, other, host, stderr)
	}
	for _, flag := range []string{"--goos", "--goarch"} {
		if code, _, stderr := releaseCommand(t, "build", "--into", filepath.Join(t.TempDir(), "releases"), flag, "invalid"); code != 2 || !strings.Contains(stderr, "flag provided but not defined") {
			t.Fatalf("build accepts %s: exit %d: %s", flag, code, stderr)
		}
	}
}

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
