// kernel-doctor reports the Linux kernel a host would run, and compares its
// reported version against reviewed, source-cited CVE fix floors. It reports
// evidence and uncertainty, never a vulnerability verdict: it does not patch,
// build, install or update a kernel, and it never claims a host is safe.
package main

import (
	"encoding/json/v2"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"runtime"
	"strings"
	"time"
)

const (
	notice = "Evidence only, NOT a security clearance. A version string shows neither whether a vendor backported the fix nor whether a running kernel carries it. Unverified is never counted as fixed."
	help   = `usage: kernel-doctor [--json] [--osrelease=<version>] [--source=<dir>]
Compares the kernel version a host reports against reviewed, source-cited CVE
fix floors. Never a vulnerability verdict; vendor backports, the running patch
state and exploitability stay unverified.
With --osrelease, only that reported version is assessed and the local /proc
and /etc/os-release are not read (use it to assess another host, e.g. from a
Windows host: wsl.exe -e uname -r).
Exit: 0 no warnings, 1 warnings or unverified, 2 usage error.
It never installs, builds or updates a kernel.
`
)

// JSONReport is the --json shape.
type JSONReport struct {
	Notice      string       `json:"notice"`
	Scope       string       `json:"scope"`
	Assessments []Assessment `json:"assessments"`
	Findings    []Finding    `json:"findings"`
}

func main() { os.Exit(RunCLI(os.Args[1:], os.Stdout)) }

// RunCLI is exported for the tests; the process entrypoint only wires stdio.
func RunCLI(args []string, out io.Writer) int {
	return run(args, out, runtime.GOOS, Collect)
}

