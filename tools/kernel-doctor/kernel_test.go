package main

import (
	"strings"
	"testing"
)

// mustIncident returns the one embedded record, failing loudly rather than
// letting a load error masquerade as a wrong comparison.
func mustIncident(t *testing.T) Incident {
	t.Helper()
	if incidentError != nil {
		t.Fatalf("embedded incident data must load: %v", incidentError)
	}
	if len(incidents) != 1 {
		t.Fatalf("expected 1 embedded record, got %d", len(incidents))
	}
	return incidents[0]
}

// The exact table the independent plan review required before implementation.
// Every row is a case where comparing naively would have produced a wrong
// answer; unverified is the safe failure and is never counted as fixed.
func TestAssessMatchesTheReviewedAcceptanceTable(t *testing.T) {
	incident := mustIncident(t)
	cases := []struct{ input, want string }{
		{"6.6.150", BelowFloor},
		{"6.6.159", AtOrAboveFloor},
		{"7.3.0", AtOrAboveFloor},
		{"6.6.87.2-microsoft-standard-WSL2", UnverifiedVendor},
		{"6.8.0-45-generic", UnverifiedVendor},
		{"6.1.0-28-amd64", UnverifiedVendor},
		{"6.6.159+", UnverifiedFormat},
		{"6.6.159.2", UnverifiedFormat},
		{"6.6.159garbage", UnverifiedFormat},
		{"7.3.0-rc1", UnverifiedFormat},
		{"4.19.999", UnverifiedBranch},
		{"7.3", UnverifiedFormat},
		{"", UnverifiedFormat},
		// Whitespace is not a version.
		{"  ", UnverifiedFormat},
		// Every other reviewed branch, floor and floor-minus-one.
		{"5.10.272", AtOrAboveFloor},
		{"5.10.271", BelowFloor},
		{"5.15.223", AtOrAboveFloor},
		{"5.15.222", BelowFloor},
		{"6.1.190", AtOrAboveFloor},
		{"6.1.189", BelowFloor},
		{"6.12.113", AtOrAboveFloor},
		{"6.12.112", BelowFloor},
		{"6.18.56", AtOrAboveFloor},
		{"6.18.55", BelowFloor},
		{"7.2.10", AtOrAboveFloor},
		{"7.2.9", BelowFloor},
		// A clean form on a branch nobody reviewed.
		{"6.17.0", UnverifiedBranch},
		{"8.0.0", AtOrAboveFloor},
	}
	for _, tc := range cases {
		got := Assess(tc.input, incident)
		if got.Outcome != tc.want {
			t.Errorf("Assess(%q).Outcome = %q, want %q (reason: %s)", tc.input, got.Outcome, tc.want, got.Reason)
		}
	}
}

// No input may ever produce a claim about the running kernel: the tool
// compares a string and observes nothing about what is loaded. Only a build
// recorded under vendorBuilds says anything about the fix, and only that its
// commit is in the vendor's tag.
func TestAssessNeverAttestsTheRunningPatchState(t *testing.T) {
	incident := mustIncident(t)
	for _, input := range []string{"6.6.159", "6.6.150", "6.6.87.2-microsoft-standard-WSL2", "junk", "", recordedWSL} {
		got := Assess(input, incident)
		if got.PatchStatus != unverified {
			t.Errorf("Assess(%q) attested a patch state: %+v", input, got)
		}
		wantBackport := unverified
		if input == recordedWSL {
			wantBackport = fixCommitInVendorTag
		}
		if got.BackportState != wantBackport {
			t.Errorf("Assess(%q).BackportState = %q, want %q", input, got.BackportState, wantBackport)
		}
		if got.Reason == "" {
			t.Errorf("Assess(%q) gave no reason", input)
		}
	}
}

// recordedWSL is the one vendor build in the shipped record.
const recordedWSL = "6.18.58.1-microsoft-standard-WSL2"

