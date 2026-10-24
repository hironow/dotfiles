package main

import (
	"context"
	"debug/pe"
	"encoding/binary"
	"io"
	"os"
	"path/filepath"
	"testing"
)

type countedSection struct {
	prefix []byte
	read   int
}

func (r *countedSection) ReadAt(p []byte, off int64) (int, error) {
	r.read += len(p)
	clear(p)
	if off < int64(len(r.prefix)) {
		copy(p, r.prefix[off:])
	}
	return len(p), nil
}

func TestPEImportsReadBoundedRangesInsteadOfWholeSections(t *testing.T) {
	prefix := make([]byte, 100)
	binary.LittleEndian.PutUint32(prefix[12:16], 1060)
	copy(prefix[60:], "libbrotli.dll\x00")
	reader := &countedSection{prefix: prefix}
	header := &pe.OptionalHeader64{NumberOfRvaAndSizes: 2}
	header.DataDirectory[pe.IMAGE_DIRECTORY_ENTRY_IMPORT] = pe.DataDirectory{VirtualAddress: 1000, Size: 40}
	f := &pe.File{OptionalHeader: header, Sections: []*pe.Section{{SectionHeader: pe.SectionHeader{VirtualAddress: 1000, Size: 1 << 20}, ReaderAt: reader}}}
	libraries, err := peLibraries(context.Background(), f)
	if err != nil || len(libraries) != 1 || libraries[0] != "libbrotli.dll" || reader.read > 8192 {
		t.Fatalf("libraries=%v bytes=%d err=%v", libraries, reader.read, err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	reader.read = 0
	if _, err := peLibraries(ctx, f); err == nil || reader.read != 0 {
		t.Fatalf("cancellation ignored: bytes=%d err=%v", reader.read, err)
	}
}

func TestInventoryStopsBeforeOpeningMoreDirectoriesAfterLimit(t *testing.T) {
	root := t.TempDir()
	for _, name := range []string{"a.exe", "b.exe", "c.exe"} {
		putFile(t, filepath.Join(root, name), "hello")
	}
	c := collector{seen: map[string]bool{}, ctx: context.Background(), limit: 2}
	if err := c.readPATH(root); err == nil || len(c.result.Paths) != 2 {
		t.Fatalf("limit not enforced: %+v", c.result)
	}
	// A missing directory must not even be opened after exhaustion.
	if err := c.readPATH(filepath.Join(root, "missing")); err == nil || os.IsNotExist(err) {
		t.Fatalf("enumerated after limit: %v", err)
	}
}

// Keep io.ReaderAt conformance checked separately from PE implementation details.
var _ io.ReaderAt = (*countedSection)(nil)
