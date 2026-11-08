package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/asn1"
	"encoding/hex"
	"encoding/pem"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
)

// `ca-doctor os-bundle` removes an incident's untrusted roots from an OS PEM
// bundle, such as macOS's /private/etc/ssl/cert.pem, which Apple's LibreSSL
// clients read and no CA variable overrides. It runs in two steps: a
// candidate run (no root) writes the new bundle to a new file, and an apply
// run (as root) installs exactly those bytes after a durable backup.

const (
	pemBegin = "-----BEGIN CERTIFICATE-----"
	pemEnd   = "-----END CERTIFICATE-----"
)

// BundlePrune is a bundle without some roots.
type BundlePrune struct {
	Out     []byte
	Dropped []UntrustedRoot // in the bundle's order
	Total   int             // certificates in the input
}

// PruneBundle returns data without the certificates whose DER SHA-256 is one
// of roots, keeping every other byte in order. In the OpenBSD layout of
// macOS's bundle, a certificate's entry is the blank line, the `=== subject`
// line, and the text dump before its PEM block, and they go with it; a
// `### group` line always stays. It reads strictly, so that what it removes
// is exactly what it parsed: every PEM boundary must be a bare
// `-----BEGIN CERTIFICATE-----` or `-----END CERTIFICATE-----` line, every
// block one certificate with no headers, and each root in the bundle once.
func PruneBundle(data []byte, roots []UntrustedRoot) (BundlePrune, error) {
	if len(roots) == 0 {
		return BundlePrune{}, errors.New("no root to remove")
	}
	wanted := map[string]UntrustedRoot{}
	for _, root := range roots {
		wanted[root.SHA256] = root
	}
	lines := bytes.SplitAfter(data, []byte("\n"))
	if len(lines[len(lines)-1]) == 0 {
		lines = lines[:len(lines)-1]
	}
	remove := make([]bool, len(lines))
	found := map[string]int{}
	var result BundlePrune
	previousEnd := 0 // the first line after the previous block
	for begin := 0; begin < len(lines); begin++ {
		switch boundary(lines[begin]) {
		case "":
			continue
		case pemBegin:
		default:
			return BundlePrune{}, fmt.Errorf("unsupported PEM boundary at line %d", begin+1)
		}
		end := begin + 1
		for ; end < len(lines); end++ {
			mark := boundary(lines[end])
			if mark == pemEnd {
				break
			}
			if mark != "" {
				return BundlePrune{}, fmt.Errorf("unsupported PEM boundary at line %d", end+1)
			}
		}
		if end == len(lines) {
			return BundlePrune{}, fmt.Errorf("unterminated certificate block at line %d", begin+1)
		}
		der, err := certificateDER(bytes.Join(lines[begin:end+1], nil))
		if err != nil {
			return BundlePrune{}, fmt.Errorf("certificate block at line %d: %w", begin+1, err)
		}
		result.Total++
		sum := sha256.Sum256(der)
		fingerprint := hex.EncodeToString(sum[:])
		if root, ok := wanted[fingerprint]; ok {
			found[fingerprint]++
			result.Dropped = append(result.Dropped, root)
			for line := entryStart(lines, previousEnd, begin); line <= end; line++ {
				remove[line] = true
			}
		}
		previousEnd = end + 1
		begin = end
	}
	for _, root := range roots {
		switch found[root.SHA256] {
		case 0:
			return BundlePrune{}, fmt.Errorf("root %s (%s) is not in the bundle", root.Subject, root.SHA256)
		case 1:
		default:
			return BundlePrune{}, fmt.Errorf("root %s (%s) is in the bundle more than once", root.Subject, root.SHA256)
		}
	}
	for index, line := range lines {
		if !remove[index] {
			result.Out = append(result.Out, line...)
		}
	}
	return result, nil
}

func lineText(line []byte) string {
	return strings.TrimRight(string(line), "\r\n")
}

// boundary is the line's PEM boundary: pemBegin, pemEnd, "" for no boundary,
// or the line itself for any other text that looks like one (a space after
// it, another type such as TRUSTED CERTIFICATE), which PruneBundle refuses.
func boundary(line []byte) string {
	text := lineText(line)
	if text == pemBegin || text == pemEnd {
		return text
	}
	if trimmed := strings.TrimSpace(text); strings.HasPrefix(trimmed, "-----BEGIN") || strings.HasPrefix(trimmed, "-----END") {
		return text
	}
	return ""
}

// certificateShape is an X.509 certificate's outer structure (RFC 5280):
// enough to tell a certificate from other bytes without x509's checks, which
// refuse roots that macOS's bundle still holds (EC-ACC has a negative serial).
type certificateShape struct {
	TBSCertificate     asn1.RawValue
	SignatureAlgorithm asn1.RawValue
	SignatureValue     asn1.BitString
}

