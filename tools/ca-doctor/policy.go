package main

import (
	"fmt"
	"regexp"
	"strconv"
	"strings"
)

const baselineControlURL = "https://example.com/"

type Finding struct{ Level, Name, Detail string }

type Outcome string

const (
	Accepted     Outcome = "accepted"
	CertRejected Outcome = "certificate-rejected"
	Unknown      Outcome = "unknown"
)

// No OK path: a certificate error alone cannot establish CA-specific distrust.
// Every chain rejected (with a working control) is INFO: there is nothing for
// the operator to do, but the reason for the rejection stays unproven. Anything
// unknown is WARN, and one accepted chain is ERR.
func ProbeEvidenceFor(incident Incident, client string, control Outcome, targets []Outcome) Finding {
	accepted, rejected := 0, 0
	var acceptedHosts []string
	for i, result := range targets {
		if result == Accepted {
			accepted++
			if i < len(incident.Hosts) {
				acceptedHosts = append(acceptedHosts, incident.Hosts[i])
			}
		}
		if result == CertRejected {
			rejected++
		}
	}
	name := "ca-live-" + incident.ID + "-" + client
	counts := fmt.Sprintf("control=%s; accepted=%d certificate-rejected=%d unverified=%d/%d", control, accepted, rejected, len(incident.Hosts)-accepted-rejected, len(incident.Hosts))
	switch {
	case accepted > 0:
		return Finding{"ERR", name, counts + "; accepted chains: " + strings.Join(acceptedHosts, ", ") + "; test endpoint accepted TLS; check CA store and TLS interception (served chain identity unverified)"}
	case control == Accepted && len(incident.Hosts) > 0 && rejected == len(incident.Hosts):
		return Finding{"INFO", name, counts + "; every test chain was rejected, but a rejection alone does not show why: CA distrust is not proven"}
	default:
		return Finding{"WARN", name, counts + "; CA-specific distrust unverified"}
	}
}

// ChainEvidence is the per-chain line, with the same level rule as the
// per-client line: accepted is ERR, rejected is INFO, unknown is WARN.
func ChainEvidence(incident Incident, client string, host int, result Outcome) Finding {
	level := "WARN"
	switch result {
	case Accepted:
		level = "ERR"
	case CertRejected:
		level = "INFO"
	case Unknown:
	}
	return Finding{level, "ca-chain-" + incident.ID + "-" + client, incident.Hosts[host] + ": " + string(result)}
}

func PlatformScope(goos, kernel string, wsl bool) string {
	switch {
	case goos == "windows":
		return "native Windows; WSL distros not assessed"
	case goos == "linux" && (wsl || strings.Contains(strings.ToLower(kernel), "microsoft")):
		return "WSL Linux; Windows host not assessed"
	case goos == "darwin":
		return "macOS; Keychain revocation and PEM bundles are independent"
	default:
		return goos + "; other hosts/containers not assessed"
	}
}

// PlatformFindings keeps scope and remediation together for CLI assembly.
// Advice is read-only and never asserts that another trust store is repaired.
func PlatformFindings(goos, kernel string, wsl bool) []Finding {
	advice := "update the OS vendor trust package and each runtime CA store separately"
	switch {
	case goos == "windows":
		advice = "check Windows Update and organization trust policy; independent PEM/runtime bundles and WSL need separate updates"
	case goos == "linux" && (wsl || strings.Contains(strings.ToLower(kernel), "microsoft")):
		advice = "update ca-certificates inside each WSL distro; Windows host trust updates do not repair Linux bundles"
	case goos == "darwin":
		advice = "check OS and Homebrew CA updates separately; Apple Python/LibreSSL may ignore SSL_CERT_FILE; verify actual TLS, not just environment paths"
	case goos == "linux":
		advice = "update the distribution CA package; independent runtime bundles, containers and static applications need separate updates"
	}
	return []Finding{
		{"INFO", "ca-platform", PlatformScope(goos, kernel, wsl) + "; OS/browser revocation updates not independently verified"},
		{"INFO", "ca-remediation", advice + "; no changes applied; see docs/runbook/ca-doctor.md"},
	}
}

