package main

import "testing"

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

// No input may ever produce a patch-state claim: the tool compares a string
// against reviewed floors and observes nothing about the running kernel.
func TestAssessAlwaysLeavesPatchStateUnverified(t *testing.T) {
	incident := mustIncident(t)
	for _, input := range []string{"6.6.159", "6.6.150", "6.6.87.2-microsoft-standard-WSL2", "junk", ""} {
		got := Assess(input, incident)
		if got.PatchStatus != unverified || got.BackportState != unverified {
			t.Errorf("Assess(%q) attested a patch state: %+v", input, got)
		}
		if got.Reason == "" {
			t.Errorf("Assess(%q) gave no reason", input)
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
