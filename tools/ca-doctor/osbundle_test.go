package main

import (
	"bytes"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/sha256"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/hex"
	"encoding/pem"
	"math/big"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"
)

// testCertificate is a self-signed certificate's PEM and its root entry.
type testCertificate struct {
	subject string
	pem     string
	root    UntrustedRoot
}

func newTestCertificate(t *testing.T, name string) testCertificate {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	template := &x509.Certificate{
		SerialNumber: big.NewInt(1),
		Subject:      pkix.Name{CommonName: name},
		NotBefore:    time.Now().Add(-time.Hour),
		NotAfter:     time.Now().Add(time.Hour),
		IsCA:         true,
	}
	der, err := x509.CreateCertificate(rand.Reader, template, template, &key.PublicKey, key)
	if err != nil {
		t.Fatal(err)
	}
	sum := sha256.Sum256(der)
	subject := "/CN=" + name
	return testCertificate{
		subject: subject,
		pem:     string(pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der})),
		root:    UntrustedRoot{SHA256: hex.EncodeToString(sum[:]), Subject: subject},
	}
}

// openBSDEntry is one certificate as macOS's /private/etc/ssl/cert.pem holds
// it: a `=== subject` line, a text dump, then the PEM block.
func openBSDEntry(c testCertificate) string {
	return "=== " + c.subject + "\nCertificate:\n    Data:\n        Subject: " + c.subject + "\n" + c.pem
}

func TestPruneBundleKeepsEveryOtherByteOfAnOpenBSDBundle(t *testing.T) {
	a1, a2 := newTestCertificate(t, "a1"), newTestCertificate(t, "a2")
	b1, c1 := newTestCertificate(t, "b1"), newTestCertificate(t, "c1")
	header := "# $OpenBSD: cert.pem,v 1.0 $\n"
	groupA := "### Group A\n\n" + openBSDEntry(a1) + "\n" + openBSDEntry(a2)
	groupAWithoutA1 := "### Group A\n\n" + openBSDEntry(a2)
	groupB := "### Group B\n\n" + openBSDEntry(b1)
	groupC := "### Group C\n\n" + openBSDEntry(c1)
	bundle := header + groupA + "\n" + groupB + "\n" + groupC
	for _, tc := range []struct {
		name  string
		roots []UntrustedRoot
		want  string
	}{
		// a1 leaves a2 in its group, so the group's line stays; b1 was its
		// group's only entry, so the group's line goes too
		{"first of a group, and a whole group", []UntrustedRoot{a1.root, b1.root}, header + groupAWithoutA1 + "\n" + groupC},
		{"the last entry of the file", []UntrustedRoot{c1.root}, header + groupA + "\n" + groupB},
		{"the second of a group", []UntrustedRoot{a2.root}, header + "### Group A\n\n" + openBSDEntry(a1) + "\n" + groupB + "\n" + groupC},
	} {
		t.Run(tc.name, func(t *testing.T) {
			got, err := PruneBundle([]byte(bundle), tc.roots)
			if err != nil {
				t.Fatal(err)
			}
			if string(got.Out) != tc.want {
				t.Fatalf("pruned bundle:\n%s\nwant:\n%s", got.Out, tc.want)
			}
			if got.Total != 4 || len(got.Dropped) != len(tc.roots) {
				t.Fatalf("total %d, dropped %+v", got.Total, got.Dropped)
			}
		})
	}
}

func TestPruneBundleRemovesOnlyTheBlockOfAPlainPEMFile(t *testing.T) {
	p1, p2, p3 := newTestCertificate(t, "p1"), newTestCertificate(t, "p2"), newTestCertificate(t, "p3")
	got, err := PruneBundle([]byte(p1.pem+p2.pem+p3.pem), []UntrustedRoot{p2.root})
	if err != nil {
		t.Fatal(err)
	}
	if string(got.Out) != p1.pem+p3.pem {
		t.Fatalf("pruned bundle:\n%s", got.Out)
	}
	if len(got.Dropped) != 1 || got.Dropped[0] != p2.root {
		t.Fatalf("dropped %+v", got.Dropped)
	}
}

