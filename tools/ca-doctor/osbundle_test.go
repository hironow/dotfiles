package main

import (
	"bytes"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/sha256"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/asn1"
	"encoding/hex"
	"encoding/pem"
	"errors"
	"fmt"
	"math/big"
	"os"
	"path/filepath"
	"runtime"
	"slices"
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
		// a `### group` line always stays, even with no entry left under it
		{"first of a group, and a group's only entry", []UntrustedRoot{a1.root, b1.root}, header + groupAWithoutA1 + "\n### Group B\n\n" + groupC},
		{"the last entry of the file", []UntrustedRoot{c1.root}, header + groupA + "\n" + groupB + "\n### Group C\n"},
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

func TestPruneBundleNeverReachesPastAGroupLineForAnEntry(t *testing.T) {
	a, b := newTestCertificate(t, "a"), newTestCertificate(t, "b")
	head := "=== unrelated\n### KEEP\n"
	got, err := PruneBundle([]byte(head+a.pem+b.pem), []UntrustedRoot{a.root})
	if err != nil {
		t.Fatal(err)
	}
	if string(got.Out) != head+b.pem {
		t.Fatalf("pruned bundle:\n%s", got.Out)
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

// negativeSerial is a certificate whose serial number is -1: macOS's bundle
// holds such a root (EC-ACC), which Go's x509 parser refuses. Its signature
// no longer verifies, which PruneBundle does not check.
func negativeSerial(t *testing.T) testCertificate {
	t.Helper()
	c := newTestCertificate(t, "negative")
	block, _ := pem.Decode([]byte(c.pem))
	// the version (v3) and then the serial, 1, as newTestCertificate writes them
	positive := []byte{0xa0, 0x03, 0x02, 0x01, 0x02, 0x02, 0x01, 0x01}
	if bytes.Count(block.Bytes, positive) != 1 {
		t.Fatal("serial not found")
	}
	der := bytes.Replace(block.Bytes, positive, []byte{0xa0, 0x03, 0x02, 0x01, 0x02, 0x02, 0x01, 0xff}, 1)
	if _, err := x509.ParseCertificate(der); err == nil {
		t.Fatal("Go's parser now reads a negative serial; this test no longer pins anything")
	}
	return testCertificate{subject: c.subject, pem: string(pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der}))}
}

func TestPruneBundleKeepsACertificateWithANegativeSerial(t *testing.T) {
	negative, a := negativeSerial(t), newTestCertificate(t, "a")
	got, err := PruneBundle([]byte(negative.pem+a.pem), []UntrustedRoot{a.root})
	if err != nil {
		t.Fatal(err)
	}
	if string(got.Out) != negative.pem || got.Total != 2 {
		t.Fatalf("total %d, pruned:\n%s", got.Total, got.Out)
	}
}

// certificateRequestPEM is a PKCS #10 request, labeled as a certificate.
func certificateRequestPEM(t *testing.T) string {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	der, err := x509.CreateCertificateRequest(rand.Reader, &x509.CertificateRequest{Subject: pkix.Name{CommonName: "request"}}, key)
	if err != nil {
		t.Fatal(err)
	}
	return string(pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der}))
}

// withExtraElement is c's certificate with one more element at the end of
// its outer SEQUENCE.
func withExtraElement(t *testing.T, c testCertificate) string {
	t.Helper()
	block, _ := pem.Decode([]byte(c.pem))
	var outer asn1.RawValue
	if _, err := asn1.Unmarshal(block.Bytes, &outer); err != nil {
		t.Fatal(err)
	}
	outer.Bytes = append(outer.Bytes, 0x02, 0x01, 0x00) // INTEGER 0
	outer.FullBytes = nil
	der, err := asn1.Marshal(outer)
	if err != nil {
		t.Fatal(err)
	}
	return string(pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der}))
}

