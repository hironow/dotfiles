package main

import (
	"bytes"
	"context"
	"encoding/json/v2"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestBunVersionComparisonNeverVerifiesIdentityOrPatchStatus(t *testing.T) {
	for _, tt := range []struct{ version, want string }{
		{"1.4.3", "below-reviewed-release-threshold"},
		{"1.4.4", "at-or-above-reviewed-release-threshold"},
		{"1.4.4+38afee6c8", "at-or-above-reviewed-release-threshold"},
		{"2.0.0", "at-or-above-reviewed-release-threshold"},
		{"1.4.4-canary", "unverified-version"},
		{"1.4.4.1", "unverified-version"},
		{"01.4.4", "unverified-version"},
		{"1.4.4evil", "unverified-version"},
		{"999999999999999999999999.4.4", "unverified-version"},
		{"1.4.4+", "unverified-version"},
		{"1.4.3+backported", "below-reviewed-release-threshold"},
	} {
		t.Run(tt.version, func(t *testing.T) {
			got := reviewBun(tt.version)
			if got.Comparison != tt.want || got.BinaryIdentity != "unverified" || got.PatchStatus != "unverified" {
				t.Fatalf("%+v", got)
			}
		})
	}
}

func TestBunScannerWholeTokensEverySplitAndNUL(t *testing.T) {
	input := []byte("other Bun v1.4.4-canary\x00bun-v1.4.3/x Bun v1.4.4+abc\x00Bun v1.4.4.1 rest")
	for split := 0; split <= len(input); split++ {
		scanner := newBunScanner()
		scanner.feed(input[:split])
		scanner.feed(input[split:])
		scanner.finish(true)
		if got := strings.Join(scanner.versions, ","); got != "1.4.4-canary,1.4.3,1.4.4+abc,1.4.4.1" {
			t.Fatalf("split=%d: %q", split, got)
		}
	}
	scanner := newBunScanner()
	scanner.feed([]byte("Bun v" + strings.Repeat("9", 1024)))
	scanner.finish(true)
	if len(scanner.versions) != 1 || reviewBun(scanner.versions[0]).Comparison != "unverified-version" {
		t.Fatal("overlong token accepted")
	}
	scanner = newBunScanner()
	scanner.feed([]byte("Bun v1.4.4"))
	scanner.finish(false)
	if reviewBun(scanner.versions[0]).Comparison != "unverified-version" {
		t.Fatal("interrupted token accepted")
	}
}

func TestBunCandidateCapIsIncompleteAndMixedCandidatesArePreserved(t *testing.T) {
	input := "Bun v1.4.3\x00Bun v1.4.4\x00Bun v1.4.4-canary\x00"
	evidence, err := stringEvidence(strings.NewReader(input))
	if err != nil {
		t.Fatal(err)
	}
	image := Image{Evidence: evidence, RuntimeReviews: bunReviews(evidence)}
	if len(image.RuntimeReviews) != 3 || evidenceState(evidence) != "HINT" {
		t.Fatalf("%+v", image)
	}
	report := Report{Notice: disclaimer, Findings: []Finding{{Path: "unknown-name", Images: []Image{image}}}}
	for _, asJSON := range []bool{false, true} {
		var out bytes.Buffer
		if err := outputReport(&out, report, asJSON); err != nil {
			t.Fatal(err)
		}
		for _, want := range []string{"1.4.3", "1.4.4-canary", "below-reviewed-release-threshold", "at-or-above-reviewed-release-threshold", "unverified"} {
			if !strings.Contains(out.String(), want) {
				t.Fatalf("lost %q: %s", want, &out)
			}
		}
		if asJSON {
			var decoded Report
			if err := json.Unmarshal(out.Bytes(), &decoded); err != nil {
				t.Fatal(err)
			}
			if decoded.Incomplete {
				t.Fatal("mixed candidates confused with operational failure")
			}
		}
	}
	var many strings.Builder
	for i := 0; i < 17; i++ {
		many.WriteString("Bun v1.4." + strings.Repeat("1", i+1) + "\x00")
	}
	_, err = stringEvidence(strings.NewReader(many.String()))
	if err == nil {
		t.Fatal("candidate cap silently truncated")
	}
	path := filepath.Join(t.TempDir(), "image")
	if err := os.WriteFile(path, append(elfFixture(t, true, false), []byte(many.String())...), 0o700); err != nil {
		t.Fatal(err)
	}
	if !scan(context.Background(), Inventory{Paths: []string{path}}, 512<<20).Incomplete {
		t.Fatal("cap not propagated")
	}
}

func TestBunScannerIgnoresWordsThatAreNotVersionCandidates(t *testing.T) {
	scanner := newBunScanner()
	scanner.feed([]byte("Bun version bun-vfs Bun v%prefix Bun v1.4.4\x00"))
	scanner.finish(true)
	if len(scanner.versions) != 1 || scanner.versions[0] != "1.4.4" {
		t.Fatalf("not version candidates: %v", scanner.versions)
	}
}

func TestBunScannerReadFailureDoesNotAcceptPrefix(t *testing.T) {
	evidence, err := stringEvidence(io.MultiReader(strings.NewReader("Bun v1.4.4"), brokenReader{}))
	if err == nil {
		t.Fatal("expected read failure")
	}
	for _, review := range bunReviews(evidence) {
		if review.Comparison != "unverified-version" {
			t.Fatalf("%+v", review)
		}
	}
}
