package main

import (
	"bytes"
	"context"
	"crypto/x509"
	"encoding/pem"
	"fmt"
	"io"
	"os"
	"strings"
	"time"
)

const maxCABundle = 1 << 20

func CADirectoryPaths(goos, value string) []string {
	separator := ":"
	if goos == "windows" {
		separator = ";"
	}
	return strings.Split(value, separator)
}

func BaselineEvidence(client string, result Outcome) Finding {
	f := Finding{"WARN", "ca-https-" + client, "baseline=" + baselineControlURL + "; " + string(result) + "; normal HTTPS verification unconfirmed"}
	if result == Accepted {
		f.Level = "OK"
		f.Detail = "baseline HTTPS accepted by this client: " + baselineControlURL + "; only this observed connection path"
	}
	return f
}

func ProbeBaseline(ctx context.Context, name string, p TLSProber, slots chan struct{}) Finding {
	select {
	case slots <- struct{}{}:
		defer func() { <-slots }()
		return BaselineEvidence(name, p.Probe(ctx, baselineControlURL))
	case <-ctx.Done():
		return BaselineEvidence(name, Unknown)
	}
}

// These checks validate syntax, dates and accessibility of explicit overrides,
// not trust policy. Root expiry semantics differ between verification engines.
func CABundleEvidence(name string, data []byte, now time.Time) Finding {
	count, invalid, expired, notYetValid := 0, 0, 0, 0
	parsedBlocks := 0
	markers := bytes.Count(data, []byte("-----BEGIN CERTIFICATE-----"))
	rest := data
	for {
		block, remaining := pem.Decode(rest)
		if block == nil {
			if bytes.Contains(rest, []byte("-----BEGIN CERTIFICATE-----")) {
				invalid++
			}
			break
		}
		rest = remaining
		if block.Type != "CERTIFICATE" {
			continue
		}
		parsedBlocks++
		cert, err := x509.ParseCertificate(block.Bytes)
		if err != nil {
			invalid++
			continue
		}
		count++
		if !now.Before(cert.NotAfter) {
			expired++
		}
		if now.Before(cert.NotBefore) {
			notYetValid++
		}
	}
	f := Finding{"OK", "ca-file-" + name, fmt.Sprintf("PEM parsed: %d certificates; trust/revocation unverified; path/subjects redacted", count)}
	// pem.Decode can skip a malformed block to find a later valid block.
	// Account for every certificate opening marker, including skipped prefixes.
	if count == 0 || invalid > 0 || parsedBlocks != markers {
		f.Level = "ERR"
		f.Detail = "explicit CA file contains no certificates or malformed PEM/X509; value redacted"
		return f
	}
	if expired > 0 || notYetValid > 0 {
		f.Level = "WARN"
		f.Detail = fmt.Sprintf("PEM parsed: %d expired, %d not yet valid by local clock; root validity semantics/trust unverified", expired, notYetValid)
	}
	return f
}

func CheckCAPaths(env map[string]string, goos string, now time.Time) []Finding {
	var findings []Finding
	for _, key := range []string{"SSL_CERT_FILE", "SSL_CERT_DIR", "CURL_CA_BUNDLE", "REQUESTS_CA_BUNDLE", "PIP_CERT", "GIT_SSL_CAINFO", "GIT_SSL_CAPATH", "NODE_EXTRA_CA_CERTS"} {
		value := env[key]
		if value == "" {
			continue
		}
		directories := key == "SSL_CERT_DIR" || key == "GIT_SSL_CAPATH"
		paths := []string{value}
		if directories {
			paths = CADirectoryPaths(goos, value)
		}
		for _, path := range paths {
			if path == "" {
				findings = append(findings, Finding{"WARN", "ca-path-" + key, "empty CA directory list component; backend semantics unverified"})
				continue
			}
			findings = append(findings, inspectCAPath(key, path, directories, key == "REQUESTS_CA_BUNDLE", now))
		}
	}
	return findings
}

func inspectCAPath(key, path string, directory, allowDirectory bool, now time.Time) Finding {
	fail := Finding{"ERR", "ca-path-" + key, "explicit CA path missing, unreadable, wrong type or too large; path redacted"}
	file, err := os.Open(path)
	if err != nil {
		return fail
	}
	defer func() { _ = file.Close() }()
	info, err := file.Stat()
	if err != nil {
		return fail
	}
	if info.IsDir() {
		if !directory && !allowDirectory {
			return fail
		}
		// Open/stat do not prove that the consuming TLS backend can use hashes or
		// PKCS#11 links. Do not inspect or recursively enumerate directory contents.
		return Finding{"WARN", "ca-path-" + key, "CA directory can be opened; contents/backend usability not assessed; path redacted"}
	}
	if directory || !info.Mode().IsRegular() || info.Size() > maxCABundle {
		return fail
	}
	data, err := io.ReadAll(io.LimitReader(file, maxCABundle+1))
	if err != nil || len(data) > maxCABundle {
		return fail
	}
	return CABundleEvidence(key, data, now)
}
