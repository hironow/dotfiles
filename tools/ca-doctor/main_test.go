package main

import (
	"bytes"
	"context"
	"os"
	"path/filepath"
	"runtime"
	"slices"
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
	}{{"OK", 0}, {"INFO", 0}, {"WARN", 1}, {"ERR", 2}} {
		var out bytes.Buffer
		if got := Report(&out, []Finding{{tc.level, "test", "detail\nERR forged"}}); got != tc.want {
			t.Fatal(got)
		}
		if strings.Count(out.String(), "\n") != 1 {
			t.Fatal("line protocol injection", out.String())
		}
	}
}

func TestLiveClientsStartWithTheDiagnosticBinaryAndSkipUnusableTools(t *testing.T) {
	tools := []toolSpec{
		{Name: "curl", Kind: "curl", Path: `C:\tools\curl.exe`},
		{Name: "git", Path: `C:\tools\git.exe`},
		{Name: "node", Kind: "node"},
		{Name: "bun", Kind: "bun", Path: `C:\tools\bun.cmd`},
	}
	for _, tc := range []struct {
		goos string
		want []string
	}{
		{"linux", []string{"diagnostic-go", "curl", "bun"}},
		{"windows", []string{"diagnostic-go", "curl"}},
	} {
		t.Run(tc.goos, func(t *testing.T) {
			clients := liveClients(tools, tc.goos)
			names := make([]string, 0, len(clients))
			for _, client := range clients {
				names = append(names, client.Name)
			}
			if !slices.Equal(names, tc.want) {
				t.Fatalf("clients %v, want %v", names, tc.want)
			}
			if _, ok := clients[0].Prober.(GoProbe); !ok {
				t.Fatalf("diagnostic-go prober is %T", clients[0].Prober)
			}
			if probe, ok := clients[1].Prober.(ExternalProbe); !ok || probe.Path != tools[0].Path || probe.Kind != "curl" {
				t.Fatalf("curl prober is %#v", clients[1].Prober)
			}
		})
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

// The scope and advice lines read the same on every run, so they are INFO.
func TestOfflineCLIReportsCaveatsAsInfo(t *testing.T) {
	t.Setenv("PATH", t.TempDir())
	var out bytes.Buffer
	_ = RunCLI(context.Background(), []string{"--source", ".", "--offline"}, &out)
	text := out.String()
	for _, want := range []string{"INFO ca-coverage - ", "INFO ca-platform - ", "INFO ca-remediation - ", "INFO ca-advice-"} {
		if !strings.Contains(text, want) {
			t.Errorf("missing %q:\n%s", want, text)
		}
	}
	for _, unwanted := range []string{"WARN ca-coverage", "WARN ca-advice", "WARN ca-platform"} {
		if strings.Contains(text, unwanted) {
			t.Errorf("caveat still warns: %q", unwanted)
		}
	}
}

// --summary is what doctor passes. The usage line must name it, so an old
// binary's ca-arguments error is recognisable as "rebuild me".
func TestCLIAcceptsSummary(t *testing.T) {
	t.Setenv("PATH", t.TempDir())
	var out bytes.Buffer
	_ = RunCLI(context.Background(), []string{"--source", ".", "--offline", "--summary"}, &out)
	if strings.Contains(out.String(), "ca-arguments") {
		t.Fatal(out.String())
	}
	out.Reset()
	if code := RunCLI(context.Background(), []string{"--bogus"}, &out); code != 2 || !strings.Contains(out.String(), "[--summary]") {
		t.Fatal(code, out.String())
	}
}

// Summary mode drops the per-chain lines; the per-client line carries the counts.
func TestSummaryDropsPerChainLines(t *testing.T) {
	findings := []Finding{
		{"INFO", "ca-live-x-node", "control=accepted"},
		{"INFO", "ca-chain-x-node", "a: certificate-rejected"},
		{"ERR", "ca-chain-x-curl", "b: accepted"},
		{"OK", "ca-https-node", "baseline"},
	}
	got := Summarize(findings)
	if len(got) != 2 || got[0].Name != "ca-live-x-node" || got[1].Name != "ca-https-node" {
		t.Fatal(got)
	}
}

// A per-chain line carries the same level rule as the per-client line.
func TestChainLevels(t *testing.T) {
	for _, tc := range []struct {
		outcome Outcome
		want    string
	}{{Accepted, "ERR"}, {CertRejected, "INFO"}, {Unknown, "WARN"}} {
		if got := ChainEvidence(incidents[0], "test", 0, tc.outcome); got.Level != tc.want {
			t.Fatalf("%s: %+v want %s", tc.outcome, got, tc.want)
		}
	}
}

func TestMissingToolIsInfo(t *testing.T) {
	got := inspectTool(context.Background(), toolSpec{Name: "rustc"})
	if len(got) != 1 || got[0].Level != "INFO" || got[0].Name != "ca-tool-rustc" {
		t.Fatal(got)
	}
}

// A tool that runs is a fact about this machine, not a problem.
func TestActiveToolAndRustCaveatAreInfo(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("the fake tool is a shell script")
	}
	dir := t.TempDir()
	rustc := filepath.Join(dir, "rustc")
	if err := os.WriteFile(rustc, []byte("#!/bin/sh\necho 'rustc 1.99.1 (fake)'\n"), 0o755); err != nil {
		t.Fatal(err)
	}
	got := inspectTool(context.Background(), toolSpec{Name: "rustc", Path: rustc, Args: []string{"--version"}})
	if len(got) != 2 || got[0].Name != "ca-tool-rustc" || got[0].Level != "INFO" || got[1].Name != "ca-rust" || got[1].Level != "INFO" {
		t.Fatal(got)
	}
}

func TestOSBundleInventoryIsInfo(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("the fake package query is a shell script")
	}
	dir := t.TempDir()
	query := filepath.Join(dir, "dpkg-query")
	if err := os.WriteFile(query, []byte("#!/bin/sh\nprintf '20260101'\n"), 0o755); err != nil {
		t.Fatal(err)
	}
	t.Setenv("PATH", dir)
	got := storeInventory(context.Background(), "linux")
	if len(got) != 1 || got[0].Name != "ca-os-bundle" || got[0].Level != "INFO" {
		t.Fatal(got)
	}
}

// Windows keeps its root store and disallowed list up to date through Windows
// Update; there is no package whose version could be read, so a WARN there
// could never clear.
func TestOSBundleOnWindowsIsInfoWithoutAPackageQuery(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("the fake package query is a shell script")
	}
	dir := t.TempDir()
	marker := filepath.Join(dir, "queried")
	query := filepath.Join(dir, "dpkg-query")
	if err := os.WriteFile(query, []byte("#!/bin/sh\ntouch '"+marker+"'\nprintf '20260101'\n"), 0o755); err != nil {
		t.Fatal(err)
	}
	t.Setenv("PATH", dir)
	got := storeInventory(context.Background(), "windows")
	if len(got) != 1 || got[0].Name != "ca-os-bundle" || got[0].Level != "INFO" || !strings.Contains(got[0].Detail, "Windows Update") {
		t.Fatal(got)
	}
	if _, err := os.Stat(marker); err == nil {
		t.Fatal("a package query ran on Windows")
	}
}

func TestOSBundleUnknownOnLinuxStaysWarn(t *testing.T) {
	t.Setenv("PATH", t.TempDir())
	got := storeInventory(context.Background(), "linux")
	if len(got) != 1 || got[0].Level != "WARN" {
		t.Fatal(got)
	}
}
