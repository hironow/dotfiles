package main

import (
	"context"
	"crypto/tls"
	"encoding/json/v2"
	"errors"
	"net"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"
)

type TLSProber interface {
	Probe(context.Context, string) Outcome
}

type GoProbe struct {
	Client *http.Client
	// IPv4 limits the default client to IPv4 addresses. An injected Client is
	// used as it is.
	IPv4 bool
}

func (p GoProbe) Probe(ctx context.Context, url string) Outcome {
	client := p.Client
	if client == nil {
		transport := &http.Transport{TLSHandshakeTimeout: 3 * time.Second}
		if p.IPv4 {
			transport.DialContext = func(ctx context.Context, _, address string) (net.Conn, error) {
				var dialer net.Dialer
				return dialer.DialContext(ctx, "tcp4", address)
			}
		}
		defer transport.CloseIdleConnections()
		client = &http.Client{Transport: transport, Timeout: 4 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodHead, url, http.NoBody)
	if err != nil {
		return Unknown
	}
	response, err := client.Do(req)
	if err == nil {
		_ = response.Body.Close()
		return Accepted
	}
	var verification *tls.CertificateVerificationError
	if errors.As(err, &verification) {
		return CertRejected
	}
	return Unknown
}

type ExternalProbe struct {
	Path, Kind string
	Commands   Commands
	// IPv4 limits the connection to IPv4 addresses. Bun's fetch has no
	// address-family option, so an IPv4 bun probe runs nothing and is unknown.
	IPv4 bool
}

const nodeProbe = `const tls=require('node:tls');
const u=new URL(process.argv[1]);
let done=false; let s;
function finish(x){if(done)return;done=true;console.log(x);if(s)s.destroy();}
s=tls.connect({host:u.hostname,port:Number(u.port||443),servername:u.hostname,...(process.argv[2]==='4'?{family:4}:{})},()=>finish('accepted'));
s.setTimeout(3000,()=>finish('unknown'));
s.on('error',e=>finish(['UNABLE_TO_GET_ISSUER_CERT_LOCALLY','UNABLE_TO_VERIFY_LEAF_SIGNATURE','CERT_HAS_EXPIRED','CERT_REVOKED','ERR_TLS_CERT_ALTNAME_INVALID','DEPTH_ZERO_SELF_SIGNED_CERT','SELF_SIGNED_CERT_IN_CHAIN','CERT_SIGNATURE_FAILURE'].includes(e.code)?'certificate-rejected':'unknown'));
`

const pythonProbe = `import socket, ssl, sys, urllib.parse
u=urllib.parse.urlsplit(sys.argv[1])
try:
    if sys.argv[2:]==['4']:
        raw=socket.socket(socket.AF_INET)
        raw.settimeout(3)
        raw.connect((u.hostname,u.port or 443))
    else:
        raw=socket.create_connection((u.hostname,u.port or 443),timeout=3)
    with raw, ssl.create_default_context().wrap_socket(raw,server_hostname=u.hostname):
        print('accepted')
except ssl.SSLCertVerificationError:
    print('certificate-rejected')
except Exception:
    print('unknown')
`

const bunProbe = `try {
 const r=await fetch(process.argv[1],{method:'HEAD',redirect:'manual',signal:AbortSignal.timeout(3000)});
 console.log(r.status>0?'accepted':'unknown');
} catch(e) {
 console.log(['UNABLE_TO_GET_ISSUER_CERT_LOCALLY','UNABLE_TO_VERIFY_LEAF_SIGNATURE','CERT_HAS_EXPIRED','CERT_REVOKED','ERR_TLS_CERT_ALTNAME_INVALID','DEPTH_ZERO_SELF_SIGNED_CERT','SELF_SIGNED_CERT_IN_CHAIN'].includes(e.code)?'certificate-rejected':'unknown');
}
`

func (p ExternalProbe) Probe(ctx context.Context, url string) Outcome {
	var args, ipv4Arg []string
	if p.IPv4 {
		// The node and python probe scripts read a trailing "4" as IPv4 only.
		ipv4Arg = []string{"4"}
	}
	switch p.Kind {
	case "curl":
		args = []string{"-q", "--proto", "=https", "--connect-timeout", "3", "--max-time", "4", "--silent", "--show-error", "--output", os.DevNull, "--write-out", "%{http_code}"}
		if p.IPv4 {
			args = append(args, "--ipv4")
		}
		args = append(args, url)
	case "node":
		args = append([]string{"--eval", nodeProbe, url}, ipv4Arg...)
	case "python":
		args = append([]string{"-c", pythonProbe, url}, ipv4Arg...)
	case "bun":
		if p.IPv4 {
			return Unknown
		}
		args = []string{"--eval", bunProbe, url}
	default:
		return Unknown
	}
	result := p.Commands.Run(ctx, p.Path, args...)
	if result.Truncated {
		return Unknown
	}
	if p.Kind == "curl" {
		return CurlOutcome(result)
	}
	if result.Code != 0 {
		return Unknown
	}
	switch strings.TrimSpace(result.Stdout) {
	case string(Accepted):
		return Accepted
	case string(CertRejected):
		return CertRejected
	default:
		return Unknown
	}
}

// schannelRejections are the SSPI names that mean Windows judged the
// certificate itself. curl's Schannel backend reports them as exit 35, not 60
// (only SEC_E_UNTRUSTED_ROOT and SEC_E_WRONG_PRINCIPAL become 60). Names that
// mean the revocation status could not be checked are left out on purpose.
var schannelRejections = []string{"CRYPT_E_REVOKED", "SEC_E_CERT_EXPIRED", "SEC_E_CERT_WRONG_USAGE"}

func schannelRejected(stderr string) bool {
	if !strings.Contains(stderr, "schannel:") {
		return false
	}
	for _, name := range schannelRejections {
		if strings.Contains(stderr, name+" (0x") {
			return true
		}
	}
	return false
}

func CurlOutcome(result CommandResult) Outcome {
	if result.Truncated {
		return Unknown
	}
	if result.Code == 60 || (result.Code == 35 && schannelRejected(result.Stderr)) {
		return CertRejected
	}
	status := strings.TrimSpace(result.Stdout)
	if result.Code == 0 && len(status) == 3 && status[0] >= '1' && status[0] <= '5' && status[1] >= '0' && status[1] <= '9' && status[2] >= '0' && status[2] <= '9' {
		return Accepted
	}
	return Unknown
}

// controlProbers is the order in which an unknown control is tried. The control
// only asks whether this client can make a TLS connection at all, and one
// unknown does not answer that. The second try is over IPv4: the test hosts
// publish only A records, and on a Windows host about half the IPv6
// connections to the control (GitHub Pages) were reset. The third try goes back
// to the default so an IPv6-only network keeps a second chance. A client with
// no IPv4 probe tries its default three times. Three unknowns stay unknown.
// Test chains are tried once, with the default probe.
func controlProbers(p, ipv4 TLSProber) []TLSProber {
	if ipv4 == nil {
		return []TLSProber{p, p, p}
	}
	return []TLSProber{p, ipv4, p}
}

// ProbeClient runs a fixed list, with a global concurrency cap shared by all
// clients. Result order is stable irrespective of completion order. ipv4 is
// nil for a client that cannot limit its own way to connect to IPv4.
func ProbeClient(ctx context.Context, incident Incident, name string, p, ipv4 TLSProber, slots chan struct{}) []Finding {
	urls := []string{incident.ControlURL}
	for _, host := range incident.Hosts {
		urls = append(urls, "https://"+host+"/")
	}
	probeOnce := func(prober TLSProber, url string) Outcome {
		select {
		case slots <- struct{}{}:
			defer func() { <-slots }()
			return prober.Probe(ctx, url)
		case <-ctx.Done():
			return Unknown
		}
	}
	results := make([]Outcome, len(urls))
	var wg sync.WaitGroup
	for i, url := range urls {
		probers := []TLSProber{p}
		if i == 0 {
			probers = controlProbers(p, ipv4)
		}
		wg.Go(func() {
			for _, prober := range probers {
				results[i] = probeOnce(prober, url)
				if results[i] != Unknown || ctx.Err() != nil {
					return
				}
			}
		})
	}
	wg.Wait()
	findings := []Finding{ProbeEvidenceFor(incident, name, results[0], results[1:])}
	// Print exact per-chain outcomes, never network error strings or response
	// bodies (which may contain proxy credentials or attacker-controlled text).
	for i, result := range results[1:] {
		findings = append(findings, ChainEvidence(incident, name, i, result))
	}
	return findings
}

// absentPackage is what pythonMetadata prints for a package that is not installed.
const absentPackage = "absent"

// Runtime metadata is a separate observation from TLS behavior.
const pythonMetadata = `import importlib.metadata, json, ssl
v={}
for n in ('certifi','pip'):
    try: v[n]=importlib.metadata.version(n)
    except importlib.metadata.PackageNotFoundError: v[n]='absent'
v['ssl']=ssl.OPENSSL_VERSION
print(json.dumps(v))
`

func PythonMetadata(result CommandResult) (map[string]string, bool) {
	values := make(map[string]string)
	if result.Code != 0 || result.Truncated || json.Unmarshal([]byte(result.Stdout), &values) != nil {
		return nil, false
	}
	return values, true
}
