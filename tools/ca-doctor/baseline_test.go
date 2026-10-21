package main

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/x509"
	"encoding/pem"
	"math/big"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
	"time"
)

func TestWindowsEnvAndDirectoryListSemantics(t *testing.T) {
	env := map[string]string{"Node_TLS_Reject_Unauthorized": "0", "Ssl_Cert_File": "C:\\資料\\ca.pem"}
	windows := NormalizeEnvironment(env, "windows")
	if got := EnvironmentEvidence(windows); len(got) != 2 || got[0].Level != "ERR" {
		t.Fatal(got)
	}
	if got := EnvironmentEvidence(NormalizeEnvironment(env, "linux")); len(got) != 0 {
		t.Fatal(got)
	}
	if got := CADirectoryPaths("linux", "/one:/two:"); !reflect.DeepEqual(got, []string{"/one", "/two", ""}) {
		t.Fatal(got)
	}
	if got := CADirectoryPaths("windows", `C:\one;D:\two`); !reflect.DeepEqual(got, []string{`C:\one`, `D:\two`}) {
		t.Fatal(got)
	}
}

func TestGitSSLNoVerifyIsPresenceBased(t *testing.T) {
	for _, value := range []string{"", "0", "false", "true", "1"} {
		findings := EnvironmentEvidence(map[string]string{"GIT_SSL_NO_VERIFY": value})
		if len(findings) != 1 || findings[0].Level != "ERR" {
			t.Fatalf("%q: %+v", value, findings)
		}
	}
	if got := EnvironmentEvidence(nil); len(got) != 0 {
		t.Fatal(got)
	}
	if got := GitVerifyEvidence(CommandResult{Code: 0, Stdout: "true"}, true); !strings.Contains(got.Detail, "overridden") {
		t.Fatal(got)
	}
}

func TestGitVerifyFailureIsNeverSilent(t *testing.T) {
	for _, tc := range []struct {
		r     CommandResult
		level string
	}{
		{CommandResult{Code: 1}, "WARN"},
		{CommandResult{Code: 128}, "WARN"},
		{CommandResult{Code: -1}, "WARN"},
		{CommandResult{Stdout: "false", Code: 0}, "ERR"},
		{CommandResult{Stdout: "garbage", Code: 0}, "WARN"},
		{CommandResult{Stdout: "true", Code: 0, Truncated: true}, "WARN"},
		{CommandResult{Stdout: "true", Code: 0}, "WARN"},
	} {
		if f := GitVerifyEvidence(tc.r, false); f.Level != tc.level {
			t.Fatal(f)
		}
	}
}

func TestExplicitCABundleHealth(t *testing.T) {
	now := time.Date(2026, 10, 21, 0, 0, 0, 0, time.UTC)
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	template := &x509.Certificate{SerialNumber: big.NewInt(1), NotBefore: now.Add(-time.Hour), NotAfter: now.Add(time.Hour), IsCA: true, BasicConstraintsValid: true, KeyUsage: x509.KeyUsageCertSign}
	der, err := x509.CreateCertificate(rand.Reader, template, template, &key.PublicKey, key)
	if err != nil {
		t.Fatal(err)
	}
	bundle := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der})
	if f := CABundleEvidence("test", bundle, now); f.Level != "OK" {
		t.Fatal(f)
	}
	if f := CABundleEvidence("test", bundle, now.Add(2*time.Hour)); f.Level != "WARN" {
		t.Fatal(f)
	}
	if f := CABundleEvidence("test", []byte("not a CA bundle"), now); f.Level != "ERR" {
		t.Fatal(f)
	}
	if f := CABundleEvidence("test", append(bundle, []byte("-----BEGIN CERTIFICATE-----\ninvalid")...), now); f.Level != "ERR" {
		t.Fatal(f)
	}
	malformed := []byte("-----BEGIN CERTIFICATE-----\n!!!!\n-----END CERTIFICATE-----\n")
	for _, data := range [][]byte{append(append([]byte{}, malformed...), bundle...), append(append(append([]byte{}, bundle...), malformed...), bundle...)} {
		if f := CABundleEvidence("test", data, now); f.Level != "ERR" {
			t.Fatal("skipped malformed certificate accepted", f)
		}
	}
	dir := t.TempDir()
	missing := CheckCAPaths(map[string]string{"SSL_CERT_FILE": filepath.Join(dir, "missing")}, "linux", now)
	if len(missing) != 1 || missing[0].Level != "ERR" {
		t.Fatal(missing)
	}
	paths := CheckCAPaths(map[string]string{"SSL_CERT_DIR": dir + ":" + dir + ":"}, "linux", now)
	if len(paths) != 3 || paths[0].Level != "WARN" || paths[2].Level != "WARN" {
		t.Fatal(paths)
	}
	file := filepath.Join(dir, "資料 with space.pem")
	if err := os.WriteFile(file, bundle, 0o600); err != nil {
		t.Fatal(err)
	}
	found := CheckCAPaths(map[string]string{"SSL_CERT_FILE": file}, "linux", now)
	if len(found) != 1 || found[0].Level != "OK" {
		t.Fatal(found)
	}
}

func TestBaselineUsesRealPositiveTLSOutcome(t *testing.T) {
	// Reuse the pure outcome boundary; no Internet is contacted.
	if f := BaselineEvidence("test", Accepted); f.Level != "OK" {
		t.Fatal(f)
	}
	if f := BaselineEvidence("test", CertRejected); f.Level != "WARN" {
		t.Fatal(f)
	}
	if f := BaselineEvidence("test", Unknown); f.Level != "WARN" {
		t.Fatal(f)
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if f := ProbeBaseline(ctx, "test", GoProbe{}, make(chan struct{})); f.Level != "WARN" {
		t.Fatal(f)
	}
}
