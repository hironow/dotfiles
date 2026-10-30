package main

import (
	"os"
	"strings"
)

// Probe is everything observed about the kernel under assessment. Tests build
// it directly, so no test needs /proc, Linux, or a fixture file.
type Probe struct {
	GOOS         string
	OSRelease    string // raw contents of /proc/sys/kernel/osrelease
	OSReleaseOK  bool
	MigrateReq   string // raw contents of /proc/sys/net/ipv4/tcp_migrate_req
	MigrateReqOK bool
	DistroID     string
	// Override is set when --osrelease supplied the version. The local /proc
	// and /etc/os-release then describe a different machine and must not be
	// reported as evidence about the kernel being assessed.
	Override bool
}

// These are absolute literals on purpose: no path comes from user input, so no
// flag can redirect a read.
const (
	osReleasePath  = "/proc/sys/kernel/osrelease"
	migrateReqPath = "/proc/sys/net/ipv4/tcp_migrate_req"
	osReleaseFile  = "/etc/os-release"
)

// Collect reads the local host. On a non-Linux GOOS there is no /proc to read.
func Collect(goos string) Probe {
	probe := Probe{GOOS: goos}
	if goos != "linux" {
		return probe
	}
	if data, err := os.ReadFile(osReleasePath); err == nil {
		probe.OSRelease, probe.OSReleaseOK = string(data), true
	}
	if data, err := os.ReadFile(migrateReqPath); err == nil {
		probe.MigrateReq, probe.MigrateReqOK = string(data), true
	}
	if data, err := os.ReadFile(osReleaseFile); err == nil {
		probe.DistroID = distroID(string(data))
	}
	return probe
}

// Override replaces the local observation with a version reported for another
// host. The local sysctl and distro are dropped: they belong to the local
// machine and would otherwise be attributed to the kernel being assessed.
func Override(goos, osrelease string) Probe {
	return Probe{GOOS: goos, OSRelease: osrelease, OSReleaseOK: true, Override: true}
}

func distroID(text string) string {
	for _, line := range strings.Split(text, "\n") {
		if value, found := strings.CutPrefix(strings.TrimSpace(line), "ID="); found {
			return strings.Trim(value, `"'`)
		}
	}
	return ""
}

func (p Probe) version() string { return strings.TrimSpace(p.OSRelease) }

// sysctlValue reports the migration sysctl, and whether it was observed about
// the kernel under assessment at all.
func (p Probe) sysctlValue() (string, bool) {
	if p.Override || !p.MigrateReqOK {
		return "", false
	}
	return strings.TrimSpace(p.MigrateReq), true
}