// A build recorded under vendorBuilds, matched as the whole string, is the
// one vendor kernel the tool may report as carrying the fix (ADR-0065
// Decision 3). /proc returns the release with a trailing newline.
func TestAssessReportsARecordedVendorBuild(t *testing.T) {
	incident := mustIncident(t)
	for _, input := range []string{recordedWSL, recordedWSL + "\n"} {
		got := Assess(input, incident)
		if got.Outcome != ReviewedVendorBuild {
			t.Fatalf("Assess(%q).Outcome = %q, want %q (reason: %s)", input, got.Outcome, ReviewedVendorBuild, got.Reason)
		}
		for _, part := range []string{"Microsoft WSL2 kernel", "a47406c769f7", "custom kernel"} {
			if !strings.Contains(got.Reason, part) {
				t.Errorf("Assess(%q).Reason lacks %q: %s", input, part, got.Reason)
			}
		}
	}
}

// Anything but the exact recorded string is an ordinary vendor kernel again:
// a near miss must never borrow the recorded build's result.
func TestANearMissOfARecordedBuildStaysUnverified(t *testing.T) {
	incident := mustIncident(t)
	cases := []struct{ input, want string }{
		{"6.18.58.2-microsoft-standard-WSL2", UnverifiedVendor},
		{"6.18.58.1-microsoft-standard-WSL2-custom", UnverifiedVendor},
		{"6.18.58.1-Microsoft-Standard-WSL2", UnverifiedVendor},
		{"6.18.58.1-microsoft-standard-WSL", UnverifiedVendor},
		{"6.18.58.1-microsoft-standard-WSL2+", UnverifiedFormat},
		{"6.18.58.1", UnverifiedFormat},
	}
	for _, tc := range cases {
		if got := Assess(tc.input, incident); got.Outcome != tc.want {
			t.Errorf("Assess(%q).Outcome = %q, want %q", tc.input, got.Outcome, tc.want)
		}
	}
}

// A below-floor result must name the floor it was compared against, or the
// warning is not actionable.
func TestAssessNamesTheFloorItCompared(t *testing.T) {
	incident := mustIncident(t)
	got := Assess("6.6.150", incident)
	if got.FixFloor != "6.6.159" {
		t.Errorf("FixFloor = %q, want 6.6.159", got.FixFloor)
	}
	if got.Branch != "6.6" {
		t.Errorf("Branch = %q, want 6.6", got.Branch)
	}
	if got.Prefix != "6.6.150" {
		t.Errorf("Prefix = %q, want 6.6.150", got.Prefix)
	}
}

// A vendor kernel still shows its numeric prefix for a human to read, even
// though it must not be compared.
func TestAssessKeepsTheNumericPrefixForDisplay(t *testing.T) {
	incident := mustIncident(t)
	if got := Assess("6.6.87.2-microsoft-standard-WSL2", incident); got.Prefix != "6.6.87.2" {
		t.Errorf("Prefix = %q, want 6.6.87.2", got.Prefix)
	}
	if got := Assess("junk", incident); got.Prefix != "" {
		t.Errorf("Prefix = %q, want empty for a non-numeric string", got.Prefix)
	}
}

func TestBranchHelpers(t *testing.T) {
	if !branchAtLeast("7.3", "7.3") {
		t.Error("7.3 must be at least 7.3")
	}
	if branchAtLeast("7.2", "7.3") {
		t.Error("7.2 must not be at least 7.3")
	}
	if branchAtLeast("6.99", "7.3") {
		t.Error("6.99 must not be at least 7.3")
	}
	if _, ok := branchParts("6"); ok {
		t.Error("a single component is not a branch")
	}
	if _, ok := versionParts("6.6"); ok {
		t.Error("6.6 is not a three-component release")
	}
}

// A record never overrides a numeric comparison: Assess itself only consults
// vendorBuilds for a vendor-shaped string, whatever a record holds. ParseIncident
// rejects such a record too; this pins the rule where the lookup happens.
func TestARecordNeverOverridesANumericComparison(t *testing.T) {
	incident := mustIncident(t)
	incident.VendorBuilds = append(incident.VendorBuilds, VendorBuild{
		Release: "6.6.150", Vendor: "planted", FixCommit: incident.VendorBuilds[0].FixCommit,
		TagCommit: incident.VendorBuilds[0].TagCommit, Evidence: incident.VendorBuilds[0].Evidence,
	})
	if got := Assess("6.6.150", incident); got.Outcome != BelowFloor {
		t.Errorf("Assess(6.6.150).Outcome = %q, want %q", got.Outcome, BelowFloor)
	}
}
