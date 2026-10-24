package main

import (
	"bytes"
	"context"
	"encoding/binary"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func TestInspectSkipsScriptWithoutExecutingAndRejectsOversize(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "script")
	marker := filepath.Join(dir, "executed")
	putFile(t, path, "#!/bin/sh\ntouch "+marker+"\n")
	finding, native := inspect(context.Background(), path, 512<<20)
	if native || len(finding.Issues) != 0 {
		t.Fatalf("%+v native=%v", finding, native)
	}
	if _, err := os.Stat(marker); !os.IsNotExist(err) {
		t.Fatal("target executed")
	}
	putFile(t, path, "\x7fELFbroken")
	finding, native = inspect(context.Background(), path, 512<<20)
	if !native || len(finding.Issues) == 0 {
		t.Fatal("malformed native image silently skipped")
	}
	finding, _ = inspect(context.Background(), path, 2)
	if len(finding.Issues) == 0 {
		t.Fatal("size limit silently accepted")
	}
}

func TestNativeFormatsAndStrippedBuildInfo(t *testing.T) {
	if testing.Short() {
		t.Skip("cross-build integration; run go test without -short")
	}
	dir := t.TempDir()
	source := filepath.Join(dir, "main.go")
	putFile(t, source, "package main\nfunc main() {}\n")
	for _, target := range []struct{ os, arch, format string }{{"linux", "amd64", "ELF"}, {"darwin", "arm64", "Mach-O"}, {"windows", "amd64", "PE"}} {
		t.Run(target.os, func(t *testing.T) {
			path := filepath.Join(dir, target.os+".bin")
			cmd := exec.Command("go", "build", "-ldflags=-s -w", "-o", path, source)
			cmd.Env = append(os.Environ(), "GOOS="+target.os, "GOARCH="+target.arch, "CGO_ENABLED=0", "GOTOOLCHAIN=local")
			if data, err := cmd.CombinedOutput(); err != nil {
				t.Fatalf("build: %v %s", err, data)
			}
			finding, native := inspect(context.Background(), path, 512<<20)
			if !native || len(finding.Issues) > 0 || len(finding.Images) != 1 || len(finding.Images[0].Issues) > 0 || finding.Images[0].Format != target.format {
				t.Fatalf("%+v", finding)
			}
			if !hasEvidence(finding.Images[0].Evidence, "go-build", "go1.") {
				t.Fatalf("stripped build metadata missing: %+v", finding)
			}
			data, err := os.ReadFile(path)
			if err != nil {
				t.Fatal(err)
			}
			switch target.os {
			case "windows":
				if !bytes.Contains(data, []byte("kernel32.dll")) {
					t.Fatal("fixture has no kernel32.dll")
				}
				data = bytes.ReplaceAll(data, []byte("kernel32.dll"), []byte("brotli64.dll"))
			case "darwin":
				old := []byte("/usr/lib/libSystem.B.dylib")
				if !bytes.Contains(data, old) {
					t.Fatal("fixture has no libSystem")
				}
				replacement := append([]byte("/usr/lib/libbrotli.dylib"), make([]byte, len(old)-len("/usr/lib/libbrotli.dylib"))...)
				data = bytes.ReplaceAll(data, old, replacement)
			default:
				return
			}
			if err := os.WriteFile(path, data, 0o700); err != nil {
				t.Fatal(err)
			}
			finding, _ = inspect(context.Background(), path, 512<<20)
			if !hasEvidence(finding.Images[0].Evidence, "dynamic-import", "brotli") {
				t.Fatalf("dynamic import not found: %+v", finding)
			}
		})
	}
}

func hasEvidence(evidence []Evidence, kind, detail string) bool {
	for _, e := range evidence {
		if e.Kind == kind && strings.Contains(e.Detail, detail) {
			return true
		}
	}
	return false
}

func TestPEImportDescriptorsIncludeOrdinalOnlyDLL(t *testing.T) {
	// Two descriptors: the first imports only by ordinal (no function names needed).
	data := make([]byte, 80)
	binary.LittleEndian.PutUint32(data[12:16], 1060)
	copy(data[60:], "brotlidec.dll\x00")
	names, err := importDescriptors(context.Background(), bytes.NewReader(data), func(rva uint32) (string, error) { return cString(data[rva-1000:]) })
	if err != nil || len(names) != 1 || names[0] != "brotlidec.dll" {
		t.Fatalf("%v %v", names, err)
	}
	_, err = importDescriptors(context.Background(), bytes.NewReader(data[:20]), func(uint32) (string, error) { return "", os.ErrInvalid })
	if err == nil {
		t.Fatal("malformed descriptor accepted")
	}
}