// certificateDER is the DER of a block that holds exactly one certificate.
func certificateDER(block []byte) ([]byte, error) {
	decoded, rest := pem.Decode(block)
	if decoded == nil || decoded.Type != "CERTIFICATE" || len(decoded.Headers) != 0 || len(bytes.TrimSpace(rest)) != 0 {
		return nil, errors.New("does not parse as one PEM certificate")
	}
	var shape certificateShape
	trailing, err := asn1.Unmarshal(decoded.Bytes, &shape)
	if err == nil && (len(trailing) != 0 || shape.TBSCertificate.Tag != asn1.TagSequence || shape.SignatureAlgorithm.Tag != asn1.TagSequence) {
		err = errors.New("not a certificate's structure")
	}
	if err != nil {
		return nil, fmt.Errorf("not a certificate: %w", err)
	}
	return decoded.Bytes, nil
}

func blank(line []byte) bool { return lineText(line) == "" }

// entryStart is the first line that goes with the block starting at begin:
// the block itself in a plain PEM file, or its OpenBSD entry (the `===` line
// and the blank line before it).
func entryStart(lines [][]byte, previousEnd, begin int) int {
	for line := begin - 1; line >= previousEnd; line-- {
		if strings.HasPrefix(lineText(lines[line]), "=== ") {
			if line-1 >= previousEnd && blank(lines[line-1]) {
				return line - 1
			}
			return line
		}
	}
	return begin
}

func contentSHA256(data []byte) string {
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:])
}

// bundleFiles is the file system ApplyBundle writes through: osFiles, or a
// recording one in tests.
type bundleFiles interface {
	Lstat(path string) (os.FileInfo, error)
	ReadFile(path string) ([]byte, error)
	CreateNew(path string, perm os.FileMode) (bundleFile, error)
	CreateTemp(dir, pattern string) (bundleFile, error)
	Rename(from, to string) error
	SyncDir(dir string) error
	Remove(path string) error
	IsRoot() bool
}

type bundleFile interface {
	Name() string
	Write(data []byte) (int, error)
	Chmod(mode os.FileMode) error
	Chown(uid, gid int) error
	Sync() error
	Close() error
}

type osFiles struct{}

func (osFiles) Lstat(path string) (os.FileInfo, error) { return os.Lstat(path) }
func (osFiles) ReadFile(path string) ([]byte, error)   { return os.ReadFile(path) }
func (osFiles) Rename(from, to string) error           { return os.Rename(from, to) }
func (osFiles) Remove(path string) error               { return os.Remove(path) }
func (osFiles) IsRoot() bool                           { return os.Geteuid() == 0 }

func (osFiles) CreateNew(path string, perm os.FileMode) (bundleFile, error) {
	return os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, perm)
}

func (osFiles) CreateTemp(dir, pattern string) (bundleFile, error) {
	return os.CreateTemp(dir, pattern)
}

func (osFiles) SyncDir(dir string) error {
	directory, err := os.Open(dir)
	if err != nil {
		return err
	}
	err = directory.Sync()
	if closeErr := directory.Close(); err == nil {
		err = closeErr
	}
	return err
}

// ApplyBundle replaces in with its prune, but only when in's SHA-256 is
// expectIn and the prune's is expectOut, the hashes a candidate run printed,
// and backup does not exist yet. The backup is written and synced, with its
// directory, before the new bundle is renamed over in; a backup that could
// not be completed is removed, so a rollback never copies a partial one.
func ApplyBundle(in, backup, expectIn, expectOut string, roots []UntrustedRoot) error {
	return applyBundle(osFiles{}, in, backup, expectIn, expectOut, roots)
}

func applyBundle(files bundleFiles, in, backup, expectIn, expectOut string, roots []UntrustedRoot) error {
	info, err := files.Lstat(in)
	if err != nil {
		return err
	}
	if !info.Mode().IsRegular() {
		return fmt.Errorf("%s is not a regular file", in)
	}
	data, err := files.ReadFile(in)
	if err != nil {
		return err
	}
	if got := contentSHA256(data); got != expectIn {
		return fmt.Errorf("the input's sha256 is %s, not %s; run the candidate again", got, expectIn)
	}
	prune, err := PruneBundle(data, roots)
	if err != nil {
		return err
	}
	if got := contentSHA256(prune.Out); got != expectOut {
		return fmt.Errorf("the prune's sha256 is %s, not the candidate's %s; run the candidate again", got, expectOut)
	}
	saved, err := files.CreateNew(backup, info.Mode().Perm())
	if err != nil {
		return fmt.Errorf("backup %s: %w", backup, err)
	}
	if err := fill(files, saved, data, info); err != nil {
		_ = files.Remove(backup)
		return fmt.Errorf("backup %s: %w", backup, err)
	}
	if err := files.SyncDir(filepath.Dir(backup)); err != nil {
		return err
	}
	temporary, err := files.CreateTemp(filepath.Dir(in), ".ca-doctor-os-bundle-*")
	if err != nil {
		return err
	}
	if err := fill(files, temporary, prune.Out, info); err != nil {
		_ = files.Remove(temporary.Name())
		return err
	}
	if err := files.Rename(temporary.Name(), in); err != nil {
		_ = files.Remove(temporary.Name())
		return err
	}
	return files.SyncDir(filepath.Dir(in))
}

