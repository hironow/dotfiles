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
			onlyBranches(m, branch("6.6", "6.6.159"), branch("6.6", "6.6.160"))
		}},
		{"floor on the wrong branch", func(m map[string]any) {
			onlyBranches(m, branch("6.6", "6.12.113"))
		}},
		{"floor is not a release", func(m map[string]any) {
			onlyBranches(m, branch("6.6", "6.6"))
		}},
		{"branch is not major.minor", func(m map[string]any) {
			onlyBranches(m, branch("6", "6.1.190"))
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
			// an unreviewed branch has no fixCommit, so an empty one must not
			// pass as equal to it
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) {
				b["release"] = "6.17.9.1-microsoft-standard-WSL2"
				pairCommits(b, "", wslTagCommit)
			})
		}},
		{"vendor build fix commit is short", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) { pairCommits(b, "a47406c769f7", wslTagCommit) })
		}},
		{"vendor build fix commit is upper case", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) {
				pairCommits(b, "A47406C769F72C070386985488F1C4D057DF86B2", wslTagCommit)
			})
		}},
		{"vendor build fix commit is not hex", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) {
				pairCommits(b, "z47406c769f72c070386985488f1c4d057df86b2", wslTagCommit)
			})
		}},
		{"vendor build source is not https", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) {
				b["source"] = "http://github.com/microsoft/WSL2-Linux-Kernel/releases/tag/linux-msft-wsl-6.18.58.1"
			})
		}},
		{"vendor build source has a query", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) { b["source"] = b["source"].(string) + "?x" })
		}},
		{"vendor build source has a fragment", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) { b["source"] = b["source"].(string) + "#x" })
		}},
		{"vendor build evidence is not https", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) { b["evidence"] = "http://github.com/x" })
		}},
		{"vendor build without a vendor", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) { b["vendor"] = "  " })
		}},
		{"vendor build vendor name is too long", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) { b["vendor"] = strings.Repeat("v", 101) })
		}},
		{"vendor build review date not a date", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) { b["reviewedAt"] = "13/11/2026" })
		}},
		{"branch fix commit is missing", func(m map[string]any) {
			branches := m["branches"].([]any)
			delete(branches[0].(map[string]any), "fixCommit")
		}},
		{"branch fix commit is short", func(m map[string]any) {
			branches := m["branches"].([]any)
			branches[0].(map[string]any)["fixCommit"] = "b3b027ef0cd3"
		}},
		{"vendor build fix commit is not the one the CVE names for its branch", func(m map[string]any) {
			// a real SHA, but the 6.12 one: "the same SHA" is checked, not trusted
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) {
				pairCommits(b, "11a03ce3c4a62d84c10ccdfe47f8075006498568", wslTagCommit)
			})
		}},
		{"vendor build tag commit is missing", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) {
				pairCommits(b, wslFixCommit, "")
				delete(b, "tagCommit")
			})
		}},
		{"vendor build tag commit is short", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) { pairCommits(b, wslFixCommit, "a989171929be") })
		}},
		{"vendor build tag commit is a tag name", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) { pairCommits(b, wslFixCommit, "linux-msft-wsl-6.18.58.1") })
		}},
		{"vendor build tag commit is the fix commit", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) { pairCommits(b, wslFixCommit, wslFixCommit) })
		}},
		{"vendor build source is not a release tag page", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) { b["source"] = "https://github.com/microsoft/WSL2-Linux-Kernel" })
		}},
		{"vendor build source is another page of the repository", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) {
				b["source"] = "https://github.com/microsoft/WSL2-Linux-Kernel/tree/linux-msft-wsl-6.18.58.1/net"
			})
		}},
		{"vendor build source has a segment after the tag", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) { b["source"] = b["source"].(string) + "/x" })
		}},
		{"vendor build source has no tag name", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) {
				b["source"] = "https://github.com/microsoft/WSL2-Linux-Kernel/releases/tag/"
			})
		}},
		{"vendor build source is not under releases", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) {
				b["source"] = "https://github.com/microsoft/WSL2-Linux-Kernel/x/tag/linux-msft-wsl-6.18.58.1"
			})
		}},
		{"vendor build source is a release download, not a tag page", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) {
				b["source"] = "https://github.com/microsoft/WSL2-Linux-Kernel/releases/download/linux-msft-wsl-6.18.58.1"
			})
		}},
		{"vendor build source has a dot-dot repository", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) {
				// net/url keeps dot segments, so this path still has six parts
				b["source"] = "https://github.com/microsoft/../releases/tag/linux-msft-wsl-6.18.58.1"
				b["evidence"] = "https://github.com/microsoft/../compare/" + wslFixCommit + "..." + wslTagCommit
			})
		}},
		{"vendor build source has a dot-dot owner", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) {
				// the evidence follows the source, so only the owner is wrong
				b["source"] = "https://github.com/../WSL2-Linux-Kernel/releases/tag/linux-msft-wsl-6.18.58.1"
				b["evidence"] = "https://github.com/../WSL2-Linux-Kernel/compare/" + wslFixCommit + "..." + wslTagCommit
			})
		}},
		{"vendor build source has an encoded path", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) {
				// decodes to the right repository, so only the encoding is wrong
				b["source"] = "https://github.com/microsoft%2FWSL2-Linux-Kernel/releases/tag/linux-msft-wsl-6.18.58.1"
			})
		}},
		{"evidence is on another repository", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) {
				b["evidence"] = "https://github.com/someone/WSL2-Linux-Kernel/compare/" + wslFixCommit + "..." + wslTagCommit
			})
		}},
		{"evidence is on another host", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) {
				b["evidence"] = "https://example.com/microsoft/WSL2-Linux-Kernel/compare/" + wslFixCommit + "..." + wslTagCommit
			})
		}},
		{"evidence has an extra path segment", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) {
				b["evidence"] = "https://github.com/microsoft/WSL2-Linux-Kernel/x/compare/" + wslFixCommit + "..." + wslTagCommit
			})
		}},
		{"evidence has an encoded slash", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) {
				b["evidence"] = "https://github.com/microsoft%2FWSL2-Linux-Kernel/compare/" + wslFixCommit + "..." + wslTagCommit
			})
		}},
		{"evidence has encoded dots", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) {
				b["evidence"] = "https://github.com/microsoft/WSL2-Linux-Kernel/compare/" + wslFixCommit + "%2E%2E%2E" + wslTagCommit
			})
		}},
		{"evidence has an empty query", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) { b["evidence"] = b["evidence"].(string) + "?" })
		}},
		{"evidence has an empty fragment", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) { b["evidence"] = b["evidence"].(string) + "#" })
		}},
		{"evidence compares against a tag name", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) {
				b["evidence"] = "https://github.com/microsoft/WSL2-Linux-Kernel/compare/a47406c769f72c070386985488f1c4d057df86b2...linux-msft-wsl-6.18.58.1"
			})
		}},
		{"evidence does not name the fix commit", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) {
				b["evidence"] = "https://github.com/microsoft/WSL2-Linux-Kernel/compare/v6.18.56...a989171929bed4ea681be8d77333845ce1c1732a"
			})
		}},
		{"evidence is not a compare of the two commits", func(m map[string]any) {
			m["vendorBuilds"] = vendorBuild(func(b map[string]any) {
				b["evidence"] = "https://github.com/microsoft/WSL2-Linux-Kernel/commit/a989171929bed4ea681be8d77333845ce1c1732a"
			})
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

const (
	wslFixCommit = "a47406c769f72c070386985488f1c4d057df86b2"
	wslTagCommit = "a989171929bed4ea681be8d77333845ce1c1732a"
)

// vendorBuild returns a one-entry vendorBuilds list, changed by mutate.
func vendorBuild(mutate func(map[string]any)) []any {
	build := map[string]any{
		"release":    "6.18.58.1-microsoft-standard-WSL2",
		"vendor":     "Microsoft WSL2 kernel",
		"fixCommit":  wslFixCommit,
		"tagCommit":  wslTagCommit,
		"source":     "https://github.com/microsoft/WSL2-Linux-Kernel/releases/tag/linux-msft-wsl-6.18.58.1",
		"evidence":   "https://github.com/microsoft/WSL2-Linux-Kernel/compare/" + wslFixCommit + "..." + wslTagCommit,
		"reviewedAt": "2026-11-13",
	}
	mutate(build)
	return []any{build}
}

// pairCommits sets both commits and the evidence that compares them, so a case
// that changes one commit fails on that commit's check, not first on a stale
// evidence URL.
func pairCommits(build map[string]any, fixCommit, tagCommit string) {
	build["fixCommit"] = fixCommit
	build["tagCommit"] = tagCommit
	build["evidence"] = "https://github.com/microsoft/WSL2-Linux-Kernel/compare/" + fixCommit + "..." + tagCommit
}

// branch returns a branches entry that carries the 6.6 fix commit, so a case
// fails on its floor or name, not first on a missing fixCommit.
func branch(name, fixed string) map[string]any {
	return map[string]any{"branch": name, "fixed": fixed, "fixCommit": "742f73df544e03744f2981c467d6542fe8172a2a"}
}

// onlyBranches replaces the branches and drops the vendor builds, which would
// otherwise fail first because their 6.18 branch is no longer reviewed.
func onlyBranches(record map[string]any, entries ...any) {
	record["branches"] = entries
	delete(record, "vendorBuilds")
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
	if build.TagCommit != "a989171929bed4ea681be8d77333845ce1c1732a" {
		t.Errorf("tagCommit = %q, want the commit the tag pointed at when reviewed", build.TagCommit)
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

// The rejection table only means something if its baselines are accepted: a
// helper whose output turned invalid would let every case built on it pass
// without testing anything.
func TestParseIncidentAcceptsTheRejectionBaselines(t *testing.T) {
	accept := func(name string, mutate func(map[string]any)) {
		t.Helper()
		var record map[string]any
		if err := json.Unmarshal(recordBytes(t), &record); err != nil {
			t.Fatalf("baseline record must decode: %v", err)
		}
		mutate(record)
		data, err := json.Marshal(record)
		if err != nil {
			t.Fatalf("re-encode: %v", err)
		}
		if _, err := ParseIncident(data); err != nil {
			t.Errorf("%s: ParseIncident rejected a valid record: %v", name, err)
		}
	}
	accept("the helper's default build", func(m map[string]any) {
		m["vendorBuilds"] = vendorBuild(func(map[string]any) {})
	})
	accept("pairCommits with the reviewed commits", func(m map[string]any) {
		m["vendorBuilds"] = vendorBuild(func(b map[string]any) { pairCommits(b, wslFixCommit, wslTagCommit) })
	})
	accept("exactly 32 distinct builds", func(m map[string]any) {
		var limit []any
		for n := range 32 {
			limit = append(limit, vendorBuild(func(b map[string]any) {
				b["release"] = fmt.Sprintf("6.18.58.%d-microsoft-standard-WSL2", n)
			})...)
		}
		m["vendorBuilds"] = limit
	})
	accept("one valid branch and no vendor builds", func(m map[string]any) {
		onlyBranches(m, branch("6.6", "6.6.159"))
	})
}

// Each reviewed branch records the fix commit the CVE record names for it
// (CVE-2026-98432.mbox, "fixed in <floor> with commit <sha>"), which is what a
// vendor build's fixCommit must equal.
func TestEveryReviewedBranchRecordsItsFixCommit(t *testing.T) {
	want := map[string]string{
		"5.10": "b3b027ef0cd322bfa839b9aaf5b27551eea54cf6",
		"5.15": "95a8c8fa9f27dce64c40c41c062de7728bf34ab5",
		"6.1":  "89b5b1eb7d633c33832b7ff2c02e19a144705036",
		"6.6":  "742f73df544e03744f2981c467d6542fe8172a2a",
		"6.12": "11a03ce3c4a62d84c10ccdfe47f8075006498568",
		"6.18": "a47406c769f72c070386985488f1c4d057df86b2",
		"7.2":  "26d4c36d318cffbbd160884a0e4cec0da4da4936",
	}
	incident := mustIncident(t)
	for _, floor := range incident.Branches {
		if floor.FixCommit != want[floor.Branch] {
			t.Errorf("branch %s fixCommit = %q, want %q", floor.Branch, floor.FixCommit, want[floor.Branch])
		}
	}
}
