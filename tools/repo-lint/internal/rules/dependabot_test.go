package rules

import "testing"

const heldPython = "FROM docker.io/library/python:3.12.15-slim AS base\n"

func ignoreAll(names ...string) []any {
	out := make([]any, 0, len(names))
	for _, name := range names {
		out = append(out, map[string]any{"dependency-name": name})
	}
	return out
}

// dependabotConfig is a .github/dependabot.yaml, as yq decodes it, that every
// Dependabot rule accepts.
func dependabotConfig() map[string]any {
	uv := func(dir string) map[string]any {
		return map[string]any{"package-ecosystem": "uv", "directory": dir, "ignore": ignoreAll("ruff", "ty")}
	}
	return map[string]any{"updates": []any{
		map[string]any{"package-ecosystem": "github-actions", "directory": "/"},
		uv("/"), uv("/tools/rttm"), uv("/emulator"),
		map[string]any{"package-ecosystem": "docker-compose", "directory": "/telemetry", "cooldown": map[string]any{"default-days": float64(7)}},
		map[string]any{
			"package-ecosystem": "docker",
			"directories":       []any{"/tests/docker", "/emulator/*"},
			"ignore": []any{map[string]any{
				"dependency-name": "library/python",
				"update-types":    []any{"version-update:semver-major", "version-update:semver-minor"},
			}},
		},
	}}
}

// dependabotEntry is the first update entry for the ecosystem.
func dependabotEntry(in Inputs, ecosystem string) map[string]any {
	for _, u := range in[dependabotPath].(map[string]any)["updates"].([]any) {
		entry := u.(map[string]any)
		if entry["package-ecosystem"] == ecosystem {
			return entry
		}
	}
	return nil
}

func uvEntry(in Inputs, directory string) map[string]any {
	for _, u := range in[dependabotPath].(map[string]any)["updates"].([]any) {
		entry := u.(map[string]any)
		if entry["package-ecosystem"] == "uv" && entry["directory"] == directory {
			return entry
		}
	}
	return nil
}

func addUpdate(in Inputs, entry map[string]any) {
	cfg := in[dependabotPath].(map[string]any)
	cfg["updates"] = append(cfg["updates"].([]any), entry)
}

func dependabotInputs() Inputs {
	return Inputs{
		dependabotPath: dependabotConfig(),
		allDockerfiles: map[string]any{
			"emulator/a2a-inspector/Dockerfile": heldPython,
			"emulator/healthcheck/Dockerfile":   healthDockerfileText,
			"templates/app/Dockerfile":          "FROM python:3.14\n",
		},
	}
}

func dockerfiles(in Inputs) map[string]any { return in[allDockerfiles].(map[string]any) }

func TestDependabotNamesAnImageWithoutItsRegistry(t *testing.T) {
	for ref, want := range map[string]string{
		"docker.io/library/python:3.12.15-slim":  "library/python",
		"docker.io/library/python@sha256:ab12":   "library/python",
		"python:3.12-slim":                       "python",
		"gcr.io/cloud-spanner-emulator/emulator": "cloud-spanner-emulator/emulator",
		"registry.local:5000/team/python":        "team/python",
		"python":                                 "python",
		"library/python":                         "library/python",
	} {
		if got := dependabotName(ref); got != want {
			t.Errorf("dependabotName(%q) = %q, want %q", ref, got, want)
		}
	}
}

func TestDependabotHoldsEveryPythonImageOnItsMinor(t *testing.T) {
	docker := func(in Inputs) map[string]any { return dependabotEntry(in, "docker") }
	runCases(t, dependabotPythonHeld(), dependabotInputs, []ruleCase{
		{"an image by its short name", func(in Inputs) {
			dockerfiles(in)["tests/docker/Dockerfile.ci"] = "FROM --platform=linux/amd64 python:3.13-slim\n"
		}, `"python"`},
		{"an image from another registry", func(in Inputs) {
			dockerfiles(in)["emulator/x/Dockerfile"] = "FROM registry.local:5000/team/python:3.12\n"
		}, `"team/python"`},
		{"minor bumps let through", func(in Inputs) {
			set(docker(in)["ignore"].([]any)[0], []any{"version-update:semver-major"}, "update-types")
		}, "library/python"},
		{"no python image left", func(in Inputs) {
			delete(dockerfiles(in), "emulator/a2a-inspector/Dockerfile")
		}, "no python base image"},
		{"no docker entry", func(in Inputs) { docker(in)["package-ecosystem"] = "gomod" }, "no docker entry"},
	})
}

func TestDependabotLeavesTheSynchronizedToolsToBumpTool(t *testing.T) {
	runCases(t, dependabotUVSyncedTools(), dependabotInputs, []ruleCase{
		{"no root entry", func(in Inputs) { uvEntry(in, "/")["directory"] = "/elsewhere" }, "no uv entry for /"},
		{"rttm bumps ty", func(in Inputs) { uvEntry(in, "/tools/rttm")["ignore"] = ignoreAll("ruff") }, "/tools/rttm must ignore ty"},
		{"emulator holds only majors of ruff", func(in Inputs) {
			uvEntry(in, "/emulator")["ignore"] = []any{
				map[string]any{"dependency-name": "ruff", "update-types": []any{"version-update:semver-major"}},
				map[string]any{"dependency-name": "ty"},
			}
		}, "/emulator must ignore ruff"},
	})
}
