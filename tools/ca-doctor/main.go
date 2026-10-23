// ca-doctor reports CA baseline health and reviewed incident evidence, never a blanket clean
// bill of health. It does not change certificates, packages, or configuration.
package main

import (
	"context"
	"flag"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"time"
)

func main() { os.Exit(RunCLI(context.Background(), os.Args[1:], os.Stdout)) }

func Report(out io.Writer, findings []Finding) int {
	code := 0
	for _, f := range findings {
		if _, err := fmt.Fprintln(out, f.String()); err != nil {
			return 2
		}
		if f.Level == "WARN" && code == 0 {
			code = 1
		}
		if f.Level == "ERR" {
			code = 2
		}
	}
	return code
}

func RunCLI(parent context.Context, args []string, out io.Writer) int {
	flags := flag.NewFlagSet("ca-doctor", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	source := flags.String("source", "tools/ca-doctor", "source directory for build freshness verification")
	offline := flags.Bool("offline", false, "skip TLS tests, report live trust as unverified")
	if err := flags.Parse(args); err != nil || flags.NArg() != 0 {
		return Report(out, []Finding{{"ERR", "ca-arguments", "usage: ca-doctor --source <tools/ca-doctor> [--offline]"}})
	}
	if !SourceMatches(*source) {
		return Report(out, []Finding{{"WARN", "ca-build", "missing/changed source or stale binary; run just ca-doctor-build; no security checks accepted"}})
	}
	if incidentError != nil {
		return Report(out, []Finding{{"ERR", "ca-policy", "invalid embedded incident data; review source and rebuild"}})
	}
	ctx, cancel := context.WithTimeout(parent, 30*time.Second)
	defer cancel()
	env := map[string]string{}
	for _, pair := range os.Environ() {
		key, value, found := strings.Cut(pair, "=")
		if found {
			env[key] = value
		}
	}
	env = NormalizeEnvironment(env, runtime.GOOS)
	kernel, _ := os.ReadFile("/proc/sys/kernel/osrelease")
	findings := []Finding{
		{"OK", "ca-build", fmt.Sprintf("binary source and incident data match checkout; %d incident policies", len(incidents))},
	}
	findings = append(findings, PlatformFindings(runtime.GOOS, string(kernel), env["WSL_DISTRO_NAME"] != "")...)
	findings = append(findings, EnvironmentEvidence(env)...)
	findings = append(findings, Finding{"OK", "ca-build-go", "diagnostic binary built with " + runtime.Version() + "; does not attest other compiled Go applications"})
	findings = append(findings, allVersionEvidence("go", strings.TrimPrefix(runtime.Version(), "go"))...)
	findings = append(findings, CheckCAPaths(env, runtime.GOOS, time.Now())...)
	for _, incident := range incidents {
		findings = append(findings, IncidentFreshness(incident, time.Now()))
		for _, advice := range incident.Advice {
			findings = append(findings, Finding{"WARN", "ca-advice-" + incident.ID, advice})
		}
	}
	tools := discoverTools()
	observations := make([][]Finding, len(tools))
	var wg sync.WaitGroup
	for i, tool := range tools {
		wg.Go(func() { observations[i] = inspectTool(ctx, tool) })
	}
	wg.Wait()
	for _, result := range observations {
		findings = append(findings, result...)
	}
	findings = append(findings, storeInventory(ctx)...)
	if *offline {
		findings = append(findings, Finding{"WARN", "ca-live", "offline requested; baseline HTTPS and all incident TLS chains unverified"})
	} else {
		// One semaphore across all clients prevents an explosion of simultaneous
		// sockets/processes while the same overall deadline bounds the whole run.
		slots := make(chan struct{}, 12)
		clients := []clientProbe{{"diagnostic-go", GoProbe{}}}
		for _, tool := range tools {
			if tool.Path != "" && tool.Kind != "" && ExecutableSupported(tool.Path, runtime.GOOS) {
				clients = append(clients, clientProbe{tool.Name, ExternalProbe{tool.Path, tool.Kind, OSCommands{}}})
			}
		}
		live := make([][]Finding, len(clients))
		for i, client := range clients {
			wg.Go(func() {
				live[i] = []Finding{ProbeBaseline(ctx, client.Name, client.Prober, slots)}
				for _, incident := range incidents {
					live[i] = append(live[i], ProbeClient(ctx, incident, client.Name, client.Prober, slots)...)
				}
			})
		}
		wg.Wait()
		for _, result := range live {
			findings = append(findings, result...)
		}
	}
	findings = append(findings, Finding{"WARN", "ca-coverage", "not a complete-machine attestation: browsers/OS revocation, Git TLS, other PATH copies/venvs, pip vendored CAs, rustls/webpki crates, Electron, containers and existing static binaries require separate verification; see docs/runbook/ca-doctor.md"})
	return Report(out, findings)
}

type clientProbe struct {
	Name   string
	Prober TLSProber
}

type toolSpec struct {
	Name, Command, Kind, Path string
	Args                      []string
}

func discoverTools() []toolSpec {
	tools := []toolSpec{
		{Name: "curl", Command: "curl", Kind: "curl", Args: []string{"--version"}},
		{Name: "git", Command: "git", Args: []string{"--version"}},
		{Name: "go", Command: "go", Args: []string{"version"}},
		{Name: "node", Command: "node", Kind: "node", Args: []string{"--version"}},
		{Name: "uv", Command: "uv", Args: []string{"--version"}},
		{Name: "mise", Command: "mise", Args: []string{"--version"}},
		{Name: "rustup", Command: "rustup", Args: []string{"--version"}},
		{Name: "rustc", Command: "rustc", Args: []string{"--version"}},
		{Name: "bun", Command: "bun", Kind: "bun", Args: []string{"--version"}},
	}
	for i := range tools {
		tools[i].Path, _ = exec.LookPath(tools[i].Command)
	}
	python := ""
	for _, command := range []string{"python3", "python"} {
		if path, err := exec.LookPath(command); err == nil {
			python = path
			break
		}
	}
	tools = append(tools, toolSpec{Name: "python", Kind: "python", Path: python, Args: []string{"--version"}})
	if runtime.GOOS == "darwin" {
		for _, pair := range []struct {
			Name, Path, Kind string
			Args             []string
		}{
			{"system-curl", "/usr/bin/curl", "curl", []string{"--version"}},
			{"system-python", "/usr/bin/python3", "python", []string{"--version"}},
		} {
			if _, err := os.Stat(pair.Path); err == nil && !sameExecutable(pair.Path, tools[0].Path) && !sameExecutable(pair.Path, python) {
				tools = append(tools, toolSpec{Name: pair.Name, Path: pair.Path, Kind: pair.Kind, Args: pair.Args})
			}
		}
	}
	return tools
}

func sameExecutable(a, b string) bool {
	if a == "" || b == "" {
		return false
	}
	x, errA := filepath.EvalSymlinks(a)
	y, errB := filepath.EvalSymlinks(b)
	return errA == nil && errB == nil && x == y
}

func ExtractVersion(tool, output string) string {
	text := strings.TrimSpace(output)
	if tool == "node" {
		return strings.TrimPrefix(text, "v")
	}
	fields := strings.Fields(text)
	if tool == "mise" && len(fields) > 0 && !strings.Contains(text, "\n") {
		return fields[0]
	}
	if tool == "go" && len(fields) == 4 && fields[0] == "go" && fields[1] == "version" {
		return strings.TrimPrefix(fields[2], "go")
	}
	if len(fields) >= 2 && fields[0] == tool {
		return fields[1]
	}
	return text
}

func inspectTool(ctx context.Context, tool toolSpec) []Finding {
	if tool.Path == "" {
		return []Finding{{"WARN", "ca-tool-" + tool.Name, "not on PATH; not assessed (installation is not required)"}}
	}
	if !ExecutableSupported(tool.Path, runtime.GOOS) {
		return []Finding{{"WARN", "ca-tool-" + tool.Name, "unsupported non-native wrapper; resolve to a native executable to assess"}}
	}
	commands := OSCommands{}
	result := commands.Run(ctx, tool.Path, tool.Args...)
	if result.Code != 0 || result.Truncated || strings.TrimSpace(result.Stdout) == "" {
		return []Finding{{"WARN", "ca-tool-" + tool.Name, "version command failed/timed out/overflowed; not assessed"}}
	}
	findings := []Finding{{"WARN", "ca-tool-" + tool.Name, "active executable: " + tool.Path + "; version/configuration evidence is not TLS remediation proof"}}
	if tool.Kind == "python" {
		values, valid := PythonMetadata(commands.Run(ctx, tool.Path, "-c", pythonMetadata))
		if !valid {
			return append(findings, Finding{"WARN", "ca-python-metadata", "unable to inspect active Python packages; certifi/pip unverified"})
		}
		for _, name := range []string{"certifi", "pip"} {
			for _, f := range allVersionEvidence(name, values[name]) {
				f.Name += "-" + tool.Name
				findings = append(findings, f)
			}
		}
		return findings
	}
	switch tool.Name {
	case "go", "node", "uv", "rustup", "mise":
		findings = append(findings, allVersionEvidence(tool.Name, ExtractVersion(tool.Name, result.Stdout))...)
	case "git":
		verify := commands.Run(ctx, tool.Path, "config", "--get-urlmatch", "http.sslVerify", baselineControlURL)
		_, noVerifyPresent := os.LookupEnv("GIT_SSL_NO_VERIFY")
		findings = append(findings, GitVerifyEvidence(verify, noVerifyPresent))
	case "bun":
		findings = append(findings, allVersionEvidence("bun", ExtractVersion("bun", result.Stdout))...)
	case "rustc":
		findings = append(findings, Finding{"WARN", "ca-rust", "rustc version does not establish compiled applications' CA dependency state; inspect each application's Cargo.lock"})
	}
	return findings
}

func storeInventory(ctx context.Context) []Finding {
	// Read-only package queries are inventory, not naive cross-distro version
	// comparisons. A vendor backport or browser block list is separate evidence.
	candidates := []struct {
		command string
		args    []string
	}{
		{"dpkg-query", []string{"-W", "-f=${Version}", "ca-certificates"}},
		{"rpm", []string{"-q", "--qf", "%{VERSION}-%{RELEASE}", "ca-certificates"}},
		{"apk", []string{"info", "-v", "ca-certificates"}},
	}
	if runtime.GOOS == "darwin" {
		candidates = append(candidates, struct {
			command string
			args    []string
		}{"brew", []string{"list", "--versions", "ca-certificates"}})
	}
	for _, candidate := range candidates {
		path, err := exec.LookPath(candidate.command)
		if err != nil {
			continue
		}
		result := (OSCommands{}).Run(ctx, path, candidate.args...)
		if result.Code == 0 && !result.Truncated && strings.TrimSpace(result.Stdout) != "" {
			return []Finding{{"WARN", "ca-os-bundle", "ca-certificates inventory via " + candidate.command + ": " + strings.TrimSpace(result.Stdout) + "; vendor backport/effective trust unverified"}}
		}
	}
	return []Finding{{"WARN", "ca-os-bundle", "OS CA bundle/revocation update state not established; update the OS/vendor trust package separately"}}
}