func TestPruneBundleRefusesWhatItCannotReadExactly(t *testing.T) {
	a, b := newTestCertificate(t, "a"), newTestCertificate(t, "b")
	request, extra := certificateRequestPEM(t), withExtraElement(t, a)
	for _, tc := range []struct {
		name, bundle string
		roots        []UntrustedRoot
		want         string
	}{
		{"a root not in the bundle", a.pem, []UntrustedRoot{b.root}, "not in the bundle"},
		{"a root twice", a.pem + a.pem, []UntrustedRoot{a.root}, "more than once"},
		{"a block that does not parse", "-----BEGIN CERTIFICATE-----\nnot base64!\n-----END CERTIFICATE-----\n" + a.pem, []UntrustedRoot{a.root}, "does not parse"},
		{"valid base64 that is no certificate", "-----BEGIN CERTIFICATE-----\nAQID\n-----END CERTIFICATE-----\n" + a.pem, []UntrustedRoot{a.root}, "not a certificate"},
		// an empty TBS, an empty algorithm, and an empty signature
		{"a certificate's outer shape only", "-----BEGIN CERTIFICATE-----\nMAcwADAAAwEA\n-----END CERTIFICATE-----\n" + a.pem, []UntrustedRoot{a.root}, "not a certificate"},
		{"a certificate request", request + a.pem, []UntrustedRoot{a.root}, "not a certificate"},
		{"an extra element in a certificate", extra + b.pem, []UntrustedRoot{b.root}, "not a certificate"},
		// a space after END would otherwise make one block of two, and drop both
		{"a space after END", strings.Replace(a.pem, pemEnd, pemEnd+" ", 1) + b.pem, []UntrustedRoot{a.root}, "PEM boundary"},
		{"a space after BEGIN", strings.Replace(a.pem, pemBegin, pemBegin+" ", 1) + b.pem, []UntrustedRoot{b.root}, "PEM boundary"},
		// LibreSSL trusts this form too, so a root in it must not be skipped
		{"a trusted certificate block", strings.ReplaceAll(a.pem, " CERTIFICATE-----", " TRUSTED CERTIFICATE-----") + b.pem, []UntrustedRoot{b.root}, "PEM boundary"},
		{"a block with headers", strings.Replace(a.pem, pemBegin+"\n", pemBegin+"\nProc-Type: 4,ENCRYPTED\n\n", 1) + b.pem, []UntrustedRoot{b.root}, "does not parse"},
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
			_, existed := os.Stat(f.backup)
			err := ApplyBundle(f.in, f.backup, f.inHash, f.outHash, f.roots)
			if err == nil || !strings.Contains(err.Error(), tc.want) {
				t.Fatalf("err = %v, want %q", err, tc.want)
			}
			if got, _ := os.ReadFile(f.in); !bytes.Equal(got, f.before) {
				t.Fatal("the input was changed")
			}
			backup, readErr := os.ReadFile(f.backup)
			if existed == nil && string(backup) != "older" {
				t.Fatalf("the existing backup was changed: %q", backup)
			}
			if existed != nil && !os.IsNotExist(readErr) {
				t.Fatal("a refused apply wrote a backup")
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
	head := header + "### Kept\n\n" + openBSDEntry(other)
	bundle = head + "\n### Comodo CA Limited\n\n" + openBSDEntry(aaa) + "\n### eMudhra Technologies Limited\n\n" + openBSDEntry(g3)
	// both entries go; their `### group` lines stay
	kept = head + "\n### Comodo CA Limited\n\n### eMudhra Technologies Limited\n"
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

// recordingFiles is the OS file system with each operation recorded and any
// of them able to fail as the OS can (a failing write lands part of its data
// first), so a test can check the order of the durable writes and what each
// failure leaves.
type recordingFiles struct {
	osFiles
	ops     []string
	failAt  map[string]bool
	root    bool
	dirSync int
}

var errInjected = errors.New("injected failure")

func failing(ops ...string) *recordingFiles {
	files := &recordingFiles{failAt: map[string]bool{}}
	for _, op := range ops {
		files.failAt[op] = true
	}
	return files
}

func (r *recordingFiles) record(op string) error {
	r.ops = append(r.ops, op)
	if r.failAt[op] {
		return errInjected
	}
	return nil
}

func (r *recordingFiles) label(path string) string {
	base := filepath.Base(path)
	switch {
	case strings.HasPrefix(base, ".ca-doctor-os-bundle-backup-"):
		return "backup-temp"
	case strings.HasPrefix(base, ".ca-doctor-os-bundle-"):
		return "temp"
	}
	return base
}

func (r *recordingFiles) CreateTemp(dir, pattern string) (bundleFile, error) {
	label := r.label(pattern)
	if err := r.record("create " + label); err != nil {
		return nil, err
	}
	file, err := r.osFiles.CreateTemp(dir, pattern)
	if err != nil {
		return nil, err
	}
	return &recordingFile{file, r, label}, nil
}

func (r *recordingFiles) Link(from, to string) error {
	if err := r.record("link " + r.label(from) + " " + r.label(to)); err != nil {
		return err
	}
	return r.osFiles.Link(from, to)
}

func (r *recordingFiles) Rename(from, to string) error {
	if err := r.record("rename " + r.label(from) + " " + r.label(to)); err != nil {
		return err
	}
	return r.osFiles.Rename(from, to)
}

func (r *recordingFiles) SyncDir(dir string) error {
	r.dirSync++
	if err := r.record(fmt.Sprintf("sync dir %d", r.dirSync)); err != nil {
		return err
	}
	return r.osFiles.SyncDir(dir)
}

func (r *recordingFiles) Remove(path string) error {
	if err := r.record("remove " + r.label(path)); err != nil {
		return err
	}
	return r.osFiles.Remove(path)
}

func (r *recordingFiles) IsRoot() bool { return r.root }

type recordingFile struct {
	bundleFile
	files *recordingFiles
	label string
}

// Write lands the first half of data, then fails, when told to fail.
func (f *recordingFile) Write(data []byte) (int, error) {
	if err := f.files.record("write " + f.label); err != nil {
		written, _ := f.bundleFile.Write(data[:len(data)/2])
		return written, err
	}
	return f.bundleFile.Write(data)
}

func (f *recordingFile) Chmod(mode os.FileMode) error {
	if err := f.files.record(fmt.Sprintf("chmod %s %o", f.label, mode)); err != nil {
		return err
	}
	return f.bundleFile.Chmod(mode)
}

// Chown is recorded, not run: these tests do not run as root.
func (f *recordingFile) Chown(uid, gid int) error {
	return f.files.record(fmt.Sprintf("chown %s %d %d", f.label, uid, gid))
}

func (f *recordingFile) Sync() error {
	if err := f.files.record("sync " + f.label); err != nil {
		return err
	}
	return f.bundleFile.Sync()
}

func (f *recordingFile) Close() error {
	err := f.files.record("close " + f.label)
	if closeErr := f.bundleFile.Close(); err == nil {
		err = closeErr
	}
	return err
}

// applySteps is a successful apply, as recordingFiles records it: the backup
// is written under a temporary name, synced, and published by a hard link,
// and its directory synced, before the new bundle is renamed over the old.
var applySteps = []string{
	"create backup-temp", "write backup-temp", "chmod backup-temp 644", "sync backup-temp", "close backup-temp",
	"link backup-temp cert.pem.backup", "remove backup-temp", "sync dir 1",
	"create temp", "write temp", "chmod temp 644", "sync temp", "close temp", "rename temp cert.pem", "sync dir 2",
}

func TestApplyBundleSyncsTheBackupBeforeTheBundleIsReplaced(t *testing.T) {
	f := newApplyFixture(t)
	files := failing()
	if err := applyBundle(files, f.in, f.backup, f.inHash, f.outHash, f.roots); err != nil {
		t.Fatal(err)
	}
	if strings.Join(files.ops, "\n") != strings.Join(applySteps, "\n") {
		t.Fatalf("operations:\n%s", strings.Join(files.ops, "\n"))
	}
}

func TestApplyBundleAsRootKeepsTheBundlesOwner(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("no owner to keep")
	}
	f := newApplyFixture(t)
	info, err := os.Lstat(f.in)
	if err != nil {
		t.Fatal(err)
	}
	uid, gid, ok := fileOwner(info)
	if !ok {
		t.Fatal("no owner")
	}
	files := failing()
	files.root = true
	if err := applyBundle(files, f.in, f.backup, f.inHash, f.outHash, f.roots); err != nil {
		t.Fatal(err)
	}
	for _, label := range []string{"backup-temp", "temp"} {
		if !slices.Contains(files.ops, fmt.Sprintf("chown %s %d %d", label, uid, gid)) {
			t.Fatalf("no chown of %s to %d:%d in\n%s", label, uid, gid, strings.Join(files.ops, "\n"))
		}
	}
}

// Run as root (sudo go test -run AsRealRoot), this checks the real chown.
func TestApplyBundleAsRealRootKeepsAnotherUsersOwnership(t *testing.T) {
	if runtime.GOOS == "windows" || os.Geteuid() != 0 {
		t.Skip("needs root")
	}
	f := newApplyFixture(t)
	if err := os.Chown(f.in, 1, 1); err != nil {
		t.Fatal(err)
	}
	if err := ApplyBundle(f.in, f.backup, f.inHash, f.outHash, f.roots); err != nil {
		t.Fatal(err)
	}
	for _, path := range []string{f.in, f.backup} {
		info, err := os.Lstat(path)
		if err != nil {
			t.Fatal(err)
		}
		if uid, gid, _ := fileOwner(info); uid != 1 || gid != 1 {
			t.Fatalf("%s is owned by %d:%d", path, uid, gid)
		}
	}
}

func TestApplyBundleFailingBeforeTheRenameLeavesTheBundleAndNoPartialBackup(t *testing.T) {
	// every step but the last directory sync, which comes after the rename
	for _, step := range applySteps[:len(applySteps)-1] {
		t.Run(step, func(t *testing.T) {
			f := newApplyFixture(t)
			err := applyBundle(failing(step), f.in, f.backup, f.inHash, f.outHash, f.roots)
			if !errors.Is(err, errInjected) {
				t.Fatalf("err = %v", err)
			}
			if got, _ := os.ReadFile(f.in); !bytes.Equal(got, f.before) {
				t.Fatal("the bundle was changed")
			}
			// the backup is published only complete
			if backup, err := os.ReadFile(f.backup); err == nil && !bytes.Equal(backup, f.before) {
				t.Fatalf("a partial backup is left: %d bytes", len(backup))
			}
			entries, _ := os.ReadDir(f.dir)
			for _, entry := range entries {
				leftover := strings.HasPrefix(entry.Name(), ".ca-doctor-os-bundle-")
				if leftover && step != "remove backup-temp" {
					t.Fatalf("a temporary file is left: %s", entry.Name())
				}
				if leftover && !strings.Contains(err.Error(), entry.Name()) {
					t.Fatalf("the error does not name the file left: %v", err)
				}
			}
		})
	}
}

func TestApplyBundleReportsATemporaryFileItCouldNotRemove(t *testing.T) {
	f := newApplyFixture(t)
	err := applyBundle(failing("write temp", "remove temp"), f.in, f.backup, f.inHash, f.outHash, f.roots)
	if !errors.Is(err, errInjected) || !strings.Contains(err.Error(), "is left") {
		t.Fatalf("err = %v", err)
	}
	if got, _ := os.ReadFile(f.in); !bytes.Equal(got, f.before) {
		t.Fatal("the bundle was changed")
	}
}

func TestApplyBundleSaysWhenTheBundleIsReplacedButNotSynced(t *testing.T) {
	f := newApplyFixture(t)
	err := applyBundle(failing("sync dir 2"), f.in, f.backup, f.inHash, f.outHash, f.roots)
	if !errors.Is(err, errInjected) || !strings.Contains(err.Error(), "was replaced") {
		t.Fatalf("err = %v", err)
	}
	if got, _ := os.ReadFile(f.in); !bytes.Equal(got, f.after) {
		t.Fatal("the bundle was not replaced")
	}
}

func TestOSBundleCandidateNeverOverwritesAnExistingFile(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("os-bundle edits a POSIX PEM bundle")
	}
	bundle, _ := rootsBundle(t)
	dir := t.TempDir()
	in := filepath.Join(dir, "cert.pem")
	if err := os.WriteFile(in, []byte(bundle), 0o644); err != nil {
		t.Fatal(err)
	}
	symlink, hardlink := filepath.Join(dir, "symlink.pem"), filepath.Join(dir, "hardlink.pem")
	if err := os.Symlink(in, symlink); err != nil {
		t.Fatal(err)
	}
	if err := os.Link(in, hardlink); err != nil {
		t.Fatal(err)
	}
	for _, out := range []string{in, symlink, hardlink} {
		t.Run(filepath.Base(out), func(t *testing.T) {
			var report bytes.Buffer
			code := RunCLI(t.Context(), []string{"os-bundle", "--source", ".", "--incident", "emudhra-2026", "--in", in, "--out", out}, &report)
			if code != 2 || !strings.Contains(report.String(), "exists") {
				t.Fatalf("exit %d:\n%s", code, &report)
			}
			if got, _ := os.ReadFile(in); string(got) != bundle {
				t.Fatal("the bundle was overwritten")
			}
		})
	}
}
