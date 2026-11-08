package main

import (
	"bytes"
	"crypto/sha256"
	"crypto/x509"
	"encoding/asn1"
	"encoding/hex"
	"encoding/pem"
	"errors"
	"flag"
	"fmt"
	"io"
	"io/fs"
	"math/big"
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

// certificateDER is the DER of a block that holds exactly one certificate.
func certificateDER(block []byte) ([]byte, error) {
	decoded, rest := pem.Decode(block)
	if decoded == nil || decoded.Type != "CERTIFICATE" || len(decoded.Headers) != 0 || len(bytes.TrimSpace(rest)) != 0 {
		return nil, errors.New("does not parse as one PEM certificate")
	}
	if err := certificateStructure(decoded.Bytes); err != nil {
		return nil, fmt.Errorf("not a certificate: %w", err)
	}
	return decoded.Bytes, nil
}

// certificateStructure checks der with Go's x509 parser, which reads every
// field (names and extensions included) but checks no signature. The parser
// refuses a negative serial number, which a root in macOS's bundle still
// has (EC-ACC); such a certificate is checked again as a copy whose serial
// is 1, so it passes only when everything else parses.
func certificateStructure(der []byte) error {
	// The parser does not refuse an element after the signature.
	if certificate, err := sequence(der); err != nil || len(certificate) != 3 {
		return errors.New("not tbsCertificate, signatureAlgorithm, signatureValue")
	}
	_, err := x509.ParseCertificate(der)
	if err == nil {
		return nil
	}
	positive, ok := withPositiveSerial(der)
	if !ok {
		return err
	}
	_, err = x509.ParseCertificate(positive)
	return err
}

// withPositiveSerial is der with its serial number replaced by 1, when der is
// a certificate whose serial is negative.
func withPositiveSerial(der []byte) ([]byte, bool) {
	certificate, err := sequence(der)
	if err != nil || len(certificate) != 3 {
		return nil, false
	}
	tbs, err := sequence(certificate[0].FullBytes)
	if err != nil {
		return nil, false
	}
	field := 0
	if len(tbs) > 0 && tbs[0].Class == asn1.ClassContextSpecific && tbs[0].Tag == 0 {
		field++ // version
	}
	if len(tbs) <= field {
		return nil, false
	}
	var serial *big.Int
	if rest, err := asn1.Unmarshal(tbs[field].FullBytes, &serial); err != nil || len(rest) != 0 || serial.Sign() >= 0 {
		return nil, false
	}
	tbs[field] = asn1.RawValue{FullBytes: []byte{0x02, 0x01, 0x01}}
	rebuiltTBS, err := encodeSequence(tbs)
	if err != nil {
		return nil, false
	}
	certificate[0] = asn1.RawValue{FullBytes: rebuiltTBS}
	rebuilt, err := encodeSequence(certificate)
	return rebuilt, err == nil
}

// sequence is the elements of the DER SEQUENCE der, which must be all of der.
func sequence(der []byte) ([]asn1.RawValue, error) {
	var outer asn1.RawValue
	rest, err := asn1.Unmarshal(der, &outer)
	if err != nil {
		return nil, err
	}
	if len(rest) != 0 || outer.Class != asn1.ClassUniversal || outer.Tag != asn1.TagSequence || !outer.IsCompound {
		return nil, errors.New("not one SEQUENCE")
	}
	var elements []asn1.RawValue
	for content := outer.Bytes; len(content) > 0; {
		var element asn1.RawValue
		if content, err = asn1.Unmarshal(content, &element); err != nil {
			return nil, err
		}
		elements = append(elements, element)
	}
	return elements, nil
}

func encodeSequence(elements []asn1.RawValue) ([]byte, error) {
	var content []byte
	for _, element := range elements {
		content = append(content, element.FullBytes...)
	}
	return asn1.Marshal(asn1.RawValue{Class: asn1.ClassUniversal, Tag: asn1.TagSequence, IsCompound: true, Bytes: content})
}

func blank(line []byte) bool { return lineText(line) == "" }

// entryStart is the first line that goes with the block starting at begin:
// its OpenBSD entry (the `===` line, the text dump, and the blank line before
// `===`), or, in any other layout, the block alone. A `### group` line ends
// the search, so it always stays.
func entryStart(lines [][]byte, previousEnd, begin int) int {
	for line := begin - 1; line >= previousEnd; line-- {
		if strings.HasPrefix(lineText(lines[line]), "### ") {
			return begin
		}
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
	CreateTemp(dir, pattern string) (bundleFile, error)
	Link(from, to string) error
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
func (osFiles) Link(from, to string) error             { return os.Link(from, to) }
func (osFiles) Remove(path string) error               { return os.Remove(path) }
func (osFiles) IsRoot() bool                           { return os.Geteuid() == 0 }

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
// and backup does not exist yet. The backup is written under a temporary
// name, synced, published by a hard link (which never replaces a file), and
// its directory synced, before the new bundle is renamed over in; so the
// backup's name only ever holds a complete copy.
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
	if _, err := files.Lstat(backup); err == nil {
		return fmt.Errorf("backup %s exists; choose a new path", backup)
	} else if !errors.Is(err, fs.ErrNotExist) {
		return fmt.Errorf("backup %s: %w", backup, err)
	}
	if err := publishBackup(files, backup, data, info); err != nil {
		return err
	}
	temporary, err := files.CreateTemp(filepath.Dir(in), ".ca-doctor-os-bundle-*")
	if err != nil {
		return err
	}
	if err := fill(files, temporary, prune.Out, info); err != nil {
		return errors.Join(err, removeTemporary(files, temporary.Name()))
	}
	if err := files.Rename(temporary.Name(), in); err != nil {
		return errors.Join(err, removeTemporary(files, temporary.Name()))
	}
	if err := files.SyncDir(filepath.Dir(in)); err != nil {
		return fmt.Errorf("%s was replaced, but syncing its directory failed, so a crash may undo it: %w", in, err)
	}
	return nil
}

// publishBackup writes data to backup's directory under a temporary name,
// syncs it, links it to backup, removes the temporary name, and syncs the
// directory.
func publishBackup(files bundleFiles, backup string, data []byte, like os.FileInfo) error {
	dir := filepath.Dir(backup)
	temporary, err := files.CreateTemp(dir, ".ca-doctor-os-bundle-backup-*")
	if err != nil {
		return fmt.Errorf("backup %s: %w", backup, err)
	}
	if err := fill(files, temporary, data, like); err != nil {
		return errors.Join(fmt.Errorf("backup %s: %w", backup, err), removeTemporary(files, temporary.Name()))
	}
	if err := files.Link(temporary.Name(), backup); err != nil {
		return errors.Join(fmt.Errorf("backup %s: %w", backup, err), removeTemporary(files, temporary.Name()))
	}
	if err := files.Remove(temporary.Name()); err != nil {
		return fmt.Errorf("backup %s is complete, but the temporary file %s is left: %w", backup, temporary.Name(), err)
	}
	return files.SyncDir(dir)
}

func removeTemporary(files bundleFiles, name string) error {
	if err := files.Remove(name); err != nil {
		return fmt.Errorf("the temporary file %s is left: %w", name, err)
	}
	return nil
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
