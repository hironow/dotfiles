package main

import (
	"bytes"
	"io"
	"strings"
	"testing"
)

func TestEvidenceDoesNotClearUnknownOrMixedImplementations(t *testing.T) {
	cases := []struct {
		name     string
		evidence []Evidence
		want     string
	}{
		{"nothing", nil, "UNKNOWN"},
		{"strings only", []Evidence{{"c-api-string", "BrotliDecoderCreateInstance"}}, "HINT"},
		{"pure is not clearance", []Evidence{{"go-module", "github.com/andybalholm/brotli@v1"}}, "EVIDENCE"},
		{"mixed", []Evidence{{"go-module", "github.com/andybalholm/brotli@v1"}, {"dynamic-import", "libbrotlidec.so"}}, "EVIDENCE"},
	}
	for _, tt := range cases {
		t.Run(tt.name, func(t *testing.T) {
			if got := evidenceState(tt.evidence); got != tt.want {
				t.Fatalf("got %s want %s", got, tt.want)
			}
		})
	}
}

func TestStringEvidenceAcrossChunksAndReadFailure(t *testing.T) {
	input := strings.Repeat("x", 32760) + "BrotliDecoderCreateInstance\x00brotli_decompressor::decode"
	got, err := stringEvidence(strings.NewReader(input))
	if err != nil || len(got) != 2 {
		t.Fatalf("evidence=%v err=%v", got, err)
	}
	_, err = stringEvidence(io.MultiReader(bytes.NewBufferString("BrotliEncoderCreateInstance"), brokenReader{}))
	if err == nil {
		t.Fatal("read failure silently accepted")
	}
}

type brokenReader struct{}

func (brokenReader) Read([]byte) (int, error) { return 0, io.ErrUnexpectedEOF }
