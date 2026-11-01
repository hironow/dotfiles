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
		// Every chain rejected while the control was accepted is reported, not
		// warned about: a rejection cannot prove CA distrust (a hostname
		// mismatch, an expired leaf or a proxy certificate all reject too), so it
		// is never OK, but there is nothing for the operator to do either.
		{"certificate rejection", Accepted, CertRejected, "INFO"},
		{"hostname mismatch", Accepted, CertRejected, "INFO"},
		{"expired leaf", Accepted, CertRejected, "INFO"},
		{"proxy certificate error", Accepted, CertRejected, "INFO"},
		{"DNS", Accepted, Unknown, "WARN"},
		{"control down", Unknown, CertRejected, "WARN"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			targets := make([]Outcome, len(incidents[0].Hosts))
			for i := range targets {
				targets[i] = tc.target
			}
			f := ProbeEvidenceFor(incidents[0], "test", tc.control, targets)
			if f.Level != tc.want {
				t.Fatalf("%+v want %s", f, tc.want)
			}
			if f.Level == "INFO" && !strings.Contains(f.Detail, "CA distrust is not proven") {
				t.Fatalf("a rejection must say its reason is unproven: %+v", f)
			}
		})
	}
	if f := ProbeEvidenceFor(incidents[0], "test", Accepted, nil); f.Level != "WARN" {
		t.Fatal(f)
	}
}

// One accepted chain is enough for ERR, and the summary line has to name it:
// in summary mode the per-chain lines are not printed.
func TestProbeEvidenceNamesTheAcceptedChains(t *testing.T) {
	targets := make([]Outcome, len(incidents[0].Hosts))
	for i := range targets {
		targets[i] = CertRejected
	}
	targets[2] = Accepted
	f := ProbeEvidenceFor(incidents[0], "test", Accepted, targets)
	if f.Level != "ERR" || !strings.Contains(f.Detail, "accepted chains: "+incidents[0].Hosts[2]) || strings.Contains(f.Detail, incidents[0].Hosts[0]) {
		t.Fatal(f)
	}
}

// A partly rejected, partly unknown run is unverified, not a quiet INFO.
func TestProbeEvidenceWithUnknownChainsStaysAWarning(t *testing.T) {
	targets := make([]Outcome, len(incidents[0].Hosts))
	for i := range targets {
		targets[i] = CertRejected
	}
	targets[5] = Unknown
	if f := ProbeEvidenceFor(incidents[0], "test", Accepted, targets); f.Level != "WARN" {
		t.Fatal(f)
	}
}

func TestEveryPublishedChainIsCovered(t *testing.T) {
	impactedHosts := incidents[0].Hosts
	want := []string{"dv-g3b", "dv-g3c", "ov-g3b", "ov-g3c", "ev-g3b", "ev-g3c"}
	if len(impactedHosts) != 14 {
		t.Fatal(impactedHosts)
	}
	for i, prefix := range want {
		if impactedHosts[i] != prefix+"-emudhra.we-have-a-problem.com" || impactedHosts[i+6] != prefix+"-aaa-emudhra.we-have-a-problem.com" {
			t.Fatal(impactedHosts)
		}
	}
}

func TestNoCTChainsAndBunEvidence(t *testing.T) {
	for i, host := range []string{"dv-g3b-noct-emudhra.we-have-a-problem.com", "dv-g3b-aaa-noct-emudhra.we-have-a-problem.com"} {
		if len(incidents[0].Hosts) < 14 || incidents[0].Hosts[12+i] != host {
			t.Fatal("missing No CT host", host)
		}
	}
	findings := allVersionEvidence("bun", "1.4.4")
	if len(findings) != 1 || findings[0].Level != "OK" || findings[0].Name != "ca-version-emudhra-2026-bun" {
		t.Fatal("Bun must have fixed-version evidence, not pending advice", findings)
	}
}

