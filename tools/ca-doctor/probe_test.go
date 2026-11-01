package main

import (
	"context"
	"crypto/x509"
	"encoding/pem"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func TestTLSProbeDoesNotConfuseHTTPFailureAndCertificateFailure(t *testing.T) {
	server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(500) }))
	defer server.Close()
	if got := (GoProbe{}).Probe(context.Background(), server.URL); got != CertRejected {
		t.Fatal(got)
	}
	if got := (GoProbe{Client: server.Client()}).Probe(context.Background(), server.URL); got != Accepted {
		t.Fatal(got)
	}
	if got := (GoProbe{}).Probe(context.Background(), "https://127.0.0.1:1/"); got != Unknown {
		t.Fatal(got)
	}
}

func TestExternalProbeAdaptersAgainstLocalTLS(t *testing.T) {
	server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(500) }))
	defer server.Close()
	cert := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: server.TLS.Certificates[0].Certificate[0]})
	if _, err := x509.ParseCertificate(server.TLS.Certificates[0].Certificate[0]); err != nil {
		t.Fatal(err)
	}
	bundle := filepath.Join(t.TempDir(), "test ca.pem")
	if err := os.WriteFile(bundle, cert, 0o600); err != nil {
		t.Fatal(err)
	}
	for _, tc := range []struct{ command, kind, env string }{
		{"curl", "curl", "CURL_CA_BUNDLE"},
		{"node", "node", "NODE_EXTRA_CA_CERTS"},
		{"python3", "python", "SSL_CERT_FILE"},
		{"bun", "bun", "NODE_EXTRA_CA_CERTS"},
	} {
		t.Run(tc.command, func(t *testing.T) {
			command, err := exec.LookPath(tc.command)
			if err != nil {
				t.Skip("not installed")
			}
			if tc.kind == "curl" && schannelOnlyCurl(command) {
				t.Skip("this curl uses Windows' Schannel, which ignores CURL_CA_BUNDLE")
			}
			t.Setenv("HTTPS_PROXY", "")
			t.Setenv("https_proxy", "")
			t.Setenv("ALL_PROXY", "")
			t.Setenv("all_proxy", "")
			t.Setenv("NODE_TLS_REJECT_UNAUTHORIZED", "1")
			probe := ExternalProbe{Path: command, Kind: tc.kind, Commands: OSCommands{}}
			t.Setenv(tc.env, bundle)
			if got := probe.Probe(context.Background(), server.URL); got != Accepted {
				t.Fatalf("trusted TLS plus HTTP 500 must be accepted, got %s", got)
			}
			if got := probe.Probe(context.Background(), "https://127.0.0.1:1/"); got != Unknown {
				t.Fatalf("network failure = %s", got)
			}
		})
	}
}

// schannelOnlyCurl reports a curl whose only TLS backend is Schannel, which
// trusts the Windows certificate store and ignores CURL_CA_BUNDLE.
func schannelOnlyCurl(path string) bool {
	out, err := exec.Command(path, "--version").Output()
	if err != nil {
		return false
	}
	first, _, _ := strings.Cut(string(out), "\n")
	return strings.Contains(first, "Schannel") && !strings.Contains(first, "OpenSSL")
}

// Schannel (curl on Windows) maps only SEC_E_UNTRUSTED_ROOT and
// SEC_E_WRONG_PRINCIPAL to exit 60; every other handshake failure, including a
// revoked certificate, is exit 35 with the SSPI name on stderr.
func TestCurlOutcomeReadsSchannelCertificateRejections(t *testing.T) {
	const prefix = "curl: (35) schannel: next InitializeSecurityContext failed: "
	cases := []struct {
		name   string
		result CommandResult
		want   Outcome
	}{
		{"revoked", CommandResult{Code: 35, Stderr: prefix + "CRYPT_E_REVOKED (0x80092010) - The certificate is revoked.\n"}, CertRejected},
		{"expired", CommandResult{Code: 35, Stderr: prefix + "SEC_E_CERT_EXPIRED (0x80090328) - The received certificate has expired.\n"}, CertRejected},
		{"wrong usage", CommandResult{Code: 35, Stderr: prefix + "SEC_E_CERT_WRONG_USAGE (0x80090349) - The certificate is not valid for the requested usage.\n"}, CertRejected},
		{"revocation server offline", CommandResult{Code: 35, Stderr: prefix + "CRYPT_E_REVOCATION_OFFLINE (0x80092013) - The revocation function was unable to check revocation because the revocation server was offline.\n"}, Unknown},
		{"no revocation check", CommandResult{Code: 35, Stderr: prefix + "CRYPT_E_NO_REVOCATION_CHECK (0x80092012)\n"}, Unknown},
		{"unspecific certificate error", CommandResult{Code: 35, Stderr: prefix + "SEC_E_CERT_UNKNOWN (0x80090327)\n"}, Unknown},
		{"connection reset", CommandResult{Code: 35, Stderr: "curl: (35) Recv failure: Connection was reset\n"}, Unknown},
		{"name without schannel", CommandResult{Code: 35, Stderr: "curl: (35) OpenSSL SSL_connect: CRYPT_E_REVOKED (0x80092010)\n"}, Unknown},
		{"name without code", CommandResult{Code: 35, Stderr: prefix + "CRYPT_E_REVOKED\n"}, Unknown},
		{"truncated", CommandResult{Code: 35, Stderr: prefix + "CRYPT_E_REVOKED (0x80092010)\n", Truncated: true}, Unknown},
		{"other exit with the name", CommandResult{Code: 28, Stderr: prefix + "CRYPT_E_REVOKED (0x80092010)\n"}, Unknown},
		{"untrusted root stays exit 60", CommandResult{Code: 60, Stderr: "curl: (60) schannel: SEC_E_UNTRUSTED_ROOT (0x80090325)\n"}, CertRejected},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := CurlOutcome(c.result); got != c.want {
				t.Fatalf("got %s, want %s", got, c.want)
			}
		})
	}
}
