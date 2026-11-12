package main

import (
	"encoding/json/v2"
	"fmt"
	"strings"
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
		{"vendor build with an unknown member", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) { b["surprise"] = true })
		}},
		{"vendor build release in upstream form", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) { b["release"] = "6.18.58" })
		}},
		{"vendor build release is a prerelease", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) { b["release"] = "6.18.0-rc1" })
		}},
		{"vendor build release with a space", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) { b["release"] = "6.18.58.1-microsoft standard" })
		}},
		{"vendor build release with a control character", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) { b["release"] = "6.18.58.1-microsoft\tWSL2" })
		}},
		{"vendor build on a branch nobody reviewed", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) { b["release"] = "6.17.9.1-microsoft-standard-WSL2" })
		}},
		{"vendor build fix commit is short", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) { b["fixCommit"] = "a47406c769f7" })
		}},
		{"vendor build fix commit is upper case", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) { b["fixCommit"] = "A47406C769F72C070386985488F1C4D057DF86B2" })
		}},
		{"vendor build fix commit is not hex", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) { b["fixCommit"] = "z47406c769f72c070386985488f1c4d057df86b2" })
		}},
		{"vendor build source is not https", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) { b["source"] = "http://github.com/x" })
		}},
		{"vendor build evidence is not https", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) { b["evidence"] = "http://github.com/x" })
		}},
		{"vendor build without a vendor", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) { b["vendor"] = "  " })
		}},
		{"vendor build review date not a date", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) { b["reviewedAt"] = "13/11/2026" })
		}},
		{"duplicate vendor build", func(m map[string]any) {
			list := vendorBuild(func(map[string]any) {})
			m["vendorBuilds"] = append(list, vendorBuild(func(map[string]any) {})...)
		}},
		{"too many vendor builds", func(m map[string]any) {
			var list []any
			for n := range 33 {
				list = append(list, vendorBuild(func(b map[string]any) {
					b["release"] = fmt.Sprintf("6.18.58.%d-microsoft-standard-WSL2", n)
				})...)
			}
			m["vendorBuilds"] = list
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

// vendorBuild returns a one-entry vendorBuilds list, changed by mutate.
func vendorBuild(mutate func(map[string]any)) []any {
	build := map[string]any{
		"release":    "6.18.58.1-microsoft-standard-WSL2",
		"vendor":     "Microsoft WSL2 kernel",
		"fixCommit":  "a47406c769f72c070386985488f1c4d057df86b2",
		"source":     "https://github.com/microsoft/WSL2-Linux-Kernel/releases/tag/linux-msft-wsl-6.18.58.1",
		"evidence":   "https://github.com/microsoft/WSL2-Linux-Kernel/compare/a47406c769f72c070386985488f1c4d057df86b2...a989171929bed4ea681be8d77333845ce1c1732a",
		"reviewedAt": "2026-11-13",
	}
	mutate(build)
	return []any{build}
}

// The shipped record carries the reviewed WSL build, tied to the fix commit
// the CVE record names for 6.18 and to the tag's commit, not the movable tag.
func TestTheShippedRecordCarriesTheReviewedWSLBuild(t *testing.T) {
	incident := mustIncident(t)
	if len(incident.VendorBuilds) != 1 {
		t.Fatalf("expected 1 reviewed vendor build, got %d", len(incident.VendorBuilds))
	}
	build := incident.VendorBuilds[0]
	if build.Release != "6.18.58.1-microsoft-standard-WSL2" ||
		build.FixCommit != "a47406c769f72c070386985488f1c4d057df86b2" {
		t.Errorf("unexpected build: %+v", build)
	}
	if !strings.Contains(build.Evidence, "/compare/"+build.FixCommit+"...a989171929bed4ea681be8d77333845ce1c1732a") {
		t.Errorf("evidence must compare the fix commit with the tag's commit: %s", build.Evidence)
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