func TestPruneBundleRefusesWhatItCannotReadExactly(t *testing.T) {
	a, b := newTestCertificate(t, "a"), newTestCertificate(t, "b")
	for _, tc := range []struct {
		name, bundle string
		roots        []UntrustedRoot
		want         string
	}{
		{"a root not in the bundle", a.pem, []UntrustedRoot{b.root}, "not in the bundle"},
		{"a root twice", a.pem + a.pem, []UntrustedRoot{a.root}, "more than once"},
		{"a block that does not parse", "-----BEGIN CERTIFICATE-----\nnot base64!\n-----END CERTIFICATE-----\n" + a.pem, []UntrustedRoot{a.root}, "does not parse"},
		{"an unterminated block", a.pem + "-----BEGIN CERTIFICATE-----\nAAAA\n", []UntrustedRoot{a.root}, "unterminated"},
		{"no root", a.pem, nil, "no root"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			if _, err := PruneBundle([]byte(tc.bundle), tc.roots); err == nil || !strings.Contains(err.Error(), tc.want) {
				t.Fatalf("err = %v, want %q", err, tc.want)
			}
		})
	}
}

// applyFixture is a bundle file to prune, in a temp directory, and the hashes
// a candidate run would print for it.
type applyFixture struct {
	dir, in, backup, inHash, outHash string
	before, after                    []byte
	roots                            []UntrustedRoot
}

func newApplyFixture(t *testing.T) applyFixture {
	t.Helper()
	a, b := newTestCertificate(t, "a"), newTestCertificate(t, "b")
	dir := t.TempDir()
	in := filepath.Join(dir, "cert.pem")
	before := []byte(a.pem + b.pem)
	if err := os.WriteFile(in, before, 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.Chmod(in, 0o644); err != nil {
		t.Fatal(err)
	}
	return applyFixture{
		dir: dir, in: in, backup: filepath.Join(dir, "cert.pem.backup"),
		inHash: contentSHA256(before), outHash: contentSHA256([]byte(a.pem)),
		before: before, after: []byte(a.pem), roots: []UntrustedRoot{b.root},
	}
}

func TestApplyBundleReplacesTheFileAfterADurableBackup(t *testing.T) {
	f := newApplyFixture(t)
	if err := ApplyBundle(f.in, f.backup, f.inHash, f.outHash, f.roots); err != nil {
		t.Fatal(err)
	}
	if got, _ := os.ReadFile(f.in); !bytes.Equal(got, f.after) {
		t.Fatalf("replaced file:\n%s", got)
	}
	if got, _ := os.ReadFile(f.backup); !bytes.Equal(got, f.before) {
		t.Fatalf("backup:\n%s", got)
	}
	if runtime.GOOS != "windows" {
		for _, path := range []string{f.in, f.backup} {
			if info, err := os.Stat(path); err != nil || info.Mode().Perm() != 0o644 {
				t.Fatalf("%s mode = %v, %v", path, info.Mode().Perm(), err)
			}
		}
	}
	// no temporary file is left beside it
	entries, _ := os.ReadDir(f.dir)
	if len(entries) != 2 {
		t.Fatalf("directory holds %d entries", len(entries))
	}
}

func TestApplyBundleWritesNothingUnlessBothHashesMatchAndTheBackupIsNew(t *testing.T) {
	for _, tc := range []struct {
		name string
		edit func(*applyFixture)
		want string
	}{
		{"the input changed", func(f *applyFixture) { f.inHash = strings.Repeat("0", 64) }, "input"},
		{"the prune gives other bytes", func(f *applyFixture) { f.outHash = strings.Repeat("0", 64) }, "candidate"},
		{"the backup exists", func(f *applyFixture) {
			if err := os.WriteFile(f.backup, []byte("older"), 0o600); err != nil {
				panic(err)
			}
		}, "backup"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			f := newApplyFixture(t)
			tc.edit(&f)
			err := ApplyBundle(f.in, f.backup, f.inHash, f.outHash, f.roots)
			if err == nil || !strings.Contains(err.Error(), tc.want) {
				t.Fatalf("err = %v, want %q", err, tc.want)
			}
			if got, _ := os.ReadFile(f.in); !bytes.Equal(got, f.before) {
				t.Fatal("the input was changed")
			}
		})
	}
}

