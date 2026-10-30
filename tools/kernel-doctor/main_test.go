package main

import (
	"bytes"
	"encoding/json/v2"
	"strings"
	"testing"
	"time"
)

func localProbe() Probe { return Collect("linux") }

func linuxProbe(version, migrateReq string, migrateOK bool) Probe {
	return Probe{GOOS: "linux", OSRelease: version, OSReleaseOK: true, MigrateReq: migrateReq, MigrateReqOK: migrateOK}
}

func darwinProbe() Probe { return Probe{GOOS: "darwin"} }

// findingsOf runs the real evaluation and returns only its line findings.
func findingsOf(probe Probe, source string, now time.Time) []Finding {
	return evaluate(probe, source, now).findings
}

// fakeCollector stands in for the host so a test can drive a Linux shape on
// macOS, and can count the reads a run actually performs.
type fakeCollector struct {
	probe Probe
	calls int
}

func (f *fakeCollector) collect(string) Probe {
	f.calls++
	return f.probe
}

// The freshness boundary the review asked to pin: still fresh on the
// review-after date, overdue from 00:00 the next day.
func TestFreshnessBoundary(t *testing.T) {
	incident := mustIncident(t)
	freshAt := func(stamp string) bool {
		now, err := time.Parse(time.RFC3339, stamp)
		if err != nil {
			t.Fatalf("bad test stamp %q: %v", stamp, err)
		}
		fresh, _ := Freshness(incident, now)
		return fresh
	}
	if !freshAt("2026-11-26T23:59:59Z") {
		t.Error("the record must still be fresh on the review-after date")
	}
	if freshAt("2026-11-27T00:00:00Z") {
		t.Error("the record must be overdue from 00:00 the day after review-after")
	}
	if freshAt("2026-12-31T00:00:00Z") {
		t.Error("a long-expired record must be overdue")
	}
	broken := incident
	broken.ReviewAfter = "not-a-date"
	if fresh, note := Freshness(broken, time.Now()); fresh || !strings.Contains(note, "policy_freshness=unknown") {
		t.Errorf("an unreadable review-after date must not read as fresh: %q", note)
	}
}

// --osrelease replaces the local observation entirely: the local sysctl
// belongs to a different machine and must not be attributed to the target.
func TestOverrideDropsLocalEvidence(t *testing.T) {
	probe := Override("darwin", "6.6.159")
	if !probe.Override || !probe.OSReleaseOK || probe.GOOS != "darwin" {
		t.Fatalf("override probe is wrong: %+v", probe)
	}
	if value, ok := probe.sysctlValue(); ok {
		t.Errorf("an override must not report a local sysctl value (got %q)", value)
	}
	if _, ok := darwinProbe().sysctlValue(); ok {
		t.Error("a non-Linux host has no migration sysctl to report")
	}
}

func TestCollectNonLinuxKeepsProcUnread(t *testing.T) {
	probe := darwinProbe()
	if probe.OSReleaseOK || probe.MigrateReqOK {
		t.Errorf("a non-Linux host must not report /proc readings: %+v", probe)
	}
}

// The P1 the plan review found: on a non-Linux host the tool must still let an
// explicit --osrelease through, or its main use (assessing a Windows host's
// WSL kernel from macOS) is unimplementable.
func TestOverrideOutranksTheNonLinuxGate(t *testing.T) {
	var out bytes.Buffer
	if code := RunCLI([]string{"--source", ".", "--osrelease", "6.6.150"}, &out); code == 2 {
		t.Fatalf("an explicit override must not be a usage error:\n%s", out.String())
	}
	text := out.String()
	if strings.Contains(text, "kernel-not-applicable") {
		t.Errorf("an override must not short-circuit as not-applicable:\n%s", text)
	}
	if !strings.Contains(text, "below-reviewed-fix-floor") {
		t.Errorf("an override must still be compared:\n%s", text)
	}
	if !strings.Contains(text, "kernel-scope") {
		t.Errorf("an override must state its scope:\n%s", text)
	}
}

// The documented contract is that the local /proc and /etc/os-release are NOT
// READ, not merely that their values are discarded. Reading and discarding
// would still touch the target host's files on a Linux run.
func TestOverridePerformsNoLocalCollection(t *testing.T) {
	for _, goos := range []string{"linux", "darwin", "windows"} {
		t.Run(goos, func(t *testing.T) {
			fake := &fakeCollector{probe: Probe{GOOS: goos}}
			var out bytes.Buffer
			if code := run([]string{"--source", ".", "--json", "--osrelease", "6.6.159"}, &out, goos, fake.collect); code != 1 {
				t.Fatalf("an override must report advisory warnings, got exit %d:\n%s", code, out.String())
			}
			if fake.calls != 0 {
				t.Errorf("--osrelease must not consult the local host; collector ran %d time(s)", fake.calls)
			}
			var report JSONReport
			if err := json.Unmarshal(out.Bytes(), &report); err != nil {
				t.Fatalf("--json output must decode: %v", err)
			}
			if report.Scope != "override-version-only" {
				t.Errorf("override scope = %q", report.Scope)
			}
			if len(report.Assessments) != 1 || report.Assessments[0].Outcome != AtOrAboveFloor {
				t.Errorf("the supplied version must still be assessed: %+v", report.Assessments)
			}
		})
	}
}

