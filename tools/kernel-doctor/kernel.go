package main

import (
	"regexp"
	"strconv"
	"strings"
)

// Outcomes of comparing a reported kernel version against the reviewed
// upstream fix floors. These are evidence labels, never a vulnerability
// verdict: no version string can show whether a vendor backported the fix, and
// nothing here observes a running kernel's patch state.
const (
	// BelowFloor: a clean upstream release, on a reviewed branch, below that
	// branch's reviewed fix floor.
	BelowFloor = "below-reviewed-fix-floor"
	// AtOrAboveFloor: a clean upstream release, on a reviewed branch (or a
	// branch at/above the reviewed mainline fix), at or above the floor.
	AtOrAboveFloor = "at-or-above-reviewed-fix-floor"
	// UnverifiedFormat: not a clean upstream x.y.z release string.
	UnverifiedFormat = "unverified-version"
	// UnverifiedVendor: a vendor/distro kernel, where the numeric components
	// are the vendor's own ABI revision, not the upstream patch level — so the
	// comparison would be wrong in both directions.
	UnverifiedVendor = "unverified-vendor"
	// UnverifiedBranch: clean upstream form, but that branch was not reviewed.
	UnverifiedBranch = "unverified-branch"
)

// A kernel version string cannot attest either of these.
const (
	unverified = "unverified"
	// The fields below are always unverified; keeping them explicit is what
	// stops a comparison from being read as a clearance (cf. brotli-doctor's
	// RuntimeReview).
)

var (
	// cleanRelease is the only form safe to compare. The whole string must
	// match: taking a leading prefix and discarding the rest would turn
	// `6.6.159+`, `6.6.159.2` and `6.6.159garbage` all into "6.6.159 or later".
	cleanRelease = regexp.MustCompile(`^[0-9]+\.[0-9]+\.[0-9]+$`)
	leadingNums  = regexp.MustCompile(`^[0-9]+(?:\.[0-9]+)*`)
	// vendorSuffix: distro/vendor shapes. Ubuntu `6.8.0-45-generic`, Debian
	// `6.1.0-28-amd64`, WSL `6.6.87.2-microsoft-standard-WSL2`, RHEL
	// `5.14.0-427.40.1.el9_4.x86_64`.
	vendorSuffix = regexp.MustCompile(`^[0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?-[^+]+$`)
	prerelease   = regexp.MustCompile(`^(rc|alpha|beta|pre|git)`)
	branchForm   = regexp.MustCompile(`^[0-9]+\.[0-9]+$`)
)

// Assessment is what a single reported kernel version yields.
type Assessment struct {
	Raw      string `json:"raw"`
	Prefix   string `json:"prefix,omitempty"`
	Outcome  string `json:"outcome"`
	Branch   string `json:"branch,omitempty"`
	FixFloor string `json:"fixed_floor,omitempty"`
	Reason   string `json:"reason"`
	// Always unverified, deliberately.
	PatchStatus   string `json:"patch_status"`
	BackportState string `json:"backport_state"`
}

// Assess compares a reported kernel version against the reviewed floors.
//
// It only compares when the whole string is a clean upstream release AND its
// major.minor is a reviewed branch (or at/above the reviewed mainline fix).
// Everything else is reported as unverified with a reason. Refusing to compare
// is the safe failure: an unverified result is never counted as fixed.
func Assess(raw string, inc Incident) Assessment {
	a := Assessment{Raw: raw, PatchStatus: unverified, BackportState: unverified}
	trimmed := strings.TrimSpace(raw)
	a.Prefix = leadingNums.FindString(trimmed)
	if trimmed == "" {
		a.Outcome = UnverifiedFormat
		a.Reason = "no kernel version available; nothing compared"
		return a
	}
	if !cleanRelease.MatchString(trimmed) {
		a.Outcome, a.Reason = incomparableReason(trimmed)
		return a
	}
	parts, ok := versionParts(trimmed)
	if !ok {
		a.Outcome = UnverifiedFormat
		a.Reason = "unparseable version; nothing compared"
		return a
	}
	a.Branch = branchOf(parts)
	if floor, found := inc.floorFor(a.Branch); found {
		a.FixFloor = floor
		a.Outcome = compareToFloor(parts, floor)
		a.Reason = "compared as a clean upstream release on a reviewed branch; vendor backports and the running patch state stay unverified"
		return a
	}
	if inc.atOrAboveMainline(parts) {
		a.FixFloor = inc.FixedInMainline
		a.Outcome = AtOrAboveFloor
		a.Reason = "at or above the reviewed mainline fix; vendor backports and the running patch state stay unverified"
		return a
	}
	a.Outcome = UnverifiedBranch
	a.Reason = "clean upstream form, but this branch is not in the reviewed set; read the reviewed floors and the branch's own stable tree or vendor advisory"
	return a
}

// incomparableReason separates a vendor kernel from a malformed string. A
// prerelease suffix (`-rc1`) is not a vendor kernel.
func incomparableReason(s string) (string, string) {
	if strings.Contains(s, "-") && vendorSuffix.MatchString(s) {
		if suffix := s[strings.Index(s, "-")+1:]; !prerelease.MatchString(suffix) {
			return UnverifiedVendor, "vendor/distro kernel: the numeric components are the vendor's own ABI revision, not upstream patch levels, and a backported fix is invisible here; use the vendor's advisory for this package"
		}
	}
	return UnverifiedFormat, "not a clean upstream x.y.z release; refusing to compare a partly-numeric string"
}

func branchOf(parts [3]int) string {
	return strconv.Itoa(parts[0]) + "." + strconv.Itoa(parts[1])
}

// compareToFloor is 0 only for the exact floor; both operands are x.y.z.
func compareToFloor(parts [3]int, floor string) string {
	f, ok := versionParts(floor)
	if !ok {
		return UnverifiedFormat
	}
	for i := range parts {
		if parts[i] < f[i] {
			return BelowFloor
		}
		if parts[i] > f[i] {
			return AtOrAboveFloor
		}
	}
	return AtOrAboveFloor
}

func versionParts(s string) ([3]int, bool) {
	var v [3]int
	if !cleanRelease.MatchString(s) {
		return v, false
	}
	for i, p := range strings.Split(s, ".") {
		n, err := strconv.Atoi(p)
		if err != nil {
			return v, false
		}
		v[i] = n
	}
	return v, true
}

// branchAtLeast compares a major.minor branch against another.
func branchAtLeast(branch, other string) bool {
	b, okB := branchParts(branch)
	o, okO := branchParts(other)
	if !okB || !okO {
		return false
	}
	if b[0] != o[0] {
		return b[0] > o[0]
	}
	return b[1] >= o[1]
}

func branchParts(s string) ([2]int, bool) {
	var v [2]int
	if !branchForm.MatchString(s) {
		return v, false
	}
	for i, p := range strings.Split(s, ".") {
		n, err := strconv.Atoi(p)
		if err != nil {
			return v, false
		}
		v[i] = n
	}
	return v, true
}
