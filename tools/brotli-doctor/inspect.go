package main

import (
	"bytes"
	"context"
	"debug/buildinfo"
	"debug/elf"
	"debug/macho"
	"errors"
	"fmt"
	"io"
	"os"
)

func inspect(ctx context.Context, path string, maxBytes int64) (Finding, bool) {
	result := Finding{Path: path}
	f, err := openRegular(path, maxBytes)
	if err != nil {
		result.Issues = []string{err.Error()}
		return result, false
	}
	defer f.Close()
	info, err := f.Stat()
	if err != nil {
		result.Issues = []string{err.Error()}
		return result, false
	}
	reader := io.NewSectionReader(f, 0, info.Size())
	header := make([]byte, 4)
	if _, err := reader.ReadAt(header, 0); err != nil {
		return result, false
	}
	format := nativeFormat(header)
	if format == "" {
		return result, false
	}
	images, err := readImages(ctx, reader, format)
	result.Images = images
	if err != nil {
		result.Issues = append(result.Issues, err.Error())
	}
	// Metadata and strings are read per slice, never attributed across fat architectures.
	if format != "Mach-O-fat" && len(images) == 1 {
		enrich(ctx, reader, &result.Images[0])
	}
	return result, true
}

func openRegular(path string, maxBytes int64) (*os.File, error) {
	info, err := os.Stat(path)
	if err != nil {
		return nil, err
	}
	if !info.Mode().IsRegular() {
		return nil, errors.New("nonregular file excluded")
	}
	if info.Size() > maxBytes {
		return nil, fmt.Errorf("image exceeds inspection limit (%d bytes)", maxBytes)
	}
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	current, err := f.Stat()
	if err != nil || !current.Mode().IsRegular() || current.Size() > maxBytes || !os.SameFile(info, current) {
		_ = f.Close()
		return nil, errors.New("file changed or is not a bounded regular file")
	}
	return f, nil
}

func nativeFormat(header []byte) string {
	switch {
	case bytes.Equal(header, []byte{0x7f, 'E', 'L', 'F'}):
		return "ELF"
	case bytes.Equal(header, []byte{0xca, 0xfe, 0xba, 0xbe}), bytes.Equal(header, []byte{0xca, 0xfe, 0xba, 0xbf}), bytes.Equal(header, []byte{0xbe, 0xba, 0xfe, 0xca}), bytes.Equal(header, []byte{0xbf, 0xba, 0xfe, 0xca}):
		return "Mach-O-fat"
	case bytes.Equal(header, []byte{0xfe, 0xed, 0xfa, 0xce}), bytes.Equal(header, []byte{0xce, 0xfa, 0xed, 0xfe}), bytes.Equal(header, []byte{0xfe, 0xed, 0xfa, 0xcf}), bytes.Equal(header, []byte{0xcf, 0xfa, 0xed, 0xfe}):
		return "Mach-O"
	case bytes.HasPrefix(header, []byte("MZ")):
		return "PE"
	default:
		return ""
	}
}

func readImages(ctx context.Context, r *io.SectionReader, format string) ([]Image, error) {
	switch format {
	case "ELF":
		image, err := readELF(r)
		return []Image{image}, err
	case "Mach-O":
		f, err := macho.NewFile(r)
		if err != nil {
			return nil, err
		}
		return []Image{machoImage(f)}, nil
	case "PE":
		image, err := readPE(ctx, r)
		return []Image{image}, err
	case "Mach-O-fat":
		return readFat(ctx, r)
	default:
		return nil, errors.New("unsupported image format")
	}
}

func readFat(ctx context.Context, r *io.SectionReader) ([]Image, error) {
	fat, err := macho.NewFatFile(r)
	if err != nil {
		return nil, fmt.Errorf("fat Mach-O: %w", err)
	}
	var images []Image
	for _, arch := range fat.Arches {
		image := machoImage(arch.File)
		slice := io.NewSectionReader(r, int64(arch.Offset), int64(arch.Size))
		enrich(ctx, slice, &image)
		images = append(images, image)
	}
	return images, nil
}

func readELF(r io.ReaderAt) (Image, error) {
	image := Image{Format: "ELF"}
	f, err := elf.NewFile(r)
	if err != nil {
		return image, fmt.Errorf("ELF: %w", err)
	}
	image.Architecture = f.Machine.String()
	libraries, err := f.ImportedLibraries()
	addLibraries(&image, libraries, err)
	for _, read := range []func() ([]elf.Symbol, error){f.Symbols, f.DynamicSymbols} {
		symbols, err := read()
		if err != nil && !errors.Is(err, elf.ErrNoSymbols) {
			image.Issues = append(image.Issues, "ELF symbols: "+err.Error())
		}
		for _, s := range symbols {
			if cAPI(s.Name) {
				kind := "c-defined-symbol"
				if s.Section == elf.SHN_UNDEF {
					kind = "c-undefined-symbol"
				}
				image.Evidence = append(image.Evidence, Evidence{kind, s.Name})
			}
		}
	}
	return image, nil
}

func machoImage(f *macho.File) Image {
	image := Image{Format: "Mach-O", Architecture: f.Cpu.String()}
	libraries, err := f.ImportedLibraries()
	addLibraries(&image, libraries, err)
	if f.Symtab != nil {
		for _, s := range f.Symtab.Syms {
			if cAPI(s.Name) {
				kind := "c-defined-symbol"
				if s.Type&0x0e == 0 {
					kind = "c-undefined-symbol"
				}
				image.Evidence = append(image.Evidence, Evidence{kind, s.Name})
			}
		}
	}
	return image
}

func addLibraries(image *Image, libraries []string, err error) {
	if err != nil {
		image.Issues = append(image.Issues, "dynamic imports: "+err.Error())
	}
	for _, name := range libraries {
		if brotliLibrary(name) {
			image.Evidence = append(image.Evidence, Evidence{"dynamic-import", name})
		}
	}
}

func enrich(ctx context.Context, r *io.SectionReader, image *Image) {
	if info, err := buildinfo.Read(r); err == nil {
		image.Evidence = append(image.Evidence, moduleEvidence(info)...)
	}
	hints, err := stringEvidence(contextReader{ctx: ctx, r: io.NewSectionReader(r, 0, r.Size())})
	image.Evidence = append(image.Evidence, hints...)
	image.RuntimeReviews = bunReviews(image.Evidence)
	if err != nil {
		image.Issues = append(image.Issues, err.Error())
	}
}

type contextReader struct {
	ctx context.Context
	r   io.Reader
}

func (r contextReader) Read(p []byte) (int, error) {
	if err := r.ctx.Err(); err != nil {
		return 0, err
	}
	return r.r.Read(p)
}