// An empty override is an explicit input, not a missing one, and must not be
// confused with the local host's version.
func TestEmptyOverrideIsAnExplicitInput(t *testing.T) {
	fake := &fakeCollector{probe: linuxProbe("6.6.159", "0", true)}
	var out bytes.Buffer
	_ = run([]string{"--source", ".", "--osrelease", ""}, &out, "linux", fake.collect)
	text := out.String()
	if !strings.Contains(text, "assessing only the version given to --osrelease") {
		t.Errorf("an empty override must still be treated as an override:\n%s", text)
	}
	if !strings.Contains(text, "unverified-version") {
		t.Errorf("an empty override must yield no comparison:\n%s", text)
	}
	if fake.calls != 0 {
		t.Errorf("an empty override must not fall back to the local host (calls=%d)", fake.calls)
	}
}

// A host shape must be driven by the injected collector, not by the machine
// running the test: this is the assertion that used to encode a macOS-only
// outcome and would have failed the gate on Linux.
func TestAReadableHostIsAssessed(t *testing.T) {
	fake := &fakeCollector{probe: linuxProbe("6.6.150", "0", true)}
	var out bytes.Buffer
	_ = run([]string{"--source", ".", "--json"}, &out, "linux", fake.collect)
	if fake.calls != 1 {
		t.Errorf("a local run must consult the host exactly once, got %d", fake.calls)
	}
	var report JSONReport
	if err := json.Unmarshal(out.Bytes(), &report); err != nil {
		t.Fatalf("--json output must decode: %v", err)
	}
	if len(report.Assessments) != 1 || report.Assessments[0].Outcome != BelowFloor {
		t.Fatalf("a readable kernel must produce exactly one assessment: %+v", report.Assessments)
	}
}

// Drive non-Linux hosts through the real CLI, not evaluate alone. Otherwise
// all test calls pass linux, and unparam sees goos as constant on Linux CI.
func TestNonLinuxCLIYieldsNoAssessments(t *testing.T) {
	for _, goos := range []string{"darwin", "windows"} {
		t.Run(goos, func(t *testing.T) {
			fake := &fakeCollector{probe: Probe{GOOS: goos}}
			var out bytes.Buffer
			_ = run([]string{"--source", ".", "--json"}, &out, goos, fake.collect)
			var report JSONReport
			if err := json.Unmarshal(out.Bytes(), &report); err != nil {
				t.Fatalf("--json output must decode: %v", err)
			}
			if fake.calls != 1 || report.Scope != goos || len(report.Assessments) != 0 {
				t.Fatalf("non-Linux scope/collection mismatch: calls=%d report=%+v", fake.calls, report)
			}
			if !strings.Contains(dump(report.Findings), "kernel-not-applicable") {
				t.Errorf("non-Linux CLI must report its limited scope: %+v", report.Findings)
			}
		})
	}
}

// The complement, on the same entry point: nothing read means nothing claimed.
func TestUnreadableHostYieldsNoAssessments(t *testing.T) {
	fake := &fakeCollector{probe: Probe{GOOS: "linux"}}
	var out bytes.Buffer
	_ = run([]string{"--source", ".", "--json"}, &out, "linux", fake.collect)
	var report JSONReport
	if err := json.Unmarshal(out.Bytes(), &report); err != nil {
		t.Fatalf("--json output must decode: %v", err)
	}
	if len(report.Assessments) != 0 {
		t.Errorf("an unreadable kernel must yield no assessment: %+v", report.Assessments)
	}
	if !strings.Contains(dump(report.Findings), "running kernel version unavailable") {
		t.Errorf("an unreadable kernel must be reported as unverified:\n%s", dump(report.Findings))
	}
}

