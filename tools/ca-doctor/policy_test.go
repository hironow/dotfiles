package main

import (
	"strings"
	"testing"
)

func TestProbeEvidenceNeverConfusesFailureWithRemediation(t *testing.T) {
	for _, tc := range []struct {
		name    string
		control Outcome
		target  Outcome
		want    string
	}{
		{"accepted", Accepted, Accepted, "ERR"},
		{"accepted without control", Unknown, Accepted, "ERR"},
		{"certificate rejection", Accepted, CertRejected, "WARN"},
		{"hostname mismatch", Accepted, CertRejected, "WARN"},
		{"expired leaf", Accepted, CertRejected, "WARN"},
		{"proxy certificate error", Accepted, CertRejected, "WARN"},
		{"DNS", Accepted, Unknown, "WARN"},
		{"control down", Unknown, CertRejected, "WARN"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			targets := make([]Outcome, 12)
			for i := range targets {
				targets[i] = tc.target
			}
			f := ProbeEvidenceFor(incidents[0], "test", tc.control, targets)
			if f.Level != tc.want {
				t.Fatalf("%+v want %s", f, tc.want)
			}
		})
	}
	if f := ProbeEvidenceFor(incidents[0], "test", Accepted, nil); f.Level != "WARN" {
		t.Fatal(f)
	}
}

func TestEveryPublishedChainIsCovered(t *testing.T) {
	impactedHosts := incidents[0].Hosts
	want := []string{"dv-g3b", "dv-g3c", "ov-g3b", "ov-g3c", "ev-g3b", "ev-g3c"}
	if len(impactedHosts) != 12 {
		t.Fatal(impactedHosts)
	}
	for i, prefix := range want {
		if impactedHosts[i] != prefix+"-emudhra.we-have-a-problem.com" || impactedHosts[i+6] != prefix+"-aaa-emudhra.we-have-a-problem.com" {
			t.Fatal(impactedHosts)
		}
	}
}

func TestEnvironmentScopes(t *testing.T) {
	if !strings.Contains(PlatformScope("linux", "6.8-microsoft-standard-WSL2", false), "Windows host not assessed") {
		t.Fatal("WSL must not certify Windows")
	}
	if !strings.Contains(PlatformScope("windows", "", false), "WSL distros not assessed") {
		t.Fatal("Windows must not certify WSL")
	}
	for _, key := range []string{"NODE_TLS_REJECT_UNAUTHORIZED", "GIT_SSL_NO_VERIFY"} {
		findings := EnvironmentEvidence(map[string]string{key: "0", "HTTPS_PROXY": "https://private-user:secret@example.invalid"})
		for _, f := range findings {
			if strings.Contains(f.String(), "secret") || strings.Contains(f.String(), "private-user") {
				t.Fatal(f)
			}
		}
	}
	f := EnvironmentEvidence(map[string]string{"NODE_TLS_REJECT_UNAUTHORIZED": "0"})
	if len(f) != 1 || f[0].Level != "ERR" {
		t.Fatal(f)
	}
}

func TestVersionEvidence(t *testing.T) {
	for _, tc := range []struct{ tool, version, want string }{
		{"go", "1.27.3", "OK"},
		{"go", "1.27.2", "ERR"},
		{"go", "1.26.10", "OK"},
		{"go", "1.26.9", "ERR"},
		{"go", "1.28.0", "WARN"},
		{"go", "1.25.9", "WARN"},
		{"node", "24.22.1", "OK"},
		{"node", "24.22.0", "ERR"},
		{"node", "22.23.4", "OK"},
		{"node", "26.12.1", "OK"},
		{"node", "26.12.1-rc.1", "WARN"},
		{"node", "28.0.0", "WARN"},
		{"uv", "0.13.4", "OK"},
		{"uv", "0.13.3", "ERR"},
		{"rustup", "1.29.2", "OK"},
		{"rustup", "1.29.1", "ERR"},
		{"certifi", "2026.10.19", "OK"},
		{"certifi", "2026.9.1", "ERR"},
		{"pip", "26.2.2", "OK"},
		{"pip", "26.2.1", "ERR"},
		{"bun", "1.3.0", "WARN"},
		{"node", "garbage", "WARN"},
		{"node", "24.22.1\nWARN forged", "WARN"},
	} {
		t.Run(tc.tool+"/"+tc.version, func(t *testing.T) {
			if got := VersionEvidenceFor(incidents[0], tc.tool, tc.version); got.Level != tc.want {
				t.Fatalf("%+v, want %s", got, tc.want)
			}
		})
	}
}
