package main

import (
	"encoding/json/v2"
	"errors"
	"fmt"
	"net"
	"net/url"
	"regexp"
	"strings"
	"time"
)

// VersionFloor is one reviewed upstream branch and its fix floor. The shape
// follows ca-doctor's VersionFloor: a branch name plus the minimum version
// that carries the fix.
type VersionFloor struct {
	Branch string `json:"branch"`
	Fixed  string `json:"fixed"`
}

// Sysctl is a kernel setting worth reporting as reachability evidence.
type Sysctl struct {
	Path string `json:"path"`
	Note string `json:"note"`
}

// Observation is a third-party number (CVSS, EPSS, KEV membership) with the
// day it was observed. Numbers without an observation day go stale silently.
type Observation struct {
	Label      string `json:"label"`
	Value      string `json:"value"`
	ObservedAt string `json:"observedAt"`
	Source     string `json:"source"`
}

// Incident is one reviewed, source-cited record. Everything the tool reports
// comes from here; nothing is fetched at run time.
type Incident struct {
	ID              string         `json:"id"`
	Type            string         `json:"type"`
	Title           string         `json:"title"`
	CVE             string         `json:"cve"`
	Source          string         `json:"source"`
	Record          string         `json:"record"`
	ReviewedAt      string         `json:"reviewedAt"`
	ReviewAfter     string         `json:"reviewAfter"`
	Branches        []VersionFloor `json:"branches"`
	FixedInMainline string         `json:"fixedInMainline"`
	Sysctls         []Sysctl       `json:"sysctls"`
	Observations    []Observation  `json:"observations"`
	Advice          []string       `json:"advice"`
	VendorBuilds    []VendorBuild  `json:"vendorBuilds"`
}

// VendorBuild is one vendor kernel build reviewed against this CVE: the fix
// commit the CVE record names (the same SHA) is an ancestor of the commit the
// vendor's release tag points at, and the fixed lines are present there.
// Evidence pins that tag commit, because a tag can move (ADR-0065 Decision 3).
// Only the exact release string matches; a near miss stays unverified.
type VendorBuild struct {
	Release    string `json:"release"`
	Vendor     string `json:"vendor"`
	FixCommit  string `json:"fixCommit"`
	Source     string `json:"source"`
	Evidence   string `json:"evidence"`
	ReviewedAt string `json:"reviewedAt"`
}

var (
	incidentID = regexp.MustCompile(`^[a-z0-9][a-z0-9-]{0,63}$`)
	cveForm    = regexp.MustCompile(`^CVE-[0-9]{4}-[0-9]{4,}$`)
	dnsHost    = regexp.MustCompile(`^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$`)
	sysctlPath = regexp.MustCompile(`^[a-z0-9_]+(?:\.[a-z0-9_]+)+$`)
	commitSHA  = regexp.MustCompile(`^[0-9a-f]{40}$`)
	// vendorRelease narrows vendorSuffix to printable release characters, so
	// a recorded release cannot carry a space or a control character.
	vendorRelease            = regexp.MustCompile(`^[0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?-[A-Za-z0-9._-]+$`)
	incidents, incidentError = loadIncidents()
)

// floorFor returns the reviewed fix floor for a major.minor branch.
func (i Incident) floorFor(branch string) (string, bool) {
	for _, candidate := range i.Branches {
		if candidate.Branch == branch {
			return candidate.Fixed, true
		}
	}
	return "", false
}

// atOrAboveMainline reports whether a version is on a branch at or above the
// reviewed mainline fix. Versions at or above it carry the fix by construction.
func (i Incident) atOrAboveMainline(parts [3]int) bool {
	fixed, ok := versionParts(i.FixedInMainline)
	if !ok {
		return false
	}
	return branchAtLeast(branchOf(parts), branchOf(fixed))
}

func publicHTTPS(raw string) bool {
	u, err := url.Parse(raw)
	return err == nil && u.Scheme == "https" && u.User == nil && u.RawQuery == "" &&
		u.Fragment == "" && u.Port() == "" && validHost(u.Hostname())
}

func validHost(host string) bool {
	return strings.Contains(host, ".") && dnsHost.MatchString(host) &&
		net.ParseIP(host) == nil && !strings.Contains(host, "..")
}

// ParseIncident rejects anything it does not fully understand: an unknown
// member, an overlapping or negative range, a non-https citation. A record
// the tool only half-reads would silently weaken every later finding.
func ParseIncident(data []byte) (Incident, error) {
	var incident Incident
	if err := json.Unmarshal(data, &incident, json.RejectUnknownMembers(true)); err != nil {
		return incident, fmt.Errorf("parse incident: %w", err)
	}
	if err := validateMeta(incident); err != nil {
		return incident, err
	}
	if err := validateBranches(incident); err != nil {
		return incident, err
	}
	if err := validateDetail(incident); err != nil {
		return incident, err
	}
	if err := validateVendorBuilds(incident); err != nil {
		return incident, err
	}
	return incident, nil
}

