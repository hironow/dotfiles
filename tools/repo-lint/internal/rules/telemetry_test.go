package rules

import "testing"

// telemetryCompose is a telemetry/compose.yaml, as yq decodes it, that the
// telemetry rule accepts.
func telemetryCompose() map[string]any {
	return map[string]any{
		"services": map[string]any{"lgtm": map[string]any{
			"image":       "docker.io/grafana/otel-lgtm:0.40.0",
			"ports":       lgtmPortList("127.0.0.1:3000:3000"),
			"volumes":     []any{"lgtm-data:/data"},
			"healthcheck": map[string]any{"test": []any{"CMD", "/otel-lgtm/docker/healthcheck.sh"}, "interval": "10s"},
		}},
		"volumes":  map[string]any{"lgtm-data": nil},
		"networks": map[string]any{"default": map[string]any{"name": "shared-otel-net", "external": true}},
	}
}

// lgtmPortList is lgtm's published ports with first in place of Grafana's.
func lgtmPortList(first string) []any {
	return []any{first, "127.0.0.1:3200:3200", "127.0.0.1:4040:4040", "127.0.0.1:4317:4317", "127.0.0.1:4318:4318", "127.0.0.1:9090:9090"}
}

func telemetryInputs() Inputs {
	return Inputs{
		telCompose:       telemetryCompose(),
		dependabotPath:   dependabotConfig(),
		justfilePath:     "lint:\n    git ls-files -z -- '*.py' ':!emulator'\n",
		pyprojectPath:    map[string]any{"tool": map[string]any{"ruff": map[string]any{"extend-exclude": []any{".semgrep", "emulator"}}}},
		markdownlintPath: map[string]any{"ignores": []any{"emulator/**", "skills/**"}},
		precommitPath:    map[string]any{"exclude": "(?x)^(\n  emulator/|\n  skills/\n)\n"},
	}
}

func lgtm(in Inputs) map[string]any {
	s, _ := table(in[telCompose], "services", "lgtm")
	return s
}

func TestTelemetryIsOnePinnedLoopbackLGTM(t *testing.T) {
	runCases(t, telemetryStack(), telemetryInputs, []ruleCase{
		{"a second service", func(in Inputs) { set(in[telCompose], map[string]any{"image": "x"}, "services", "collector") }, "collector"},
		{"no lgtm", func(in Inputs) { set(in[telCompose], nil, "services", "lgtm") }, "no lgtm service"},
		{"moving tag", func(in Inputs) { lgtm(in)["image"] = "docker.io/grafana/otel-lgtm:latest" }, "image"},
		{"short registry name", func(in Inputs) { lgtm(in)["image"] = "grafana/otel-lgtm:0.40.0" }, "image"},
		{"no healthcheck", func(in Inputs) { delete(lgtm(in), "healthcheck") }, "healthcheck"},
		{"healthcheck without interval", func(in Inputs) { set(lgtm(in), nil, "healthcheck", "interval") }, "interval"},
		{"port off loopback", func(in Inputs) { lgtm(in)["ports"] = lgtmPortList("3000:3000") }, "127.0.0.1"},
		{"another host port", func(in Inputs) { lgtm(in)["ports"] = lgtmPortList("127.0.0.1:3001:3000") }, "3001"},
		{"a port dropped", func(in Inputs) { lgtm(in)["ports"] = lgtmPortList("127.0.0.1:3000:3000")[:5] }, "9090"},
		{"bind mount", func(in Inputs) { lgtm(in)["volumes"] = []any{"lgtm-data:/data", "./grafana:/etc/grafana"} }, "bind"},
		{"another volume", func(in Inputs) {
			set(in[telCompose], nil, "volumes", "extra")
			in[telCompose].(map[string]any)["volumes"].(map[string]any)["extra"] = nil
		}, "extra"},
		{"another network", func(in Inputs) { set(in[telCompose], "otel", "networks", "default", "name") }, "shared-otel-net"},
	})
}

func TestDependabotBumpsTheLGTMTagAfterACooldown(t *testing.T) {
	compose := func(in Inputs) map[string]any { return dependabotEntry(in, "docker-compose") }
	runCases(t, telemetryDependabot(), telemetryInputs, []ruleCase{
		{"another directory", func(in Inputs) { compose(in)["directory"] = "/srv/telemetry" }, "/srv/telemetry"},
		{"no cooldown", func(in Inputs) { delete(compose(in), "cooldown") }, "cooldown"},
		{"a shorter cooldown", func(in Inputs) { set(compose(in), float64(1), "cooldown", "default-days") }, "cooldown"},
		{"two entries", func(in Inputs) {
			addUpdate(in, map[string]any{"package-ecosystem": "docker-compose", "directory": "/emulator"})
		}, "exactly one"},
		{"no entry", func(in Inputs) { compose(in)["package-ecosystem"] = "docker" }, "exactly one"},
		{"examples watched", func(in Inputs) {
			addUpdate(in, map[string]any{"package-ecosystem": "docker", "directories": []any{"/telemetry/examples"}})
		}, "/telemetry/examples"},
	})
}

func TestRootLintCoversTelemetry(t *testing.T) {
	runCases(t, rootLintCoversTelemetry(), telemetryInputs, []ruleCase{
		{"justfile pathspec", func(in Inputs) {
			in[justfilePath] = "lint:\n    git ls-files -z -- '*.py' ':!emulator' ':!telemetry'\n"
		}, "':!telemetry'"},
		{"ruff exclude", func(in Inputs) {
			set(in[pyprojectPath], []any{".semgrep", "telemetry"}, "tool", "ruff", "extend-exclude")
		}, "extend-exclude"},
		{"markdownlint ignore", func(in Inputs) { in[markdownlintPath] = map[string]any{"ignores": []any{"telemetry/**"}} }, "ignores"},
		{"prek exclude", func(in Inputs) {
			in[precommitPath] = map[string]any{"exclude": "(?x)^(\n  emulator/|\n  telemetry/|\n)\n"}
		}, "exclude"},
	})
}