// run takes the host OS and the collector as parameters, so a test can drive
// every host shape on any machine — a test that instead relied on the real
// runtime.GOOS asserted a macOS-only outcome and would have failed the gate on
// the Linux the sandbox runs.
//
// Injecting the collector is also what makes the --osrelease contract
// checkable: a supplied version must perform NO local read, not merely discard
// the result afterwards.
func run(args []string, out io.Writer, goos string, collect func(string) Probe) int {
	flags := flag.NewFlagSet("kernel-doctor", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	asJSON := flags.Bool("json", false, "JSON output")
	source := flags.String("source", "tools/kernel-doctor", "source directory for build freshness verification")
	osrelease := flags.String("osrelease", "", "assess this reported kernel version instead of the local one")
	if err := flags.Parse(args); err != nil {
		_, _ = io.WriteString(out, help)
		if errors.Is(err, flag.ErrHelp) {
			return 0
		}
		return 2
	}
	if flags.NArg() != 0 {
		_, _ = io.WriteString(out, help)
		return 2
	}
	// Visit distinguishes "not supplied" from "supplied empty": an empty
	// override is an explicit input, not a missing one.
	override := false
	flags.Visit(func(f *flag.Flag) {
		if f.Name == "osrelease" {
			override = true
		}
	})

	var probe Probe
	if override {
		probe = Override(goos, *osrelease)
	} else {
		probe = collect(goos)
	}

	result := evaluate(probe, *source, time.Now())
	if *asJSON {
		report := JSONReport{Notice: notice, Scope: scopeText(probe), Assessments: result.assessments, Findings: result.findings}
		data, err := json.Marshal(report)
		if err != nil {
			return 1
		}
		if _, err := out.Write(append(data, '\n')); err != nil {
			return 1
		}
		for _, f := range result.findings {
			if f.Level != "OK" {
				return 1
			}
		}
		return 0
	}
	return Report(out, result.findings)
}

// evaluation holds the line findings and the structured assessments together,
// so the two outputs cannot disagree about whether a comparison was allowed.
//
// They used to be computed independently, and the JSON then advertised
// `at-or-above-reviewed-fix-floor` while the findings said only that the binary
// was stale and no finding should be trusted. The structured output has to be
// withheld for exactly the reason the line output is.
type evaluation struct {
	findings    []Finding
	assessments []Assessment
}

func evaluate(probe Probe, source string, now time.Time) evaluation {
	if !SourceMatches(source) {
		return evaluation{findings: []Finding{{"WARN", "kernel-build", "missing/changed source or stale binary; run just kernel-doctor-build before trusting any finding"}}}
	}
	if incidentError != nil {
		// The record lives in this repository, so naming the fault is a
		// developer aid, not a leak of host data.
		return evaluation{findings: []Finding{{"WARN", "kernel-policy", "invalid embedded incident data (" + incidentError.Error() + "); review the source and rebuild; no comparison performed"}}}
	}
	out := []Finding{{"OK", "kernel-build", fmt.Sprintf("binary source and incident data match the checkout; %d reviewed record(s)", len(incidents))}}
	out = append(out, scopeFindings(probe)...)
	if probe.GOOS != "linux" && !probe.Override {
		// No Linux kernel to assess. There is nothing to compare, and saying
		// more would read as a clearance.
		return evaluation{findings: append(out, coverageFinding())}
	}
	for _, incident := range incidents {
		out = append(out, assessmentFindings(probe, incident)...)
	}
	for _, incident := range incidents {
		out = append(out, freshnessFindings(incident, now)...)
	}
	return evaluation{findings: append(out, coverageFinding()), assessments: assessments(probe)}
}

func scopeFindings(probe Probe) []Finding {
	switch {
	case probe.Override:
		return []Finding{{"WARN", "kernel-scope", "assessing only the version given to --osrelease; the local /proc and /etc/os-release were not read, so this host's own kernel and the target host's settings are not assessed by this run"}}
	case probe.GOOS != "linux":
		return []Finding{{"OK", "kernel-not-applicable", "no Linux kernel runs on this local OS (" + probe.GOOS + "); any WSL or Linux VM used from this machine is NOT assessed by this run"}}
	case !probe.OSReleaseOK:
		return []Finding{{"WARN", "kernel-scope", "cannot read " + osReleasePath + "; the running kernel version is unverified"}}
	}
	return []Finding{{"OK", "kernel-scope", "running kernel " + probe.version() + " (" + hostOrigin(probe) + ")"}}
}

func hostOrigin(probe Probe) string {
	if probe.DistroID == "" {
		return "this is the host kernel and containers share it"
	}
	return "distro " + probe.DistroID + "; this is the host kernel and containers share it"
}

func assessments(probe Probe) []Assessment {
	if !probe.OSReleaseOK {
		return nil
	}
	result := make([]Assessment, 0, len(incidents))
	for _, incident := range incidents {
		result = append(result, Assess(probe.version(), incident))
	}
	return result
}

func scopeText(probe Probe) string {
	if probe.Override {
		return "override-version-only"
	}
	return probe.GOOS
}

func assessmentFindings(probe Probe, incident Incident) []Finding {
	var out []Finding
	if !probe.OSReleaseOK {
		out = append(out, Finding{"WARN", "kernel-version-" + incident.ID, "running kernel version unavailable; nothing compared"})
	} else {
		a := Assess(probe.version(), incident)
		level := "WARN"
		if a.Outcome == AtOrAboveFloor {
			level = "OK"
		}
		detail := fmt.Sprintf("%s %s; %s; patch_status=%s backport_state=%s; %s",
			incident.CVE, a.Outcome, a.Reason, a.PatchStatus, a.BackportState, floorList(incident))
		out = append(out, Finding{level, "kernel-version-" + incident.ID, detail})
	}
	out = append(out, sysctlFindings(probe, incident)...)
	// One line for every third-party figure: they are context for a human, not
	// separate actions, and one line each would dominate `just doctor`.
	out = append(out, Finding{
		"WARN", "kernel-observed-" + incident.ID,
		observationList(incident) + "; third-party figures read on their observation dates, not measured here",
	})
	for _, advice := range incident.Advice {
		out = append(out, Finding{"WARN", "kernel-advice-" + incident.ID, advice})
	}
	return out
}

func sysctlFindings(probe Probe, incident Incident) []Finding {
	var out []Finding
	for _, setting := range incident.Sysctls {
		name := "kernel-sysctl-" + incident.ID + "-" + strings.ReplaceAll(setting.Path, ".", "-")
		value, observed := probe.sysctlValue()
		switch {
		case probe.Override:
			out = append(out, Finding{"WARN", name, setting.Path + " not observed: --osrelease assesses a version only, so the target host's settings are unverified; " + setting.Note})
		case !observed:
			out = append(out, Finding{"WARN", name, setting.Path + " unreadable; " + setting.Note})
		default:
			level := "OK"
			if value != "0" {
				level = "WARN"
			}
			out = append(out, Finding{level, name, setting.Path + "=" + value +
				" in this network namespace only (a BPF reuseport migration is invisible to this value, and other namespaces are not inspected); " +
				setting.Note})
		}
	}
	return out
}

func freshnessFindings(incident Incident, now time.Time) []Finding {
	fresh, note := Freshness(incident, now)
	if !fresh {
		return []Finding{{
			"WARN", "kernel-freshness-" + incident.ID,
			note + "; reviewed " + incident.ReviewedAt + "; re-read the primary sources and refresh the record",
		}}
	}
	return []Finding{{"OK", "kernel-freshness-" + incident.ID, "reviewed " + incident.ReviewedAt + "; review by " + incident.ReviewAfter}}
}

func observationList(incident Incident) string {
	values := make([]string, 0, len(incident.Observations))
	for _, o := range incident.Observations {
		values = append(values, o.Label+"="+o.Value+" ("+o.ObservedAt+")")
	}
	return strings.Join(values, "; ")
}

func floorList(incident Incident) string {
	floors := make([]string, 0, len(incident.Branches))
	for _, floor := range incident.Branches {
		floors = append(floors, floor.Branch+"->"+floor.Fixed)
	}
	return "reviewed upstream floors: " + strings.Join(floors, " ") + "; mainline " + incident.FixedInMainline
}

func coverageFinding() Finding {
	return Finding{
		"WARN", "kernel-coverage",
		"not a kernel attestation: a kernel update takes effect only when the host or VM boots the new kernel (restarting processes or containers is not enough); " +
			"a vendor backport is invisible to this comparison; " +
			"the first trigger path of this CVE (sockets carrying IP options) and any BPF reuseport migration are not inspected; " +
			"see docs/runbook/kernel-doctor.md",
	}
}