// validateVendorBuilds accepts only a vendor-shaped release on a reviewed
// branch: an upstream x.y.z release is compared against the floors instead,
// and a prerelease is not a vendor build.
func validateVendorBuilds(i Incident) error {
	if len(i.VendorBuilds) > 32 {
		return errors.New("incident allows at most 32 vendor builds")
	}
	seen := map[string]bool{}
	for _, build := range i.VendorBuilds {
		outcome, _ := incomparableReason(build.Release)
		if outcome != UnverifiedVendor || !vendorRelease.MatchString(build.Release) || seen[build.Release] {
			return errors.New("invalid/duplicate vendor build release")
		}
		// vendorRelease guarantees at least two dots before the first '-'.
		major, rest, _ := strings.Cut(build.Release, ".")
		minor, _, _ := strings.Cut(rest, ".")
		if _, reviewed := i.floorFor(major + "." + minor); !reviewed {
			return errors.New("vendor build must be on a reviewed branch")
		}
		vendor := strings.TrimSpace(build.Vendor)
		if vendor == "" || len(vendor) > 100 || !commitSHA.MatchString(build.FixCommit) ||
			!publicHTTPS(build.Source) || !publicHTTPS(build.Evidence) {
			return errors.New("invalid vendor build")
		}
		if _, err := time.Parse(time.DateOnly, build.ReviewedAt); err != nil {
			return errors.New("vendor build needs a review date")
		}
		seen[build.Release] = true
	}
	return nil
}

// vendorBuild returns the reviewed build whose release is exactly s.
func (i Incident) vendorBuild(s string) (VendorBuild, bool) {
	for _, build := range i.VendorBuilds {
		if build.Release == s {
			return build, true
		}
	}
	return VendorBuild{}, false
}

func validateMeta(i Incident) error {
	if !incidentID.MatchString(i.ID) || i.Type != "kernel-version-range" ||
		i.Title == "" || len(i.Title) > 300 || !cveForm.MatchString(i.CVE) ||
		!publicHTTPS(i.Source) || !publicHTTPS(i.Record) {
		return errors.New("invalid incident metadata")
	}
	reviewed, err := time.Parse(time.DateOnly, i.ReviewedAt)
	if err != nil {
		return fmt.Errorf("review date: %w", err)
	}
	after, err := time.Parse(time.DateOnly, i.ReviewAfter)
	if err != nil || !after.After(reviewed) {
		return errors.New("invalid review-after date")
	}
	return nil
}

func validateBranches(i Incident) error {
	if len(i.Branches) == 0 || len(i.Branches) > 32 {
		return errors.New("incident needs 1-32 branches")
	}
	seen := map[string]bool{}
	for _, floor := range i.Branches {
		if _, valid := branchParts(floor.Branch); !valid || seen[floor.Branch] {
			return errors.New("invalid/duplicate branch")
		}
		fixed, valid := versionParts(floor.Fixed)
		if !valid || branchOf(fixed) != floor.Branch {
			return errors.New("fix floor must be an x.y.z release on its own branch")
		}
		seen[floor.Branch] = true
	}
	if !cleanRelease.MatchString(i.FixedInMainline) {
		return errors.New("fixedInMainline must be an x.y.z release")
	}
	return nil
}

func validateDetail(i Incident) error {
	if len(i.Advice) == 0 || len(i.Advice) > 32 {
		return errors.New("incident needs 1-32 advice lines")
	}
	for _, advice := range i.Advice {
		if strings.TrimSpace(advice) == "" || len(advice) > 500 {
			return errors.New("invalid advice line")
		}
	}
	for _, sysctl := range i.Sysctls {
		if !sysctlPath.MatchString(sysctl.Path) || strings.TrimSpace(sysctl.Note) == "" {
			return errors.New("invalid sysctl entry")
		}
	}
	if len(i.Observations) == 0 {
		return errors.New("incident needs at least one dated observation")
	}
	seen := map[string]bool{}
	for _, o := range i.Observations {
		if o.Label == "" || seen[o.Label] || strings.TrimSpace(o.Value) == "" ||
			!publicHTTPS(o.Source) {
			return errors.New("invalid/duplicate observation")
		}
		if _, err := time.Parse(time.DateOnly, o.ObservedAt); err != nil {
			return errors.New("observation needs an observation date")
		}
		seen[o.Label] = true
	}
	return nil
}

func loadIncidents() ([]Incident, error) {
	entries, err := buildSource.ReadDir("incidents")
	if err != nil {
		return nil, fmt.Errorf("incident directory: %w", err)
	}
	var result []Incident
	seen := map[string]bool{}
	for _, entry := range entries {
		data, err := buildSource.ReadFile("incidents/" + entry.Name())
		if err != nil {
			return nil, fmt.Errorf("incident read: %w", err)
		}
		incident, err := ParseIncident(data)
		if err != nil {
			return nil, fmt.Errorf("incident %s: %w", entry.Name(), err)
		}
		if seen[incident.ID] {
			return nil, errors.New("duplicate incident id")
		}
		seen[incident.ID] = true
		result = append(result, incident)
	}
	return result, nil
}
