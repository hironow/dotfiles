package main

import (
	"bytes"
	"errors"
	"fmt"
	"io"
	"strings"
)

// Evidence records observations, not vulnerability or absence verdicts.
type Evidence struct {
	Kind   string `json:"kind"`
	Detail string `json:"detail"`
}

type Image struct {
	Format         string          `json:"format"`
	Architecture   string          `json:"architecture"`
	Evidence       []Evidence      `json:"evidence"`
	Issues         []string        `json:"issues"`
	RuntimeReviews []RuntimeReview `json:"runtime_reviews"`
}

type Finding struct {
	Path   string   `json:"path"`
	Images []Image  `json:"images"`
	Issues []string `json:"issues"`
}

func evidenceState(evidence []Evidence) string {
	state := "UNKNOWN"
	for _, e := range evidence {
		switch e.Kind {
		case "go-build":
			continue
		case "c-api-string", "rust-path-string", "bun-version-string":
			state = "HINT"
		default:
			return "EVIDENCE"
		}
	}
	return state
}

func brotliLibrary(name string) bool { return strings.Contains(strings.ToLower(name), "brotli") }
func cAPI(name string) bool {
	name = strings.TrimPrefix(name, "_")
	return strings.HasPrefix(name, "BrotliDecoder") || strings.HasPrefix(name, "BrotliEncoder") || strings.HasPrefix(name, "BrotliGet")
}

func stringEvidence(r io.Reader) ([]Evidence, error) {
	patterns := []Evidence{
		{"c-api-string", "BrotliDecoderCreateInstance"},
		{"c-api-string", "BrotliEncoderCreateInstance"},
		{"c-api-string", "BrotliDecoderDecompress"},
		{"c-api-string", "BrotliEncoderCompress"},
		{"rust-path-string", "brotli_decompressor::"},
		{"rust-path-string", "brotli::"},
		{"rust-path-string", "brotli_sys::"},
	}
	seen := map[string]bool{}
	var found []Evidence
	chunk := make([]byte, 32768)
	var overlap []byte
	versions := newBunScanner()
	for {
		n, err := r.Read(chunk)
		versions.feed(chunk[:n])
		overlap = append(overlap, chunk[:n]...)
		data := overlap
		for _, p := range patterns {
			if !seen[p.Detail] && bytes.Contains(data, []byte(p.Detail)) {
				seen[p.Detail] = true
				found = append(found, p)
			}
		}
		if err != nil || versions.err != nil {
			versions.finish(errors.Is(err, io.EOF))
			found = append(found, versions.evidence()...)
			if errors.Is(err, io.EOF) {
				return found, versions.err
			}
			if err != nil {
				err = fmt.Errorf("string scan: %w", err)
			}
			return found, errors.Join(err, versions.err)
		}
		keep := min(len(data), 64)
		overlap = append([]byte(nil), data[len(data)-keep:]...)
	}
}