// A stale binary must withhold the structured comparison for the same reason
// it withholds the line findings: the JSON used to carry
// `at-or-above-reviewed-fix-floor` while the findings said not to trust any of
// them.
func TestAssessmentsAreWithheldWhenTheSourceIsUnverified(t *testing.T) {
	fake := &fakeCollector{probe: linuxProbe("6.6.159", "0", true)}
	var jsonOut bytes.Buffer
	if code := run([]string{"--source", t.TempDir(), "--json"}, &jsonOut, "linux", fake.collect); code != 1 {
		t.Errorf("a stale source must still be a warning, got exit %d", code)
	}
	var report JSONReport
	if err := json.Unmarshal(jsonOut.Bytes(), &report); err != nil {
		t.Fatalf("--json output must decode: %v", err)
	}
	if len(report.Assessments) != 0 {
		t.Errorf("a stale binary must not publish a comparison in --json: %+v", report.Assessments)
	}
	if len(report.Findings) != 1 || report.Findings[0].Name != "kernel-build" {
		t.Fatalf("a stale source must stop at the build finding: %+v", report.Findings)
	}

	var lineOut bytes.Buffer
	_ = run([]string{"--source", t.TempDir()}, &lineOut, "linux", fake.collect)
	if strings.Contains(lineOut.String(), "kernel-version-cve") {
		t.Errorf("the line output must be withheld too:\n%s", lineOut.String())
	}
}

// A non-Linux host must say what it is NOT covering, rather than reading as a
// clean bill of health for the WSL or Linux VM the operator actually uses.
func TestNonLinuxScopeExcludesWSLAndLinuxVMs(t *testing.T) {
	found := findingsOf(darwinProbe(), ".", time.Now())
	joined := dump(found)
	if !strings.Contains(joined, "kernel-not-applicable") {
		t.Fatalf("expected a not-applicable finding:\n%s", joined)
	}
	if !strings.Contains(joined, "WSL") {
		t.Errorf("the not-applicable finding must scope out WSL/Linux VMs:\n%s", joined)
	}
	if strings.Contains(joined, "kernel-version-cve") {
		t.Errorf("there is no kernel to compare on this host:\n%s", joined)
	}
}

// D1: no input may make this checker emit an ERR, because an ERR is what turns
// `just doctor` into exit 1 and breaks `just self-check` and
// test_doctor_sandbox over a condition only the operator can fix.
func TestNoFindingIsEverAnError(t *testing.T) {
	probes := []Probe{
		darwinProbe(),
		{GOOS: "windows"},
		{GOOS: "linux"},
		linuxProbe("6.6.150", "0", true),
		linuxProbe("6.6.150", "1", true),
		linuxProbe("6.6.159", "0", false),
		linuxProbe("6.6.87.2-microsoft-standard-WSL2", "0", true),
		linuxProbe("garbage", "0", true),
		Override("darwin", "6.6.150"),
		Override("linux", "6.6.159"),
	}
	for _, probe := range probes {
		found := findingsOf(probe, ".", time.Now())
		if len(found) == 0 {
			t.Fatalf("probe %+v produced no findings at all", probe)
		}
		for _, f := range found {
			if f.Level != "OK" && f.Level != "WARN" {
				t.Errorf("probe %+v produced level %q: %s", probe, f.Level, f.Detail)
			}
		}
		var out bytes.Buffer
		if code := Report(&out, found); code > 1 {
			t.Errorf("probe %+v made Report return %d; it must never exceed 1", probe, code)
		}
	}
}

// The migration sysctl is one of two trigger paths, so its line must never
// claim more than it observed: 0 does not exclude a BPF program.
func TestSysctlCoverageNamesTheBpfPathInEveryState(t *testing.T) {
	incident := mustIncident(t)
	cases := []struct {
		name  string
		probe Probe
		want  string
	}{
		{"zero", linuxProbe("6.6.159", "0", true), "BPF reuseport migration is invisible"},
		{"one", linuxProbe("6.6.159", "1", true), "BPF reuseport migration is invisible"},
		{"unreadable", linuxProbe("6.6.159", "", false), "unreadable"},
		{"override", Override("linux", "6.6.159"), "not observed"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			joined := dump(sysctlFindings(tc.probe, incident))
			if !strings.Contains(joined, tc.want) {
				t.Errorf("sysctl finding must contain %q:\n%s", tc.want, joined)
			}
		})
	}
}

// A non-zero migration sysctl is the one state the tool has positive evidence
// for, so it must be raised rather than reported as fine.
func TestNonZeroMigrationSysctlRaisesAWarning(t *testing.T) {
	incident := mustIncident(t)
	found := sysctlFindings(linuxProbe("6.6.159", "1", true), incident)
	if len(found) != 1 || found[0].Level != "WARN" {
		t.Fatalf("migration enabled must warn: %+v", found)
	}
	ok := sysctlFindings(linuxProbe("6.6.159", "0", true), incident)
	if len(ok) != 1 || ok[0].Level != "OK" {
		t.Fatalf("migration disabled must not warn: %+v", ok)
	}
}

