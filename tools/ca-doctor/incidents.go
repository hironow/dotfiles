package main

import (
	"encoding/json/v2"
	"errors"
	"fmt"
	"net"
	"net/url"
	"regexp"
	"strings"
	"time"
)

type VersionFloor struct {
	Branch  string `json:"branch"`
	Minimum string `json:"minimum"`
}

type Incident struct {
	ID          string                    `json:"id"`
	Type        string                    `json:"type"`
	Title       string                    `json:"title"`
	Source      string                    `json:"source"`
	ReviewedAt  string                    `json:"reviewedAt"`
	ReviewAfter string                    `json:"reviewAfter"`
	ControlURL  string                    `json:"controlURL"`
	Hosts       []string                  `json:"hosts"`
	Floors      map[string][]VersionFloor `json:"floors"`
	Pending     []string                  `json:"pending"`
	Advice      []string                  `json:"advice"`
}

var (
	incidentID               = regexp.MustCompile(`^[a-z0-9][a-z0-9-]{0,63}$`)
	dnsHost                  = regexp.MustCompile(`^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$`)
	versionBranch            = regexp.MustCompile(`^[0-9]+(?:\.[0-9]+)?$`)
	incidents, incidentError = loadIncidents()
)

func publicHTTPS(raw string) bool {
	u, err := url.Parse(raw)
	return err == nil && u.Scheme == "https" && u.User == nil && u.RawQuery == "" && u.Fragment == "" && u.Port() == "" && validHost(u.Hostname())
}

func validHost(host string) bool {
	return strings.Contains(host, ".") && dnsHost.MatchString(host) && net.ParseIP(host) == nil && !strings.Contains(host, "..")
}

func ParseIncident(data []byte) (Incident, error) {
	var incident Incident
	if err := json.Unmarshal(data, &incident, json.RejectUnknownMembers(true)); err != nil {
		return incident, fmt.Errorf("parse incident: %w", err)
	}
	if !incidentID.MatchString(incident.ID) || incident.Type != "tls-endpoint-and-version" || incident.Title == "" || !publicHTTPS(incident.Source) || !publicHTTPS(incident.ControlURL) || len(incident.Hosts) == 0 || len(incident.Hosts) > 64 {
		return incident, errors.New("invalid incident metadata")
	}
	reviewed, err := time.Parse(time.DateOnly, incident.ReviewedAt)
	if err != nil {
		return incident, fmt.Errorf("review date: %w", err)
	}
	after, err := time.Parse(time.DateOnly, incident.ReviewAfter)
	if err != nil || !after.After(reviewed) {
		return incident, errors.New("invalid review-after date")
	}
	seen := map[string]bool{}
	for _, host := range incident.Hosts {
		if !validHost(host) || seen[host] {
			return incident, errors.New("invalid/duplicate incident host")
		}
		seen[host] = true
	}
	for tool, floors := range incident.Floors {
		if !versionToolSupported(tool) || len(floors) == 0 {
			return incident, errors.New("invalid tool floor")
		}
		seenBranches := map[string]bool{}
		for _, floor := range floors {
			if _, valid := versionParts(floor.Minimum); !valid || !versionBranch.MatchString(floor.Branch) || !strings.HasPrefix(floor.Minimum, floor.Branch+".") || seenBranches[floor.Branch] {
				return incident, errors.New("invalid version branch/floor")
			}
			for previous := range seenBranches {
				if strings.HasPrefix(previous, floor.Branch+".") || strings.HasPrefix(floor.Branch, previous+".") {
					return incident, errors.New("overlapping version branches")
				}
			}
			seenBranches[floor.Branch] = true
		}
	}
	for _, tool := range incident.Pending {
		if !versionToolSupported(tool) && tool != "bun" {
			return incident, errors.New("invalid pending tool")
		}
	}
	return incident, nil
}

func versionToolSupported(tool string) bool {
	switch tool {
	case "go", "node", "uv", "rustup", "certifi", "pip", "bun", "mise":
		return true
	default:
		return false
	}
}

func loadIncidents() ([]Incident, error) {
	entries, err := buildSource.ReadDir("incidents")
	if err != nil {
		return nil, fmt.Errorf("incident directory: %w", err)
	}
	var result []Incident
	seen := map[string]bool{}
	for _, entry := range entries {
		data, err := buildSource.ReadFile("incidents/" + entry.Name())
		if err != nil {
			return nil, fmt.Errorf("incident read: %w", err)
		}
		incident, err := ParseIncident(data)
		if err != nil {
			return nil, fmt.Errorf("incident %s: %w", entry.Name(), err)
		}
		if seen[incident.ID] {
			return nil, errors.New("duplicate incident id")
		}
		seen[incident.ID] = true
		result = append(result, incident)
	}
	return result, nil
}

func IncidentFreshness(incident Incident, now time.Time) Finding {
	after, err := time.Parse(time.DateOnly, incident.ReviewAfter)
	f := Finding{"OK", "ca-policy-" + incident.ID, "reviewed " + incident.ReviewedAt + "; source " + incident.Source + "; review by " + incident.ReviewAfter}
	if err != nil || !now.Before(after.AddDate(0, 0, 1)) {
		f.Level = "WARN"
		f.Detail += "; policy review overdue; refresh from primary sources, no remote rules loaded"
	}
	return f
}

func allVersionEvidence(tool, version string) []Finding {
	var findings []Finding
	for _, incident := range incidents {
		if _, found := incident.Floors[tool]; found {
			findings = append(findings, VersionEvidenceFor(incident, tool, version))
		}
		for _, pending := range incident.Pending {
			if pending == tool {
				findings = append(findings, Finding{"WARN", "ca-pending-" + incident.ID + "-" + tool, "upstream fix pending at policy review; current release unverified"})
			}
		}
	}
	return findings
}

func VersionEvidenceFor(incident Incident, tool, version string) Finding {
	name := "ca-version-" + incident.ID + "-" + tool
	if version == absentPackage {
		return Finding{"INFO", name, "not installed in this Python; nothing to compare"}
	}
	f := Finding{"WARN", name, "unsupported/unparseable release; remediation unverified"}
	v, valid := versionParts(version)
	if !valid {
		return f
	}
	branches := make([]string, 0, len(incident.Floors[tool]))
	for _, candidate := range incident.Floors[tool] {
		branches = append(branches, candidate.Branch)
		if !strings.HasPrefix(version, candidate.Branch+".") {
			continue
		}
		floor, valid := versionParts(candidate.Minimum)
		if !valid {
			return f
		}
		f.Level = "OK"
		for i := range v {
			if v[i] < floor[i] {
				f.Level = "ERR"
				break
			}
			if v[i] > floor[i] {
				break
			}
		}
		f.Detail = version + "; published fix floor " + candidate.Minimum + " (reviewed " + incident.ReviewedAt + "); version evidence only"
		if f.Level == "ERR" {
			f.Detail += "; update this tool"
		}
		return f
	}
	f.Detail = version + " is outside the reviewed fix branches (" + strings.Join(branches, ", ") + "); remediation unverified"
	return f
}