func TestPlatformFindingsGuideEachTrustStore(t *testing.T) {
	for _, tc := range []struct {
		os, kernel string
		wsl        bool
		want       string
	}{
		{"darwin", "", false, "LibreSSL"},
		{"windows", "microsoft", true, "Windows Update"},
		{"linux", "6.8-microsoft-standard-WSL2", false, "each WSL distro"},
		{"linux", "", true, "each WSL distro"},
		{"linux", "6.8", false, "distribution"},
		{"freebsd", "", false, "vendor"},
	} {
		t.Run(tc.os+"/"+tc.kernel, func(t *testing.T) {
			findings := PlatformFindings(tc.os, tc.kernel, tc.wsl)
			// Scope and remediation are the same text on every run: INFO, not WARN.
			if len(findings) != 2 || findings[0].Name != "ca-platform" || findings[0].Level != "INFO" || findings[1].Name != "ca-remediation" || findings[1].Level != "INFO" {
				t.Fatal(findings)
			}
			if !strings.Contains(findings[1].Detail, tc.want) || !strings.Contains(findings[1].Detail, "docs/runbook/ca-doctor.md") {
				t.Fatal(findings[1])
			}
		})
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

// A CA file or directory variable is reported, not warned about: the file
// itself is parsed by ca-file-* / ca-path-*, and the runbook recommends these
// on macOS. Variables that change TLS behavior stay warnings.
func TestEnvironmentLevels(t *testing.T) {
	for _, tc := range []struct{ key, want string }{
		{"SSL_CERT_FILE", "INFO"},
		{"SSL_CERT_DIR", "INFO"},
		{"CURL_CA_BUNDLE", "INFO"},
		{"REQUESTS_CA_BUNDLE", "INFO"},
		{"PIP_CERT", "INFO"},
		{"GIT_SSL_CAINFO", "INFO"},
		{"GIT_SSL_CAPATH", "INFO"},
		{"NODE_EXTRA_CA_CERTS", "INFO"},
		{"HTTPS_PROXY", "WARN"},
		{"https_proxy", "WARN"},
		{"NODE_OPTIONS", "WARN"},
		{"GODEBUG", "WARN"},
		{"PYTHONHTTPSVERIFY", "WARN"},
		{"NODE_TLS_REJECT_UNAUTHORIZED", "WARN"},
		{"GIT_SSL_NO_VERIFY", "ERR"},
	} {
		t.Run(tc.key, func(t *testing.T) {
			f := EnvironmentEvidence(map[string]string{tc.key: "1"})
			if len(f) != 1 || f[0].Level != tc.want {
				t.Fatalf("%+v want %s", f, tc.want)
			}
		})
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
		{"uv", "0.13.5", "OK"},
		{"uv", "0.13.4", "ERR"},
		{"rustup", "1.29.2", "OK"},
		{"rustup", "1.29.1", "ERR"},
		{"certifi", "2026.10.19", "OK"},
		{"certifi", "2026.9.1", "ERR"},
		{"pip", "26.2.2", "OK"},
		{"pip", "26.2.1", "ERR"},
		{"bun", "1.3.0", "WARN"},
		{"bun", "1.4.3", "ERR"},
		{"bun", "1.4.4", "OK"},
		{"bun", "1.5.0", "WARN"},
		{"bun", "1.4.4-canary", "WARN"},
		{"mise", "2026.10.16", "ERR"},
		{"mise", "2026.10.17", "OK"},
		{"mise", "2027.1.1", "WARN"},
		{"node", "garbage", "WARN"},
		{"node", "24.22.1\nWARN forged", "WARN"},
		// The Python metadata probe reports a missing package as "absent".
		{"certifi", "absent", "INFO"},
		{"pip", "absent", "INFO"},
	} {
		t.Run(tc.tool+"/"+tc.version, func(t *testing.T) {
			if got := VersionEvidenceFor(incidents[0], tc.tool, tc.version); got.Level != tc.want {
				t.Fatalf("%+v, want %s", got, tc.want)
			}
		})
	}
}

// Missing and outside-the-reviewed-branches are different facts and say so.
func TestVersionEvidenceNamesWhatItCouldNotCompare(t *testing.T) {
	if f := VersionEvidenceFor(incidents[0], "pip", "absent"); !strings.Contains(f.Detail, "not installed") {
		t.Fatal(f)
	}
	if f := VersionEvidenceFor(incidents[0], "pip", "21.2.4"); f.Level != "WARN" || !strings.Contains(f.Detail, "21.2.4 is outside the reviewed fix branches") {
		t.Fatal(f)
	}
	if f := VersionEvidenceFor(incidents[0], "node", "garbage"); f.Level != "WARN" || !strings.Contains(f.Detail, "unparseable") {
		t.Fatal(f)
	}
}
