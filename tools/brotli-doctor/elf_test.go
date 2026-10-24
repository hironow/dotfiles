package main

import (
	"bytes"
	"context"
	"debug/elf"
	"encoding/binary"
	"os"
	"path/filepath"
	"testing"
)

func writeLE(t *testing.T, w *bytes.Buffer, value any) {
	t.Helper()
	if err := binary.Write(w, binary.LittleEndian, value); err != nil {
		t.Fatal(err)
	}
}

func elfFixture(t *testing.T, defined bool, brokenSymbols bool) []byte {
	t.Helper()
	dynstr := []byte("\x00libbrotlidec.so.1\x00")
	strtab := []byte("\x00BrotliDecoderCreateInstance\x00")
	var dyn, symbols bytes.Buffer
	writeLE(t, &dyn, elf.Dyn64{Tag: int64(elf.DT_NEEDED), Val: 1})
	writeLE(t, &dyn, elf.Dyn64{Tag: int64(elf.DT_NULL)})
	writeLE(t, &symbols, elf.Sym64{})
	symbol := elf.Sym64{Name: 1}
	if defined {
		symbol.Shndx = 1
	}
	writeLE(t, &symbols, symbol)
	data := make([]byte, 64)
	sections := []elf.Section64{{}}
	for i, body := range [][]byte{dynstr, dyn.Bytes(), strtab, symbols.Bytes()} {
		section := elf.Section64{Off: uint64(len(data)), Size: uint64(len(body))}
		switch i {
		case 0, 2:
			section.Type = uint32(elf.SHT_STRTAB)
		case 1:
			section.Type = uint32(elf.SHT_DYNAMIC)
			section.Link = 1
			section.Entsize = 16
		case 3:
			section.Type = uint32(elf.SHT_SYMTAB)
			section.Link = 3
			section.Entsize = 24
			if brokenSymbols {
				section.Link = 999
			}
		}
		data = append(data, body...)
		sections = append(sections, section)
	}
	header := elf.Header64{Type: uint16(elf.ET_EXEC), Machine: uint16(elf.EM_X86_64), Version: 1, Shoff: uint64(len(data)), Ehsize: 64, Shentsize: 64, Shnum: uint16(len(sections))}
	copy(header.Ident[:], []byte{0x7f, 'E', 'L', 'F', byte(elf.ELFCLASS64), byte(elf.ELFDATA2LSB), 1})
	var encoded bytes.Buffer
	writeLE(t, &encoded, header)
	copy(data, encoded.Bytes())
	for _, section := range sections {
		encoded.Reset()
		writeLE(t, &encoded, section)
		data = append(data, encoded.Bytes()...)
	}
	return data
}

func TestELFImportsDefinedUndefinedAndBrokenSymbols(t *testing.T) {
	for _, tt := range []struct {
		name            string
		defined, broken bool
		kind            string
	}{{"defined", true, false, "c-defined-symbol"}, {"undefined", false, false, "c-undefined-symbol"}, {"broken", true, true, ""}} {
		t.Run(tt.name, func(t *testing.T) {
			path := filepath.Join(t.TempDir(), "image")
			if err := os.WriteFile(path, elfFixture(t, tt.defined, tt.broken), 0o700); err != nil {
				t.Fatal(err)
			}
			finding, native := inspect(context.Background(), path, 512<<20)
			if !native || len(finding.Images) != 1 {
				t.Fatalf("%+v", finding)
			}
			image := finding.Images[0]
			if !hasEvidence(image.Evidence, "dynamic-import", "libbrotlidec.so.1") {
				t.Fatalf("import missing: %+v", finding)
			}
			if tt.broken {
				if len(image.Issues) == 0 {
					t.Fatal("symbol failure hidden")
				}
				return
			}
			if len(image.Issues) > 0 || !hasEvidence(image.Evidence, tt.kind, "BrotliDecoder") {
				t.Fatalf("%+v", finding)
			}
		})
	}
}
