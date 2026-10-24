package main

import (
	"bytes"
	"context"
	"debug/macho"
	"encoding/binary"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
)

func TestFatMachOSeparatesArchitecturesAndReportsBrokenSlice(t *testing.T) {
	if testing.Short() {
		t.Skip("cross-build integration")
	}
	dir := t.TempDir()
	source := filepath.Join(dir, "main.go")
	putFile(t, source, "package main\nfunc main() {}\n")
	payloads := [][]byte{}
	arches := []macho.FatArchHeader{}
	offset := uint32(4096)
	for _, arch := range []string{"amd64", "arm64"} {
		path := filepath.Join(dir, arch)
		cmd := exec.Command("go", "build", "-o", path, source)
		cmd.Env = append(os.Environ(), "GOOS=darwin", "GOARCH="+arch, "CGO_ENABLED=0", "GOTOOLCHAIN=local")
		if data, err := cmd.CombinedOutput(); err != nil {
			t.Fatalf("build: %v %s", err, data)
		}
		data, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		f, err := macho.NewFile(bytes.NewReader(data))
		if err != nil {
			t.Fatal(err)
		}
		arches = append(arches, macho.FatArchHeader{Cpu: f.Cpu, SubCpu: f.SubCpu, Offset: offset, Size: uint32(len(data)), Align: 12})
		payloads = append(payloads, data)
		offset = (offset + uint32(len(data)) + 4095) &^ 4095
	}
	var buf bytes.Buffer
	if err := binary.Write(&buf, binary.BigEndian, []uint32{macho.MagicFat, 2}); err != nil {
		t.Fatal(err)
	}
	for _, arch := range arches {
		if err := binary.Write(&buf, binary.BigEndian, arch); err != nil {
			t.Fatal(err)
		}
	}
	image := buf.Bytes()
	for i, arch := range arches {
		image = append(image, make([]byte, int(arch.Offset)-len(image))...)
		image = append(image, payloads[i]...)
	}
	path := filepath.Join(dir, "fat")
	if err := os.WriteFile(path, image, 0o700); err != nil {
		t.Fatal(err)
	}
	result, native := inspect(context.Background(), path, 512<<20)
	if !native || len(result.Issues) > 0 || len(result.Images) != 2 {
		t.Fatalf("%+v", result)
	}
	for _, slice := range result.Images {
		if len(slice.Issues) > 0 || !hasEvidence(slice.Evidence, "go-build", "go1.") {
			t.Fatalf("%+v", slice)
		}
	}
	if result.Images[0].Architecture == result.Images[1].Architecture {
		t.Fatal("architecture attribution lost")
	}
	if err := os.WriteFile(path, image[:int(arches[1].Offset)+4], 0o700); err != nil {
		t.Fatal(err)
	}
	report := scan(context.Background(), Inventory{Paths: []string{path}}, 512<<20)
	if !report.Incomplete {
		t.Fatal("broken slice accepted as complete")
	}
}
