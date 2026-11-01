package main

import (
	"context"
	"crypto/x509"
	"encoding/pem"
	"net"
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

// The IPv4 probe still reaches an IPv4 server and never dials IPv6, which is
// the path that reset about half the control connections on a Windows host.
func TestGoProbeIPv4DialsOnlyIPv4(t *testing.T) {
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(500) })
	server := httptest.NewTLSServer(handler)
	defer server.Close()
	if got := (GoProbe{IPv4: true}).Probe(context.Background(), server.URL); got != CertRejected {
		t.Fatalf("IPv4 server = %s", got)
	}
	listener, err := net.Listen("tcp6", "[::1]:0")
	if err != nil {
		t.Skip("no IPv6 loopback")
	}
	ipv6 := httptest.NewUnstartedServer(handler)
	_ = ipv6.Listener.Close()
	ipv6.Listener = listener
	ipv6.StartTLS()
	defer ipv6.Close()
	if got := (GoProbe{}).Probe(context.Background(), ipv6.URL); got != CertRejected {
		t.Fatalf("default probe to an IPv6 server = %s", got)
	}
	if got := (GoProbe{IPv4: true}).Probe(context.Background(), ipv6.URL); got != Unknown {
		t.Fatalf("IPv4 probe to an IPv6 server = %s", got)
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
			probe.IPv4 = true
			if tc.kind == "bun" {
				if got := probe.Probe(context.Background(), server.URL); got != Unknown {
					t.Fatalf("bun cannot limit fetch to IPv4, got %s", got)
				}
				return
			}
			if got := probe.Probe(context.Background(), server.URL); got != Accepted {
				t.Fatalf("IPv4 probe to an IPv4 server must be accepted, got %s", got)
			}
			if got := probe.Probe(context.Background(), "https://127.0.0.1:1/"); got != Unknown {
				t.Fatalf("IPv4 network failure = %s", got)
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

// The IPv4 probe adds one switch to the default arguments. Bun's fetch has no
// address-family option, so an IPv4 bun probe runs nothing and stays unknown.
func TestExternalProbeIPv4Arguments(t *testing.T) {
	const url = "https://h.example/"
	cases := []struct {
		kind string
		want []string
	}{
		{"curl", []string{"-q", "--proto", "=https", "--connect-timeout", "3", "--max-time", "4", "--silent", "--show-error", "--output", os.DevNull, "--write-out", "%{http_code}", "--ipv4", url}},
		{"node", []string{"--eval", nodeProbe, url, "4"}},
		{"python", []string{"-c", pythonProbe, url, "4"}},
		{"bun", nil},
	}
	for _, c := range cases {
		t.Run(c.kind, func(t *testing.T) {
			commands := &recordedCommands{}
			got := ExternalProbe{Path: "client", Kind: c.kind, Commands: commands, IPv4: true}.Probe(context.Background(), url)
			if !slices.Equal(commands.args, c.want) {
				t.Fatalf("args %q, want %q", commands.args, c.want)
			}
			if c.want == nil && got != Unknown {
				t.Fatalf("outcome %s, want unknown", got)
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

// newScriptedProber answers the control from control and every test chain from
// chains.
func newScriptedProber(incident Incident, control []Outcome, chains Outcome) *scriptedProber {
	answers := map[string][]Outcome{incident.ControlURL: control}
	for _, host := range incident.Hosts {
		answers["https://"+host+"/"] = []Outcome{chains}
	}
	return &scriptedProber{answers: answers, calls: map[string]int{}}
}

// The control asks only whether this client can make a TLS connection at all.
// One reset does not answer that. The second try is over IPv4, the family the
// test hosts use (on a Windows host the control's IPv6 path reset about half
// the connections); the third goes back to the default so an IPv6-only network
// keeps its second chance. Every test chain is rejected in these cases.
func TestProbeClientRepeatsAnUnknownControl(t *testing.T) {
	cases := []struct {
		name                     string
		control, ipv4Control     []Outcome
		noIPv4                   bool
		wantLevel                string
		wantDefault, wantIPv4Hit int
	}{
		{"reset then accepted over IPv4", []Outcome{Unknown}, []Outcome{Accepted}, false, "INFO", 1, 1},
		{"IPv4 unknown, default recovers", []Outcome{Unknown, Accepted}, []Outcome{Unknown}, false, "INFO", 2, 1},
		{"unknown on every try", []Outcome{Unknown}, []Outcome{Unknown}, false, "WARN", 2, 1},
		{"accepted at once", []Outcome{Accepted}, []Outcome{Unknown}, false, "INFO", 1, 0},
		{"rejected is an answer", []Outcome{CertRejected}, []Outcome{Accepted}, false, "WARN", 1, 0},
		{"no IPv4 probe: default three times", []Outcome{Unknown}, nil, true, "WARN", 3, 0},
		{"no IPv4 probe: default recovers", []Outcome{Unknown, Accepted}, nil, true, "INFO", 2, 0},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			incident := probeIncident()
			p := newScriptedProber(incident, c.control, CertRejected)
			ipv4 := newScriptedProber(incident, c.ipv4Control, Accepted)
			var ipv4Prober TLSProber = ipv4
			if c.noIPv4 {
				ipv4Prober = nil
			}
			got := ProbeClient(context.Background(), incident, "fake", p, ipv4Prober, make(chan struct{}, 1))
			if got[0].Level != c.wantLevel {
				t.Fatalf("level %s, want %s: %v", got[0].Level, c.wantLevel, got[0])
			}
			if p.calls[incident.ControlURL] != c.wantDefault || ipv4.calls[incident.ControlURL] != c.wantIPv4Hit {
				t.Fatalf("control probed %d times by default and %d over IPv4, want %d and %d", p.calls[incident.ControlURL], ipv4.calls[incident.ControlURL], c.wantDefault, c.wantIPv4Hit)
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
	ipv4 := newScriptedProber(incident, []Outcome{Accepted}, Accepted)
	got := ProbeClient(context.Background(), incident, "fake", p, ipv4, make(chan struct{}, 1))
	if p.calls["https://a.example/"] != 1 {
		t.Fatalf("test chain probed %d times, want 1", p.calls["https://a.example/"])
	}
	if ipv4.calls["https://a.example/"] != 0 || ipv4.calls["https://b.example/"] != 0 {
		t.Fatalf("test chains must use the default probe only: %v", ipv4.calls)
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
	ipv4 := newScriptedProber(incident, []Outcome{Unknown}, Unknown)
	got := ProbeClient(ctx, incident, "fake", p, ipv4, make(chan struct{}))
	if got[0].Level != "WARN" || p.calls[incident.ControlURL] != 0 || ipv4.calls[incident.ControlURL] != 0 {
		t.Fatalf("cancelled run: level %s, control calls %d default and %d IPv4", got[0].Level, p.calls[incident.ControlURL], ipv4.calls[incident.ControlURL])
	}
}
