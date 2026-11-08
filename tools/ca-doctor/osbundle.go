package main

import (
	"bytes"
	"crypto/sha256"
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
// candidate run (no root) writes the new bundle beside, and an apply run (as
// root) installs exactly those bytes after a durable backup.

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
// line, and the text dump before its PEM block, and they go with it; so does
// a `### group` line that the removal leaves without an entry. Each root must
// be in the bundle exactly once, and every block must parse.
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
		if lineText(lines[begin]) != pemBegin {
			continue
		}
		end := begin
		for end < len(lines) && lineText(lines[end]) != pemEnd {
			end++
		}
		if end == len(lines) {
			return BundlePrune{}, fmt.Errorf("unterminated certificate block at line %d", begin+1)
		}
		block, _ := pem.Decode(bytes.Join(lines[begin:end+1], nil))
		if block == nil || block.Type != "CERTIFICATE" {
			return BundlePrune{}, fmt.Errorf("certificate block at line %d does not parse", begin+1)
		}
		result.Total++
		sum := sha256.Sum256(block.Bytes)
		fingerprint := hex.EncodeToString(sum[:])
		if root, ok := wanted[fingerprint]; ok {
			found[fingerprint]++
			result.Dropped = append(result.Dropped, root)
			for line := entryStart(lines, previousEnd, begin, end); line <= end; line++ {
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

func blank(line []byte) bool { return lineText(line) == "" }

// entryStart is the first line that goes with the block at begin..end: the
// block itself in a plain PEM file, or its OpenBSD entry, with the entry's
// `### group` line when no entry of that group follows.
func entryStart(lines [][]byte, previousEnd, begin, end int) int {
	start := begin
	for line := begin - 1; line >= previousEnd; line-- {
		if strings.HasPrefix(lineText(lines[line]), "=== ") {
			start = line
			break
		}
	}
	if start == begin {
		return begin
	}
	if start-1 >= previousEnd && blank(lines[start-1]) {
		start--
	}
	group := start - 1
	if group < previousEnd || !strings.HasPrefix(lineText(lines[group]), "### ") {
		return start
	}
	next := end + 1
	for next < len(lines) && blank(lines[next]) {
		next++
	}
	if next < len(lines) && !strings.HasPrefix(lineText(lines[next]), "### ") {
		return start // another entry of the group follows
	}
	if group-1 >= previousEnd && blank(lines[group-1]) {
		return group - 1
	}
	return group
}

func contentSHA256(data []byte) string {
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:])
}

// ApplyBundle replaces in with its prune, but only when in's SHA-256 is
// expectIn and the prune's is expectOut, the hashes a candidate run printed,
// and backup does not exist yet. The backup is written and synced, with its
// directory, before the new bundle is renamed over in.
func ApplyBundle(in, backup, expectIn, expectOut string, roots []UntrustedRoot) error {
	info, err := os.Lstat(in)
	if err != nil {
		return err
	}
	if !info.Mode().IsRegular() {
		return fmt.Errorf("%s is not a regular file", in)
	}
	data, err := os.ReadFile(in)
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
	if err := writeDurably(backup, data, info, os.O_WRONLY|os.O_CREATE|os.O_EXCL); err != nil {
		return fmt.Errorf("backup %s: %w", backup, err)
	}
	temporary, err := os.CreateTemp(filepath.Dir(in), ".ca-doctor-os-bundle-*")
	if err != nil {
		return err
	}
	name := temporary.Name()
	if err := fillDurably(temporary, prune.Out, info); err != nil {
		_ = os.Remove(name)
		return err
	}
	if err := os.Rename(name, in); err != nil {
		_ = os.Remove(name)
		return err
	}
	return syncDirectory(filepath.Dir(in))
}

// writeDurably creates path with data and like's mode (and owner, as root),
// and syncs the file and its directory.
func writeDurably(path string, data []byte, like os.FileInfo, flags int) error {
	file, err := os.OpenFile(path, flags, like.Mode().Perm())
	if err != nil {
		return err
	}
	if err := fillDurably(file, data, like); err != nil {
		return err
	}
	return syncDirectory(filepath.Dir(path))
}

func fillDurably(file *os.File, data []byte, like os.FileInfo) error {
	_, err := file.Write(data)
	if err == nil {
		err = file.Chmod(like.Mode().Perm())
	}
	if uid, gid, ok := fileOwner(like); err == nil && ok && os.Geteuid() == 0 {
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

func syncDirectory(dir string) error {
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

const osBundleUsage = "usage: ca-doctor os-bundle --source DIR --incident ID --in FILE (--out FILE | --apply --expect-sha256 HEX --expect-out-sha256 HEX --backup FILE)"

func runOSBundle(args []string, out io.Writer) int {
	flags := flag.NewFlagSet("os-bundle", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	source := flags.String("source", "tools/ca-doctor", "source directory for build freshness verification")
	incidentID := flags.String("incident", "", "incident whose untrusted roots to remove")
	in := flags.String("in", "", "the PEM bundle")
	candidate := flags.String("out", "", "write the candidate bundle here (no root needed)")
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
		if err := os.WriteFile(*candidate, prune.Out, 0o600); err != nil {
			return Report(out, append(findings, Finding{"ERR", "ca-os-bundle", err.Error()}))
		}
		return Report(out, append(findings, Finding{"OK", "ca-os-bundle-candidate", fmt.Sprintf("%s: sha256 %s; %s; apply with: just ca-os-bundle-apply %s %s", *candidate, outHash, kept, inHash, outHash)}))
	}
	if err := ApplyBundle(*in, *backup, *expectIn, *expectOut, roots); err != nil {
		return Report(out, append(findings, Finding{"ERR", "ca-os-bundle", err.Error()}))
	}
	return Report(out, append(findings, Finding{"OK", "ca-os-bundle-apply", fmt.Sprintf("%s replaced: sha256 %s; %s; the old bundle is at %s", *in, outHash, kept, *backup)}))
}
