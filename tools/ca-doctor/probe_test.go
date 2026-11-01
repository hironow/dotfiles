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
	"slices"
	"strings"
	"sync"
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

// recordedCommands keeps the arguments of the last command instead of running it.
type recordedCommands struct{ args []string }

func (c *recordedCommands) Run(_ context.Context, _ string, args ...string) CommandResult {
	c.args = args
	return CommandResult{Code: 1}
}

// The default probe of each external client keeps the arguments it has always
// used, so a new way to connect cannot change the default one by accident.
func TestExternalProbeDefaultArguments(t *testing.T) {
	const url = "https://h.example/"
	cases := []struct {
		kind string
		want []string
	}{
		{"curl", []string{"-q", "--proto", "=https", "--connect-timeout", "3", "--max-time", "4", "--silent", "--show-error", "--output", os.DevNull, "--write-out", "%{http_code}", url}},
		{"node", []string{"--eval", nodeProbe, url}},
		{"python", []string{"-c", pythonProbe, url}},
		{"bun", []string{"--eval", bunProbe, url}},
	}
	for _, c := range cases {
		t.Run(c.kind, func(t *testing.T) {
			commands := &recordedCommands{}
			ExternalProbe{Path: "client", Kind: c.kind, Commands: commands}.Probe(context.Background(), url)
			if !slices.Equal(commands.args, c.want) {
				t.Fatalf("args %q, want %q", commands.args, c.want)
			}
		})
	}
}

// scriptedProber answers each URL from a queue and counts the calls. The last
// answer repeats once the queue is empty.
type scriptedProber struct {
	mu      sync.Mutex
	answers map[string][]Outcome
	calls   map[string]int
}

func (p *scriptedProber) Probe(_ context.Context, url string) Outcome {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.calls[url]++
	queue := p.answers[url]
	answer := queue[0]
	if len(queue) > 1 {
		p.answers[url] = queue[1:]
	}
	return answer
}

func probeIncident() Incident {
	return Incident{ID: "test-2026", ControlURL: "https://control.example/", Hosts: []string{"a.example", "b.example"}}
}

// The control asks only whether this client can make a TLS connection at all.
// One reset (seen on Windows, cause not established) does not answer that.
func TestProbeClientRepeatsAnUnknownControl(t *testing.T) {
	cases := []struct {
		name      string
		control   []Outcome
		wantLevel string
		wantCalls int
	}{
		{"reset then accepted", []Outcome{Unknown, Accepted}, "INFO", 2},
		{"unknown three times", []Outcome{Unknown}, "WARN", 3},
		{"accepted at once", []Outcome{Accepted}, "INFO", 1},
		{"rejected is an answer", []Outcome{CertRejected}, "WARN", 1},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			incident := probeIncident()
			p := &scriptedProber{
				answers: map[string][]Outcome{
					incident.ControlURL:  c.control,
					"https://a.example/": {CertRejected},
					"https://b.example/": {CertRejected},
				},
				calls: map[string]int{},
			}
			got := ProbeClient(context.Background(), incident, "fake", p, make(chan struct{}, 1))
			if got[0].Level != c.wantLevel {
				t.Fatalf("level %s, want %s: %v", got[0].Level, c.wantLevel, got[0])
			}
			if p.calls[incident.ControlURL] != c.wantCalls {
				t.Fatalf("control probed %d times, want %d", p.calls[incident.ControlURL], c.wantCalls)
			}
		})
	}
}

// A test chain is never repeated: an unreachable host would multiply the
// timeout, and a repeated answer is not new evidence.
func TestProbeClientDoesNotRepeatTestChains(t *testing.T) {
	incident := probeIncident()
	p := &scriptedProber{
		answers: map[string][]Outcome{
			incident.ControlURL:  {Accepted},
			"https://a.example/": {Unknown},
			"https://b.example/": {CertRejected},
		},
		calls: map[string]int{},
	}
	got := ProbeClient(context.Background(), incident, "fake", p, make(chan struct{}, 1))
	if p.calls["https://a.example/"] != 1 {
		t.Fatalf("test chain probed %d times, want 1", p.calls["https://a.example/"])
	}
	if got[0].Level != "WARN" {
		t.Fatalf("an unknown chain must stay WARN: %v", got[0])
	}
}

func TestProbeClientStopsRepeatingWhenCancelled(t *testing.T) {
	incident := probeIncident()
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	p := &scriptedProber{
		answers: map[string][]Outcome{incident.ControlURL: {Unknown}, "https://a.example/": {Unknown}, "https://b.example/": {Unknown}},
		calls:   map[string]int{},
	}
	got := ProbeClient(ctx, incident, "fake", p, make(chan struct{}))
	if got[0].Level != "WARN" || p.calls[incident.ControlURL] != 0 {
		t.Fatalf("cancelled run: level %s, control calls %d", got[0].Level, p.calls[incident.ControlURL])
	}
}
