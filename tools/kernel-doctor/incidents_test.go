package main

import (
	"encoding/json/v2"
	"testing"
)

func recordBytes(t *testing.T) []byte {
	t.Helper()
	data, err := buildSource.ReadFile("incidents/cve-2026-98432.json")
	if err != nil {
		t.Fatalf("the shipped record must be embedded: %v", err)
	}
	return data
}

// The shipped record must parse. If it does not, every finding degrades to
// kernel-policy and this test says why.
func TestParseIncidentAcceptsTheShippedRecord(t *testing.T) {
	incident, err := ParseIncident(recordBytes(t))
	if err != nil {
		t.Fatalf("the shipped record must parse: %v", err)
	}
	if incident.ID != "cve-2026-98432" || incident.CVE != "CVE-2026-98432" {
		t.Errorf("unexpected identity: %+v", incident)
	}
	if len(incident.Branches) != 7 {
		t.Errorf("expected 7 reviewed branches, got %d", len(incident.Branches))
	}
	if incident.FixedInMainline != "7.3.0" {
		t.Errorf("FixedInMainline = %q, want 7.3.0", incident.FixedInMainline)
	}
	for _, floor := range incident.Branches {
		if floor.Branch == "6.6" && floor.Fixed != "6.6.159" {
			t.Errorf("6.6 floor = %q, want 6.6.159", floor.Fixed)
		}
	}
}

// A record the tool only half-understands would silently weaken every later
// finding, so anything unclear must be rejected outright.
func TestParseIncidentRejectsMalformedRecords(t *testing.T) {
	observations := func() []any {
		return []any{map[string]any{
			"label":      "nvd-cvss",
			"value":      "9.8",
			"observedAt": "2026-10-29",
			"source":     "https://osv.dev/vulnerability/CVE-2026-98432",
		}}
	}
	cases := []struct {
		name   string
		mutate func(map[string]any)
	}{
		{"unknown member", func(m map[string]any) { m["surprise"] = true }},
		{"wrong type", func(m map[string]any) { m["type"] = "something-else" }},
		{"bad cve id", func(m map[string]any) { m["cve"] = "CVE-2026" }},
		{"non-https source", func(m map[string]any) { m["source"] = "http://osv.dev/x" }},
		{"source with credentials", func(m map[string]any) { m["source"] = "https://u:p@osv.dev/x" }},
		{"source with a port", func(m map[string]any) { m["source"] = "https://osv.dev:8443/x" }},
		{"review-after before reviewed-at", func(m map[string]any) { m["reviewAfter"] = "2026-01-01" }},
		{"review-after equal to reviewed-at", func(m map[string]any) { m["reviewAfter"] = "2026-10-29" }},
		{"review date not a date", func(m map[string]any) { m["reviewedAt"] = "29/10/2026" }},
		{"no branches", func(m map[string]any) { m["branches"] = []any{} }},
		{"duplicate branch", func(m map[string]any) {
			m["branches"] = []any{
				map[string]any{"branch": "6.6", "fixed": "6.6.159"},
				map[string]any{"branch": "6.6", "fixed": "6.6.160"},
			}
		}},
		{"floor on the wrong branch", func(m map[string]any) {
			m["branches"] = []any{map[string]any{"branch": "6.6", "fixed": "6.12.113"}}
		}},
		{"floor is not a release", func(m map[string]any) {
			m["branches"] = []any{map[string]any{"branch": "6.6", "fixed": "6.6"}}
		}},
		{"branch is not major.minor", func(m map[string]any) {
			m["branches"] = []any{map[string]any{"branch": "6", "fixed": "6.1.190"}}
		}},
		{"mainline is not a release", func(m map[string]any) { m["fixedInMainline"] = "7.3" }},
		{"no advice", func(m map[string]any) { m["advice"] = []any{} }},
		{"blank advice", func(m map[string]any) { m["advice"] = []any{"   "} }},
		{"no observations", func(m map[string]any) { m["observations"] = []any{} }},
		{"observation without a real date", func(m map[string]any) {
			list := observations()
			list[0].(map[string]any)["observedAt"] = "later"
			m["observations"] = list
		}},
		{"duplicate observation label", func(m map[string]any) {
			list := observations()
			m["observations"] = append(list, list[0].(map[string]any))
		}},
		{"sysctl without a note", func(m map[string]any) {
			m["sysctls"] = []any{map[string]any{"path": "net.ipv4.tcp_migrate_req", "note": ""}}
		}},
		{"sysctl path is not dotted", func(m map[string]any) {
			m["sysctls"] = []any{map[string]any{"path": "tcp_migrate_req", "note": "x"}}
		}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			var record map[string]any
			if err := json.Unmarshal(recordBytes(t), &record); err != nil {
				t.Fatalf("baseline record must decode: %v", err)
			}
			tc.mutate(record)
			data, err := json.Marshal(record)
			if err != nil {
				t.Fatalf("re-encode: %v", err)
			}
			if _, err := ParseIncident(data); err == nil {
				t.Fatalf("ParseIncident accepted a malformed record: %s", data)
			}
		})
	}
}

func TestIncidentFloorLookup(t *testing.T) {
	incident := mustIncident(t)
	if floor, ok := incident.floorFor("6.6"); !ok || floor != "6.6.159" {
		t.Errorf("floorFor(6.6) = %q,%v; want 6.6.159,true", floor, ok)
	}
	if _, ok := incident.floorFor("6.17"); ok {
		t.Error("floorFor(6.17) must not find a reviewed floor")
	}
}
