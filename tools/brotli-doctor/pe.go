package main

import (
	"bytes"
	"context"
	"debug/pe"
	"encoding/binary"
	"errors"
	"fmt"
	"io"
)

func readPE(ctx context.Context, r io.ReaderAt) (Image, error) {
	image := Image{Format: "PE"}
	f, err := pe.NewFile(r)
	if err != nil {
		return image, fmt.Errorf("PE: %w", err)
	}
	image.Architecture = fmt.Sprintf("machine-%#x", f.Machine)
	libraries, err := peLibraries(ctx, f)
	addLibraries(&image, libraries, err)
	for _, s := range f.Symbols {
		if cAPI(s.Name) {
			kind := "c-defined-symbol"
			if s.SectionNumber <= 0 {
				kind = "c-undefined-symbol"
			}
			image.Evidence = append(image.Evidence, Evidence{kind, s.Name})
		}
	}
	return image, nil
}

// debug/pe.ImportedLibraries is an unimplemented stub in Go 1.27.
// Read descriptors directly, including DLLs imported only by ordinal.
func peLibraries(ctx context.Context, f *pe.File) ([]string, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	var directory pe.DataDirectory
	switch h := f.OptionalHeader.(type) {
	case *pe.OptionalHeader64:
		if h.NumberOfRvaAndSizes <= pe.IMAGE_DIRECTORY_ENTRY_IMPORT {
			return nil, nil
		}
		directory = h.DataDirectory[pe.IMAGE_DIRECTORY_ENTRY_IMPORT]
	case *pe.OptionalHeader32:
		if h.NumberOfRvaAndSizes <= pe.IMAGE_DIRECTORY_ENTRY_IMPORT {
			return nil, nil
		}
		directory = h.DataDirectory[pe.IMAGE_DIRECTORY_ENTRY_IMPORT]
	default:
		return nil, errors.New("PE executable has no optional header")
	}
	if directory.VirtualAddress == 0 {
		return nil, nil
	}
	table, err := peRange(f, directory.VirtualAddress, 20*4096)
	if err != nil {
		return nil, err
	}
	return importDescriptors(ctx, table, func(rva uint32) (string, error) {
		if err := ctx.Err(); err != nil {
			return "", err
		}
		r, err := peRange(f, rva, 4096)
		if err != nil {
			return "", err
		}
		data, err := io.ReadAll(contextReader{ctx: ctx, r: r})
		if err != nil {
			return "", err
		}
		return cString(data)
	})
}

// Bound each read, rather than repeatedly materializing an entire section.
func peRange(f *pe.File, rva uint32, limit int64) (io.Reader, error) {
	for _, section := range f.Sections {
		if rva < section.VirtualAddress {
			continue
		}
		offset := int64(rva - section.VirtualAddress)
		if offset >= int64(section.Size) {
			continue
		}
		return io.NewSectionReader(section, offset, min(limit, int64(section.Size)-offset)), nil
	}
	return nil, errors.New("PE import RVA outside file-backed sections")
}

func importDescriptors(ctx context.Context, r io.Reader, readName func(uint32) (string, error)) ([]string, error) {
	var names []string
	var descriptor [20]byte
	for i := 0; i < 4096; i++ {
		if err := ctx.Err(); err != nil {
			return names, err
		}
		if _, err := io.ReadFull(r, descriptor[:]); err != nil {
			return names, fmt.Errorf("truncated PE import descriptors: %w", err)
		}
		if bytes.Equal(descriptor[:], make([]byte, 20)) {
			return names, nil
		}
		name, err := readName(binary.LittleEndian.Uint32(descriptor[12:16]))
		if err != nil {
			return names, err
		}
		names = append(names, name)
	}
	return names, errors.New("PE import descriptor limit exceeded")
}

func cString(data []byte) (string, error) {
	if end := bytes.IndexByte(data[:min(len(data), 4096)], 0); end > 0 {
		return string(data[:end]), nil
	}
	return "", errors.New("missing/unterminated PE library name")
}
