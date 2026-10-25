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
