package main

import (
	"fmt"
	"strings"
	"testing"
	"time"
)

// The SHA-256 fingerprints (of the DER) of the two roots the emudhra-2026
// test chains end at.
const (
	emsignECCG3            = "86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b"
	aaaCertificateServices = "d7a7a0fb5d7e2731d771e9484ebcdef71d5f0c3e0a2948782bc83ee0ea699ef4"
)

// distinctRoots is n valid, distinct untrusted roots, each followed by a comma.
func distinctRoots(n int) string {
	var b strings.Builder
	for i := range n {
		fmt.Fprintf(&b, `{"sha256": "%064x", "subject": "root %d"}, `, i+1, i+1)
	}
	return b.String()
}

func TestIncidentManifestValidation(t *testing.T) {
	data, err := buildSource.ReadFile("incidents/emudhra-2026.json")
	if err != nil {
		t.Fatal(err)
	}
	for _, tc := range []struct{ name, old, new string }{
		{"HTTP source", "https://emudhra.we-have-a-problem.com/", "http://emudhra.we-have-a-problem.com/"},
		{"credentials", "https://emudhra.we-have-a-problem.com/", "https://user:password@emudhra.we-have-a-problem.com/"},
		{"unknown mode", "tls-endpoint-and-version", "arbitrary-shell"},
		{"invalid floor", "1.27.3", "1.27.3-rc.1"},
		{"two-part floor", "26.2.2", "26.2"},
		{"invalid date", "2026-11-20", "2026-10-01"},
		{"unknown field", "\"title\":", "\"unrecognized\":true, \"title\":"},
		{"untrusted root with colons", emsignECCG3, "86:A1:EC"},
		{"untrusted root in upper case", emsignECCG3, strings.ToUpper(emsignECCG3)},
		{"untrusted root twice", aaaCertificateServices, emsignECCG3},
		{"untrusted root without subject", emsignECCG3 + "\",\n      \"subject\": \"/C=IN/OU=emSign PKI/O=eMudhra Technologies Limited/CN=emSign ECC Root CA - G3\"", emsignECCG3 + "\""},
		{"empty untrusted root subject", "\"subject\": \"/C=GB/ST=Greater Manchester/L=Salford/O=Comodo CA Limited/CN=AAA Certificate Services\"", "\"subject\": \"\""},
		{"too many untrusted roots", "\"untrustedRoots\": [", "\"untrustedRoots\": [" + distinctRoots(15)},
	} {
		t.Run(tc.name, func(t *testing.T) {
			broken := strings.Replace(string(data), tc.old, tc.new, 1)
			if _, err := ParseIncident([]byte(broken)); err == nil {
				t.Fatal("invalid manifest accepted")
			}
		})
	}
	sixteen := strings.Replace(string(data), "\"untrustedRoots\": [", "\"untrustedRoots\": ["+distinctRoots(14), 1)
	if _, err := ParseIncident([]byte(sixteen)); err != nil {
		t.Fatalf("16 untrusted roots refused: %v", err)
	}
	incident, err := ParseIncident(data)
	if err != nil {
		t.Fatal(err)
	}
	// the roots this incident's test chains end at, which a fixed bundle
	// does not hold
	if got := []string{incident.UntrustedRoots[0].SHA256, incident.UntrustedRoots[1].SHA256}; len(incident.UntrustedRoots) != 2 || got[0] != emsignECCG3 || got[1] != aaaCertificateServices {
		t.Fatalf("untrusted roots = %+v", incident.UntrustedRoots)
	}
	date := time.Date(2026, 11, 21, 0, 0, 0, 0, time.UTC)
	if got := IncidentFreshness(incident, date); got.Level != "WARN" {
		t.Fatal(got)
	}
}

func TestPolicyMissingAndUnsupportedBranchesNeverPass(t *testing.T) {
	incident := Incident{ID: "future", Floors: map[string][]VersionFloor{"tool": {{Branch: "3.1", Minimum: "3.1.9"}}}}
	for _, tc := range []struct{ v, level string }{{"3.1.8", "ERR"}, {"3.1.9", "OK"}, {"3.2.0", "WARN"}, {"4.0.0", "WARN"}} {
		if got := VersionEvidenceFor(incident, "tool", tc.v); got.Level != tc.level {
			t.Fatal(got)
		}
	}
}