// Windows environment variable names are case-insensitive; Unix names are not.
func NormalizeEnvironment(env map[string]string, goos string) map[string]string {
	result := make(map[string]string, len(env))
	for key, value := range env {
		if goos == "windows" {
			key = strings.ToUpper(key)
		}
		result[key] = value
	}
	return result
}

// caFileVariables name a CA file or directory. Their contents are checked by
// ca-file-* / ca-path-*, so the variable itself is a fact, not a warning.
var caFileVariables = map[string]bool{
	"SSL_CERT_FILE": true, "SSL_CERT_DIR": true, "CURL_CA_BUNDLE": true, "REQUESTS_CA_BUNDLE": true,
	"PIP_CERT": true, "GIT_SSL_CAINFO": true, "GIT_SSL_CAPATH": true, "NODE_EXTRA_CA_CERTS": true,
}

func EnvironmentEvidence(env map[string]string) []Finding {
	var findings []Finding
	for _, key := range []string{"NODE_TLS_REJECT_UNAUTHORIZED", "GIT_SSL_NO_VERIFY", "PYTHONHTTPSVERIFY", "SSL_CERT_FILE", "SSL_CERT_DIR", "CURL_CA_BUNDLE", "REQUESTS_CA_BUNDLE", "PIP_CERT", "GIT_SSL_CAINFO", "GIT_SSL_CAPATH", "NODE_EXTRA_CA_CERTS", "NODE_OPTIONS", "GODEBUG", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy"} {
		value, present := env[key]
		if !present || value == "" && key != "GIT_SSL_NO_VERIFY" {
			continue
		}
		level := "WARN"
		switch {
		case key == "NODE_TLS_REJECT_UNAUTHORIZED" && value == "0" || key == "GIT_SSL_NO_VERIFY":
			level = "ERR"
		case caFileVariables[key]:
			level = "INFO"
		}
		findings = append(findings, Finding{level, "ca-env", key + " is set (value redacted); custom CA/proxy/TLS settings limit conclusions"})
	}
	return findings
}

func GitVerifyEvidence(result CommandResult, noVerifyPresent bool) Finding {
	if noVerifyPresent {
		return Finding{"WARN", "ca-git-verify", "configuration overridden: GIT_SSL_NO_VERIFY is present and disables verification regardless of its value"}
	}
	f := Finding{"WARN", "ca-git-verify", "effective Git TLS verification could not be assessed"}
	if result.Truncated {
		return f
	}
	if result.Code == 1 && strings.TrimSpace(result.Stdout) == "" && strings.TrimSpace(result.Stderr) == "" {
		f.Level = "INFO"
		f.Detail = "not overridden: no http.sslVerify for baseline URL in current config context, so Git's default (verify) applies; other URLs/repos and Git TLS remain unverified"
		return f
	}
	if result.Code != 0 {
		return f
	}
	switch strings.ToLower(strings.TrimSpace(result.Stdout)) {
	case "false", "no", "off", "0", "":
		f.Level = "ERR"
		f.Detail = "effective http.sslVerify disables TLS verification for baseline URL"
	case "true", "yes", "on", "1":
		f.Level = "INFO"
		f.Detail = "http.sslVerify enabled for baseline URL; effective CA trust and other URLs/repos unverified"
	}
	return f
}

func (f Finding) String() string {
	return fmt.Sprintf("%-4s %s - %s", f.Level, clean(f.Name), clean(f.Detail))
}

func clean(s string) string {
	return strings.Map(func(r rune) rune {
		if r < 32 || r == 127 {
			return ' '
		}
		return r
	}, s)
}

var stableVersion = regexp.MustCompile(`^[0-9]+\.[0-9]+\.[0-9]+$`)

func versionParts(s string) ([3]int, bool) {
	var v [3]int
	if !stableVersion.MatchString(s) {
		return v, false
	}
	for i, p := range strings.Split(s, ".") {
		n, err := strconv.Atoi(p)
		if err != nil {
			return v, false
		}
		v[i] = n
	}
	return v, true
}