// fill writes data to file with like's mode (and, as root, its owner),
// syncs it, and closes it.
func fill(files bundleFiles, file bundleFile, data []byte, like os.FileInfo) error {
	_, err := file.Write(data)
	if err == nil {
		err = file.Chmod(like.Mode().Perm())
	}
	if uid, gid, ok := fileOwner(like); err == nil && ok && files.IsRoot() {
		err = file.Chown(uid, gid)
	}
	if err == nil {
		err = file.Sync()
	}
	if closeErr := file.Close(); err == nil {
		err = closeErr
	}
	return err
}

const osBundleUsage = "usage: ca-doctor os-bundle --source DIR --incident ID --in FILE (--out NEW-FILE | --apply --expect-sha256 HEX --expect-out-sha256 HEX --backup NEW-FILE)"

func runOSBundle(args []string, out io.Writer) int {
	flags := flag.NewFlagSet("os-bundle", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	source := flags.String("source", "tools/ca-doctor", "source directory for build freshness verification")
	incidentID := flags.String("incident", "", "incident whose untrusted roots to remove")
	in := flags.String("in", "", "the PEM bundle")
	candidate := flags.String("out", "", "write the candidate bundle to this new file (no root needed)")
	apply := flags.Bool("apply", false, "replace --in with the candidate (as root)")
	expectIn := flags.String("expect-sha256", "", "the input's sha256 the candidate run printed")
	expectOut := flags.String("expect-out-sha256", "", "the candidate's sha256 the candidate run printed")
	backup := flags.String("backup", "", "where to keep the old bundle; must not exist")
	usage := []Finding{{"ERR", "ca-arguments", osBundleUsage}}
	if err := flags.Parse(args); err != nil || flags.NArg() != 0 || *in == "" || *incidentID == "" || *apply == (*candidate != "") {
		return Report(out, usage)
	}
	if *apply && (*expectIn == "" || *expectOut == "" || *backup == "") {
		return Report(out, usage)
	}
	if runtime.GOOS == "windows" {
		return Report(out, []Finding{{"ERR", "ca-os-bundle", "os-bundle edits a POSIX PEM bundle; Windows keeps its roots in its own store"}})
	}
	if !SourceMatches(*source) {
		return Report(out, []Finding{{"WARN", "ca-build", "missing/changed source or stale binary; run just ca-doctor-build; nothing written"}})
	}
	if incidentError != nil {
		return Report(out, []Finding{{"ERR", "ca-policy", "invalid embedded incident data; review source and rebuild"}})
	}
	var roots []UntrustedRoot
	known := false
	for _, incident := range incidents {
		if incident.ID == *incidentID {
			roots, known = incident.UntrustedRoots, true
		}
	}
	if !known || len(roots) == 0 {
		return Report(out, []Finding{{"ERR", "ca-os-bundle", "incident " + strconv.Quote(*incidentID) + " lists no untrusted roots"}})
	}
	data, err := os.ReadFile(*in)
	if err != nil {
		return Report(out, []Finding{{"ERR", "ca-os-bundle", err.Error()}})
	}
	prune, err := PruneBundle(data, roots)
	if err != nil {
		return Report(out, []Finding{{"ERR", "ca-os-bundle", err.Error()}})
	}
	inHash, outHash := contentSHA256(data), contentSHA256(prune.Out)
	findings := []Finding{{"INFO", "ca-os-bundle-input", fmt.Sprintf("%s: sha256 %s; %d certificates", *in, inHash, prune.Total)}}
	for _, root := range prune.Dropped {
		findings = append(findings, Finding{"INFO", "ca-os-bundle-drop", root.Subject + " (sha256 " + root.SHA256 + ")"})
	}
	kept := fmt.Sprintf("kept %d of %d certificates", prune.Total-len(prune.Dropped), prune.Total)
	if !*apply {
		if err := writeCandidate(*candidate, prune.Out); err != nil {
			return Report(out, append(findings, Finding{"ERR", "ca-os-bundle", err.Error()}))
		}
		return Report(out, append(findings, Finding{"OK", "ca-os-bundle-candidate", fmt.Sprintf("%s: sha256 %s; %s; apply with: just ca-os-bundle-apply %s %s", *candidate, outHash, kept, inHash, outHash)}))
	}
	if err := ApplyBundle(*in, *backup, *expectIn, *expectOut, roots); err != nil {
		return Report(out, append(findings, Finding{"ERR", "ca-os-bundle", err.Error()}))
	}
	return Report(out, append(findings, Finding{"OK", "ca-os-bundle-apply", fmt.Sprintf("%s replaced: sha256 %s; %s; the old bundle is at %s", *in, outHash, kept, *backup)}))
}

// writeCandidate creates path, which must not exist (so not the input, nor a
// link to it), with the candidate's bytes.
func writeCandidate(path string, data []byte) error {
	file, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o600)
	if err != nil {
		if errors.Is(err, os.ErrExist) {
			return fmt.Errorf("%s exists; the candidate goes to a new file", path)
		}
		return err
	}
	_, err = file.Write(data)
	if closeErr := file.Close(); err == nil {
		err = closeErr
	}
	return err
}
