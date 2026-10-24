package main

import (
	"bytes"
	"context"
	"encoding/json/v2"
	"path/filepath"
	"strings"
	"testing"
)

func TestCLIReportsUnknownNotClearanceAndUsageErrors(t *testing.T) {
	for _, args := range [][]string{{"--mise=false", "--path=false"}, {"--max-bytes=0"}, {"--bad-option"}} {
		var out bytes.Buffer
		if code := runCLI(context.Background(), args, &out); code != 2 {
			t.Fatalf("%v code=%d: %s", args, code, &out)
		}
	}
	dir := t.TempDir()
	path := filepath.Join(dir, "malformed")
	putFile(t, path, "\x7fELFbroken")
	var out bytes.Buffer
	code := runCLI(context.Background(), []string{"--json", path}, &out)
	var report Report
	if err := json.Unmarshal(out.Bytes(), &report); err != nil {
		t.Fatal(err, out.String())
	}
	if code != 1 || !report.Incomplete {
		t.Fatalf("code=%d report=%+v", code, report)
	}
	out.Reset()
	putFile(t, path, "#!/bin/sh\nexit 42\n")
	code = runCLI(context.Background(), []string{path}, &out)
	if code != 0 || !strings.Contains(out.String(), "NOT a security clearance") || !strings.Contains(out.String(), "non-native=1") {
		t.Fatalf("code=%d: %s", code, &out)
	}
}

func TestGoBuildMetadataAloneIsUnknown(t *testing.T) {
	if evidenceState([]Evidence{{"go-build", "go1.27.3"}}) != "UNKNOWN" {
		t.Fatal("Go version became Brotli evidence")
	}
}

func TestCLIOutputsAreTerminalEscapedAndMissingMiseIsIncomplete(t *testing.T) {
	var out bytes.Buffer
	if err := outputReport(&out, Report{Findings: []Finding{{Path: "evil\x1b[31m", Issues: []string{"bad\x1b"}}}}, false); err != nil {
		t.Fatal(err)
	}
	if strings.ContainsRune(out.String(), '\x1b') {
		t.Fatal("raw terminal control emitted")
	}
	t.Setenv("PATH", t.TempDir())
	out.Reset()
	if code := runCLI(context.Background(), []string{"--path=false", "--json"}, &out); code != 1 {
		t.Fatalf("missing mise code=%d: %s", code, &out)
	}
}
