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
func ProbeEvidenceFor(incident Incident, client string, control Outcome, targets []Outcome) Finding {
	accepted, rejected := 0, 0
	for _, result := range targets {
		if result == Accepted {
			accepted++
		}
		if result == CertRejected {
			rejected++
		}
	}
	f := Finding{"WARN", "ca-live-" + incident.ID + "-" + client, fmt.Sprintf("control=%s; accepted=%d certificate-rejected=%d unverified=%d/%d; CA-specific distrust unverified", control, accepted, rejected, len(incident.Hosts)-accepted-rejected, len(incident.Hosts))}
	if accepted > 0 {
		f.Level = "ERR"
		f.Detail += "; test endpoint accepted TLS; check CA store and TLS interception (served chain identity unverified)"
	}
	return f
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

func EnvironmentEvidence(env map[string]string) []Finding {
	var findings []Finding
	for _, key := range []string{"NODE_TLS_REJECT_UNAUTHORIZED", "GIT_SSL_NO_VERIFY", "PYTHONHTTPSVERIFY", "SSL_CERT_FILE", "SSL_CERT_DIR", "CURL_CA_BUNDLE", "REQUESTS_CA_BUNDLE", "PIP_CERT", "GIT_SSL_CAINFO", "GIT_SSL_CAPATH", "NODE_EXTRA_CA_CERTS", "NODE_OPTIONS", "GODEBUG", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy"} {
		value, present := env[key]
		if !present || value == "" && key != "GIT_SSL_NO_VERIFY" {
			continue
		}
		level := "WARN"
		if key == "NODE_TLS_REJECT_UNAUTHORIZED" && value == "0" || key == "GIT_SSL_NO_VERIFY" {
			level = "ERR"
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
		f.Detail = "no explicit http.sslVerify for baseline URL in current config context; other URLs/repos and Git TLS remain unverified"
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
