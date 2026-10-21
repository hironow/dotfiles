package main

import (
	"context"
	"crypto/tls"
	"encoding/json/v2"
	"errors"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"
)

type TLSProber interface {
	Probe(context.Context, string) Outcome
}

type GoProbe struct{ Client *http.Client }

func (p GoProbe) Probe(ctx context.Context, url string) Outcome {
	client := p.Client
	if client == nil {
		transport := &http.Transport{TLSHandshakeTimeout: 3 * time.Second}
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
}

const nodeProbe = `const tls=require('node:tls');
const u=new URL(process.argv[1]);
let done=false; let s;
function finish(x){if(done)return;done=true;console.log(x);if(s)s.destroy();}
s=tls.connect({host:u.hostname,port:Number(u.port||443),servername:u.hostname},()=>finish('accepted'));
s.setTimeout(3000,()=>finish('unknown'));
s.on('error',e=>finish(['UNABLE_TO_GET_ISSUER_CERT_LOCALLY','UNABLE_TO_VERIFY_LEAF_SIGNATURE','CERT_HAS_EXPIRED','CERT_REVOKED','ERR_TLS_CERT_ALTNAME_INVALID','DEPTH_ZERO_SELF_SIGNED_CERT','SELF_SIGNED_CERT_IN_CHAIN','CERT_SIGNATURE_FAILURE'].includes(e.code)?'certificate-rejected':'unknown'));
`

const pythonProbe = `import socket, ssl, sys, urllib.parse
u=urllib.parse.urlsplit(sys.argv[1])
try:
    with socket.create_connection((u.hostname,u.port or 443),timeout=3) as raw:
        with ssl.create_default_context().wrap_socket(raw,server_hostname=u.hostname):
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
	var args []string
	switch p.Kind {
	case "curl":
		args = []string{"-q", "--proto", "=https", "--connect-timeout", "3", "--max-time", "4", "--silent", "--show-error", "--output", os.DevNull, "--write-out", "%{http_code}", url}
	case "node":
		args = []string{"--eval", nodeProbe, url}
	case "python":
		args = []string{"-c", pythonProbe, url}
	case "bun":
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

func CurlOutcome(result CommandResult) Outcome {
	if result.Truncated {
		return Unknown
	}
	if result.Code == 60 {
		return CertRejected
	}
	status := strings.TrimSpace(result.Stdout)
	if result.Code == 0 && len(status) == 3 && status[0] >= '1' && status[0] <= '5' && status[1] >= '0' && status[1] <= '9' && status[2] >= '0' && status[2] <= '9' {
		return Accepted
	}
	return Unknown
}

// ProbeClient runs a fixed list, with a global concurrency cap shared by all
// clients. Result order is stable irrespective of completion order.
func ProbeClient(ctx context.Context, incident Incident, name string, p TLSProber, slots chan struct{}) []Finding {
	urls := []string{incident.ControlURL}
	for _, host := range incident.Hosts {
		urls = append(urls, "https://"+host+"/")
	}
	results := make([]Outcome, len(urls))
	var wg sync.WaitGroup
	for i, url := range urls {
		wg.Go(func() {
			select {
			case slots <- struct{}{}:
				defer func() { <-slots }()
				results[i] = p.Probe(ctx, url)
			case <-ctx.Done():
				results[i] = Unknown
			}
		})
	}
	wg.Wait()
	findings := []Finding{ProbeEvidenceFor(incident, name, results[0], results[1:])}
	// Print exact per-chain outcomes, never network error strings or response
	// bodies (which may contain proxy credentials or attacker-controlled text).
	for i, result := range results[1:] {
		level := "WARN"
		if result == Accepted {
			level = "ERR"
		}
		findings = append(findings, Finding{level, "ca-chain-" + incident.ID + "-" + name, incident.Hosts[i] + ": " + string(result)})
	}
	return findings
}

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