// rootsBundle is an OpenBSD-format bundle holding a generated certificate
// and the two public roots that emudhra-2026 lists.
func rootsBundle(t *testing.T) (bundle, kept string) {
	t.Helper()
	other := newTestCertificate(t, "kept")
	g3 := testCertificate{subject: "/CN=emSign ECC Root CA - G3", pem: emsignECCRootCAG3PEM}
	aaa := testCertificate{subject: "/CN=AAA Certificate Services", pem: aaaCertificateServicesPEM}
	header := "# $OpenBSD: cert.pem,v 1.0 $\n"
	kept = header + "### Kept\n\n" + openBSDEntry(other)
	bundle = kept + "\n### Comodo CA Limited\n\n" + openBSDEntry(aaa) + "\n### eMudhra Technologies Limited\n\n" + openBSDEntry(g3)
	return bundle, kept
}

func TestOSBundleCandidateThenApplyThroughTheCLI(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("os-bundle edits a POSIX PEM bundle")
	}
	bundle, kept := rootsBundle(t)
	dir := t.TempDir()
	in, candidate, backup := filepath.Join(dir, "cert.pem"), filepath.Join(dir, "candidate.pem"), filepath.Join(dir, "backup.pem")
	if err := os.WriteFile(in, []byte(bundle), 0o644); err != nil {
		t.Fatal(err)
	}
	var out bytes.Buffer
	code := RunCLI(t.Context(), []string{"os-bundle", "--source", ".", "--incident", "emudhra-2026", "--in", in, "--out", candidate}, &out)
	if code != 0 {
		t.Fatalf("candidate exit %d:\n%s", code, &out)
	}
	if got, _ := os.ReadFile(candidate); string(got) != kept {
		t.Fatalf("candidate:\n%s", got)
	}
	inHash, outHash := contentSHA256([]byte(bundle)), contentSHA256([]byte(kept))
	for _, want := range []string{inHash, outHash, "emSign ECC Root CA - G3", "AAA Certificate Services", "kept 1 of 3 certificates"} {
		if !strings.Contains(out.String(), want) {
			t.Fatalf("candidate output lacks %q:\n%s", want, &out)
		}
	}
	out.Reset()
	code = RunCLI(t.Context(), []string{"os-bundle", "--source", ".", "--incident", "emudhra-2026", "--in", in, "--apply", "--expect-sha256", inHash, "--expect-out-sha256", outHash, "--backup", backup}, &out)
	if code != 0 {
		t.Fatalf("apply exit %d:\n%s", code, &out)
	}
	if got, _ := os.ReadFile(in); string(got) != kept {
		t.Fatalf("applied:\n%s", got)
	}
	if got, _ := os.ReadFile(backup); string(got) != bundle {
		t.Fatal("backup differs from the old bundle")
	}
}

func TestOSBundleRefusesAStaleBinaryOrBadArgumentsBeforeWriting(t *testing.T) {
	bundle, _ := rootsBundle(t)
	dir := t.TempDir()
	in, candidate := filepath.Join(dir, "cert.pem"), filepath.Join(dir, "candidate.pem")
	if err := os.WriteFile(in, []byte(bundle), 0o644); err != nil {
		t.Fatal(err)
	}
	for _, tc := range []struct {
		name string
		args []string
		want string
		code int
	}{
		{"stale source", []string{"os-bundle", "--source", t.TempDir(), "--incident", "emudhra-2026", "--in", in, "--out", candidate}, "WARN ca-build", 1},
		{"unknown incident", []string{"os-bundle", "--source", ".", "--incident", "nope", "--in", in, "--out", candidate}, "ERR", 2},
		{"no mode", []string{"os-bundle", "--source", ".", "--incident", "emudhra-2026", "--in", in}, "ca-arguments", 2},
		{"both modes", []string{"os-bundle", "--source", ".", "--incident", "emudhra-2026", "--in", in, "--out", candidate, "--apply"}, "ca-arguments", 2},
		{"apply without hashes", []string{"os-bundle", "--source", ".", "--incident", "emudhra-2026", "--in", in, "--apply", "--backup", candidate}, "ca-arguments", 2},
	} {
		t.Run(tc.name, func(t *testing.T) {
			var out bytes.Buffer
			if code := RunCLI(t.Context(), tc.args, &out); code != tc.code || !strings.Contains(out.String(), tc.want) {
				t.Fatalf("exit %d, output:\n%s", code, &out)
			}
			if _, err := os.Stat(candidate); err == nil {
				t.Fatal("a candidate was written")
			}
			if got, _ := os.ReadFile(in); string(got) != bundle {
				t.Fatal("the input was changed")
			}
		})
	}
}
