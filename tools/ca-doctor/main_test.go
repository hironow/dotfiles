package main

import (
	"bytes"
	"context"
	"strings"
	"testing"
)

func TestCLIRejectsUnverifiableBuildBeforeRunningChecks(t *testing.T) {
	var out bytes.Buffer
	code := RunCLI(context.Background(), []string{"--source", t.TempDir(), "--offline"}, &out)
	if code != 1 || !strings.HasPrefix(out.String(), "WARN ca-build - ") || strings.Contains(out.String(), "OK   ") {
		t.Fatal(code, out.String())
	}
}

func TestOfflineCLIWiresRemediationOnceWithoutHidingErrors(t *testing.T) {
	// No PATH tools are required; offline mode never probes TLS endpoints.
	t.Setenv("PATH", t.TempDir())
	t.Setenv("GIT_SSL_NO_VERIFY", "1")
	var out bytes.Buffer
	code := RunCLI(context.Background(), []string{"--source", ".", "--offline"}, &out)
	if code != 2 || strings.Count(out.String(), " ca-remediation - ") != 1 || !strings.Contains(out.String(), "ERR  ca-env") || !strings.Contains(out.String(), "WARN ca-live - offline requested") {
		t.Fatal(code, out.String())
	}
}

func TestReportExitContract(t *testing.T) {
	for _, tc := range []struct {
		level string
		want  int
	}{{"OK", 0}, {"WARN", 1}, {"ERR", 2}} {
		var out bytes.Buffer
		if got := Report(&out, []Finding{{tc.level, "test", "detail\nERR forged"}}); got != tc.want {
			t.Fatal(got)
		}
		if strings.Count(out.String(), "\n") != 1 {
			t.Fatal("line protocol injection", out.String())
		}
	}
}

func TestDiscoveryIncludesMise(t *testing.T) {
	for _, tool := range discoverTools() {
		if tool.Name == "mise" && tool.Command == "mise" && len(tool.Args) == 1 && tool.Args[0] == "--version" {
			return
		}
	}
	t.Fatal("mise must be assessed, including the bootstrap security floor")
}

func TestVersionExtractionRejectsTrailingPrereleaseAndGarbage(t *testing.T) {
	for _, tc := range []struct{ tool, output, want string }{
		{"go", "go version go1.27.3 darwin/arm64\n", "1.27.3"},
		{"node", "v24.22.1\n", "24.22.1"},
		{"node", "v24.22.1-rc.1\n", "24.22.1-rc.1"},
		{"uv", "uv 0.13.4 (xyz 2026-10-20)", "0.13.4"},
		{"rustup", "rustup 1.29.2 (xyz)", "1.29.2"},
		{"mise", "2026.10.17 macos-arm64 (abc 2026-10-17)", "2026.10.17"},
		{"mise", "2026.10.17-rc.1 macos-arm64", "2026.10.17-rc.1"},
		{"mise", "warning hello\n2026.10.17", "warning hello\n2026.10.17"},
		{"node", "warning hello\nv24.22.1", "warning hello\nv24.22.1"},
	} {
		if got := ExtractVersion(tc.tool, tc.output); got != tc.want {
			t.Errorf("%s: %q want %q", tc.tool, got, tc.want)
		}
	}
}
