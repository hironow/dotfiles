package rules

import (
	"fmt"
	"maps"
	"regexp"
	"slices"
	"strings"
)

const (
	telCompose       = "telemetry/compose.yaml"
	pyprojectPath    = "pyproject.toml"
	markdownlintPath = ".markdownlint-cli2.yaml"
	precommitPath    = ".pre-commit-config.yaml"
)

var (
	lgtmImage    = regexp.MustCompile(`^docker\.io/grafana/otel-lgtm:\d+\.\d+\.\d+$`)
	loopbackPort = regexp.MustCompile(`^127\.0\.0\.1:(\d+):(\d+)$`)
	seconds      = regexp.MustCompile(`^\d+s$`)
	// precommitTelemetry is telemetry/ as one alternative of the prek exclude.
	precommitTelemetry = regexp.MustCompile(`(?m)^\s*telemetry/`)
)

// lgtmPorts is every port of the otel-lgtm image, sorted.
var lgtmPorts = []string{"3000", "3200", "4040", "4317", "4318", "9090"}

// telemetryStack: telemetry is one upstream grafana/otel-lgtm container with
// no config of ours (ADR 0072), on loopback, on the shared network that
// tests.utils.isolation rewrites per run.
func telemetryStack() Rule {
	const id = "telemetry-one-pinned-lgtm"
	return Rule{
		ID:     id,
		Why:    "telemetry is one pinned upstream otel-lgtm container on loopback with no config of ours (ADR 0072)",
		Inputs: []Input{{Path: telCompose, Format: YAML}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: telCompose}
			compose := in[telCompose]
			for _, name := range slices.Sorted(maps.Keys(services(compose))) {
				if name != "lgtm" {
					r.add("telemetry runs only lgtm; remove the service %q", name)
				}
			}
			lgtm, ok := table(compose, "services", "lgtm")
			if !ok {
				r.add("telemetry/compose.yaml has no lgtm service")
				return r.out
			}
			if image, _ := str(lgtm, "image"); !lgtmImage.MatchString(image) {
				r.add("pin the lgtm image to a released version with the full registry name, not %q", image)
			}
			// Podman may drop an image's HEALTHCHECK; the isolated run waits on health.
			if !slices.Equal(strs(lgtm, "healthcheck", "test"), []string{"CMD", "/otel-lgtm/docker/healthcheck.sh"}) {
				r.add("the lgtm healthcheck must run the upstream /otel-lgtm/docker/healthcheck.sh")
			}
			if interval, _ := str(lgtm, "healthcheck", "interval"); !seconds.MatchString(interval) {
				r.add("the lgtm healthcheck needs an interval in seconds, not %q", interval)
			}
			var published []string
			for _, p := range strs(lgtm, "ports") {
				m := loopbackPort.FindStringSubmatch(p)
				switch {
				case m == nil:
					r.add("publish lgtm on 127.0.0.1 only, as host:container: %s", p)
				case m[1] != m[2]:
					r.add("keep lgtm's port number on the host: %s", p)
				default:
					published = append(published, m[1])
				}
			}
			slices.Sort(published)
			if !slices.Equal(published, lgtmPorts) {
				r.add("publish exactly the lgtm ports %v, not %v", lgtmPorts, published)
			}
			if !slices.Equal(strs(lgtm, "volumes"), []string{"lgtm-data:/data"}) {
				r.add("lgtm mounts only lgtm-data:/data: no bind mounts, dotfiles keeps no config for the stack")
			}
			volumes, _ := table(compose, "volumes")
			if names := slices.Sorted(maps.Keys(volumes)); !slices.Equal(names, []string{"lgtm-data"}) {
				r.add("the only named volume is lgtm-data, not %v", names)
			}
			if !sharedNetwork(compose) {
				r.add("networks must be only default: {name: shared-otel-net, external: true}")
			}
			return r.out
		},
	}
}

func sharedNetwork(compose any) bool {
	networks, _ := table(compose, "networks")
	def, ok := table(networks, "default")
	return ok && len(networks) == 1 && len(def) == 2 &&
		def["name"] == "shared-otel-net" && def["external"] == true
}

// directories is every directory an update entry watches.
func directories(entry map[string]any) []string {
	out := strs(entry, "directories")
	if dir, ok := str(entry, "directory"); ok {
		out = append(out, dir)
	}
	return out
}

// telemetryDependabot: Dependabot bumps the lgtm tag after the 7-day cooldown.
func telemetryDependabot() Rule {
	const id = "telemetry-dependabot-bumps-lgtm"
	return Rule{
		ID:     id,
		Why:    "one docker-compose Dependabot entry bumps the lgtm tag in telemetry/ after the 7-day cooldown",
		Inputs: []Input{{Path: dependabotPath, Format: YAML}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: dependabotPath}
			var compose []map[string]any
			for _, entry := range tables(in[dependabotPath], "updates") {
				if eco, _ := str(entry, "package-ecosystem"); eco == "docker-compose" {
					compose = append(compose, entry)
				}
				if slices.Contains(directories(entry), "/telemetry/examples") {
					r.add("no entry watches /telemetry/examples")
				}
			}
			if len(compose) != 1 {
				r.add("keep exactly one docker-compose entry, not %d", len(compose))
				return r.out
			}
			if dir, _ := str(compose[0], "directory"); dir != "/telemetry" {
				r.add("the docker-compose entry watches /telemetry, not %q", dir)
			}
			if days, _ := at(compose[0], "cooldown", "default-days"); fmt.Sprint(days) != "7" {
				r.add("the docker-compose entry waits 7 days (cooldown.default-days), not %v", days)
			}
			return r.out
		},
	}
}

func telemetryPath(p string) bool {
	return p == "telemetry" || strings.HasPrefix(p, "telemetry/")
}

// rootLintCoversTelemetry: the root lint runs over telemetry/ too; no tool's
// exclude list leaves it out.
func rootLintCoversTelemetry() Rule {
	const id = "root-lint-covers-telemetry"
	return Rule{
		ID:  id,
		Why: "telemetry/ is first-party, so the root lint and format tools cover it",
		Inputs: []Input{
			{Path: justfilePath, Format: Text},
			{Path: pyprojectPath, Format: TOML},
			{Path: markdownlintPath, Format: YAML},
			{Path: precommitPath, Format: YAML},
		},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id}
			if text, _ := in[justfilePath].(string); strings.Contains(text, "':!telemetry'") {
				r.addAt(justfilePath, "a file list leaves telemetry out with ':!telemetry'")
			}
			if slices.ContainsFunc(strs(in[pyprojectPath], "tool", "ruff", "extend-exclude"), telemetryPath) {
				r.addAt(pyprojectPath, "[tool.ruff] extend-exclude leaves telemetry out")
			}
			if slices.ContainsFunc(strs(in[markdownlintPath], "ignores"), telemetryPath) {
				r.addAt(markdownlintPath, "ignores leaves telemetry out")
			}
			if exclude, _ := str(in[precommitPath], "exclude"); precommitTelemetry.MatchString(exclude) {
				r.addAt(precommitPath, "the exclude leaves telemetry/ out")
			}
			return r.out
		},
	}
}
