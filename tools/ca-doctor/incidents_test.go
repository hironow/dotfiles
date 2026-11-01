package main

import (
	"strings"
	"testing"
	"time"
)

func TestIncidentManifestValidation(t *testing.T) {
	data, err := buildSource.ReadFile("incidents/emudhra-2026.json")
	if err != nil {
		t.Fatal(err)
	}
	for _, tc := range []struct{ name, old, new string }{
		{"HTTP source", "https://emudhra.we-have-a-problem.com/", "http://emudhra.we-have-a-problem.com/"},
		{"credentials", "https://emudhra.we-have-a-problem.com/", "https://user:password@emudhra.we-have-a-problem.com/"},
		{"unknown mode", "tls-endpoint-and-version", "arbitrary-shell"},
		{"invalid floor", "1.27.3", "1.27.3-rc.1"},
		{"two-part floor", "26.2.2", "26.2"},
		{"invalid date", "2026-11-20", "2026-10-01"},
		{"unknown field", "\"title\":", "\"unrecognized\":true, \"title\":"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			broken := strings.Replace(string(data), tc.old, tc.new, 1)
			if _, err := ParseIncident([]byte(broken)); err == nil {
				t.Fatal("invalid manifest accepted")
			}
		})
	}
	incident, err := ParseIncident(data)
	if err != nil {
		t.Fatal(err)
	}
	date := time.Date(2026, 11, 21, 0, 0, 0, 0, time.UTC)
	if got := IncidentFreshness(incident, date); got.Level != "WARN" {
		t.Fatal(got)
	}
}

func TestPolicyMissingAndUnsupportedBranchesNeverPass(t *testing.T) {
	incident := Incident{ID: "future", Floors: map[string][]VersionFloor{"tool": {{Branch: "3.1", Minimum: "3.1.9"}}}}
	for _, tc := range []struct{ v, level string }{{"3.1.8", "ERR"}, {"3.1.9", "OK"}, {"3.2.0", "WARN"}, {"4.0.0", "WARN"}} {
		if got := VersionEvidenceFor(incident, "tool", tc.v); got.Level != tc.level {
			t.Fatal(got)
		}
	}
}