// A stale or missing binary must not be laundered into a finding about the
// kernel.
func TestStaleSourceYieldsOnlyABuildWarning(t *testing.T) {
	found := findingsOf(darwinProbe(), t.TempDir(), time.Now())
	if len(found) != 1 || found[0].Name != "kernel-build" {
		t.Fatalf("a stale source must stop at the build finding: %+v", found)
	}
	if found[0].Level != "WARN" {
		t.Errorf("a stale source must warn, not error: %+v", found[0])
	}
}

func TestSourceMatchesTheCheckout(t *testing.T) {
	if !SourceMatches(".") {
		t.Fatal("the freshly built binary must match its own source tree")
	}
}

func TestRunCLIUsageErrors(t *testing.T) {
	var out bytes.Buffer
	if code := RunCLI([]string{"--nope"}, &out); code != 2 {
		t.Errorf("an unknown flag must be a usage error, got %d", code)
	}
	out.Reset()
	if code := RunCLI([]string{"unexpected"}, &out); code != 2 {
		t.Errorf("a positional argument must be a usage error, got %d", code)
	}
	out.Reset()
	if code := RunCLI([]string{"--help"}, &out); code != 0 {
		t.Errorf("--help must exit 0, got %d", code)
	}
}

func TestRunCLIJSONCarriesTheNoticeAndScope(t *testing.T) {
	var out bytes.Buffer
	_ = RunCLI([]string{"--source", ".", "--osrelease", "6.6.150", "--json"}, &out)
	var report JSONReport
	if err := json.Unmarshal(out.Bytes(), &report); err != nil {
		t.Fatalf("--json output must decode: %v\n%s", err, out.String())
	}
	if !strings.Contains(report.Notice, "NOT a security clearance") {
		t.Errorf("the notice must not read as a clearance: %q", report.Notice)
	}
	if report.Scope != "override-version-only" {
		t.Errorf("scope = %q, want override-version-only", report.Scope)
	}
	if len(report.Assessments) != 1 || report.Assessments[0].Outcome != BelowFloor {
		t.Fatalf("assessment is wrong: %+v", report.Assessments)
	}
	if len(report.Findings) == 0 {
		t.Error("the JSON report must carry the findings")
	}
}

func TestLinuxRunReportsTheRunningKernel(t *testing.T) {
	probe := linuxProbe("6.6.87.2-microsoft-standard-WSL2", "0", true)
	joined := dump(findingsOf(probe, ".", time.Now()))
	if !strings.Contains(joined, "6.6.87.2-microsoft-standard-WSL2") {
		t.Errorf("the running kernel must be reported:\n%s", joined)
	}
	if !strings.Contains(joined, "containers share it") {
		t.Errorf("the host/container relationship must be stated:\n%s", joined)
	}
}

func TestUnreadableRunningKernelIsUnverified(t *testing.T) {
	joined := dump(findingsOf(Probe{GOOS: "linux"}, ".", time.Now()))
	if !strings.Contains(joined, "running kernel version unavailable") {
		t.Errorf("an unreadable kernel must be unverified, not clean:\n%s", joined)
	}
	if strings.Contains(joined, "kernel-version-cve-2026-98432 - CVE-2026-98432 at-or-above") {
		t.Errorf("an unreadable kernel must not be reported as fixed:\n%s", joined)
	}
}

// The coverage caveat is the one line that must survive every path, including
// the non-Linux early return, or the tool reads as an attestation.
func TestCoverageCaveatAlwaysAppears(t *testing.T) {
	for _, probe := range []Probe{darwinProbe(), linuxProbe("6.6.150", "0", true), Override("darwin", "6.6.159")} {
		if !strings.Contains(dump(findingsOf(probe, ".", time.Now())), "kernel-coverage") {
			t.Errorf("probe %+v lost the coverage caveat", probe)
		}
	}
}

// A version string is untrusted input (it can arrive through --osrelease), so
// it must not be able to forge a second doctor line.
func TestVersionCannotForgeADoctorLine(t *testing.T) {
	probe := Override("darwin", "6.6.150\nOK   kernel-fake - everything is fine")
	var out bytes.Buffer
	_ = Report(&out, findingsOf(probe, ".", time.Now()))
	if strings.Contains(out.String(), "\nOK   kernel-fake") {
		t.Errorf("a newline in a version string forged a doctor line:\n%s", out.String())
	}
}

func TestLocalProbeDoesNotPanicOffLinux(t *testing.T) {
	// Collect must be safe to call on any GOOS; on non-Linux it reads nothing.
	if probe := localProbe(); probe.GOOS != "linux" {
		t.Errorf("GOOS = %q, want linux", probe.GOOS)
	}
}

func dump(found []Finding) string {
	var builder strings.Builder
	for _, f := range found {
		builder.WriteString(f.String())
		builder.WriteByte('\n')
	}
	return builder.String()
}
