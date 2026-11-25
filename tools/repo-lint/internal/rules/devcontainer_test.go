package rules

import (
	"strings"
	"testing"
)

const featureScriptWithProfile = "#!/bin/sh\ncat > /etc/profile.d/dotfiles-mise.sh <<'PROFILE'\nexport MISE_DATA_DIR=/opt/mise\nexport QUINT_HOME=/opt/quint\nPROFILE\nexport QUINT_HOME=/opt/quint\n"

// devcontainerConfig is a devcontainer.json, as decoded, that the rule accepts.
func devcontainerConfig() map[string]any {
	return map[string]any{
		"image":             "mcr.microsoft.com/devcontainers/base:trixie",
		"remoteUser":        "root",
		"containerUser":     "root",
		"initializeCommand": "bash .devcontainer/require-podman-socket.sh",
		"mounts":            []any{podmanSocketMount},
		"features": map[string]any{
			"./features/dotfiles-tools":                     map[string]any{},
			"ghcr.io/devcontainers/features/common-utils:2": map[string]any{},
		},
		"containerEnv": map[string]any{
			"CONTAINER_HOST":            podmanSocketHost,
			"PODMAN_COMPOSE_PROVIDER":   "podman-compose",
			"MISE_DATA_DIR":             "/opt/mise",
			"QUINT_HOME":                "/opt/quint",
			"PATH":                      "/root/.local/bin:/opt/mise/shims:/usr/bin:/bin",
			"MISE_TRUSTED_CONFIG_PATHS": "/root/dotfiles:/root/sandbox/dotfiles-fresh",
		},
		"customizations": map[string]any{"vscode": map[string]any{"settings": map[string]any{"files.eol": "\n"}}},
	}
}

func devcontainerInputs() Inputs {
	return Inputs{
		devcontainerPath: devcontainerConfig(),
		devcontainerLock: map[string]any{"features": map[string]any{"ghcr.io/devcontainers/features/common-utils:2": map[string]any{}}},
		featureInstall:   featureScriptWithProfile,
	}
}

func dc(in Inputs) map[string]any { return in[devcontainerPath].(map[string]any) }

func containerEnv(in Inputs) map[string]any { return dc(in)["containerEnv"].(map[string]any) }

func addFeature(in Inputs, id string, locked bool) {
	dc(in)["features"].(map[string]any)[id] = map[string]any{}
	if locked {
		in[devcontainerLock].(map[string]any)["features"].(map[string]any)[id] = map[string]any{}
	}
}

func TestDevcontainerReachesOneExplicitEngineFromOfficialParts(t *testing.T) {
	runCases(t, devcontainerEngineAndPaths(), devcontainerInputs, []ruleCase{
		{"a community base image", func(in Inputs) { dc(in)["image"] = "docker.io/someone/base:1" }, "image"},
		{"the docker feature", func(in Inputs) {
			addFeature(in, "ghcr.io/devcontainers/features/docker-outside-of-docker:1", true)
		}, "docker-outside-of-docker"},
		{"a community feature", func(in Inputs) { addFeature(in, "ghcr.io/someone/features/x:1", true) }, "ghcr.io/someone/features/x:1"},
		{"a feature the lock misses", func(in Inputs) {
			addFeature(in, "ghcr.io/devcontainers/features/node:1", false)
		}, "devcontainer-lock.json"},
		{"a lock entry for a removed feature", func(in Inputs) {
			in[devcontainerLock].(map[string]any)["features"].(map[string]any)["ghcr.io/devcontainers/features/python:1"] = map[string]any{}
		}, "devcontainer-lock.json"},
		{"another user", func(in Inputs) { dc(in)["remoteUser"] = "vscode" }, "remoteUser"},
		{"a second mount", func(in Inputs) { dc(in)["mounts"] = []any{podmanSocketMount, "source=/,target=/host,type=bind"} }, "mounts"},
		{"a remote engine", func(in Inputs) { containerEnv(in)["CONTAINER_HOST"] = "tcp://10.0.0.1:2375" }, "CONTAINER_HOST"},
		{"another compose provider", func(in Inputs) { containerEnv(in)["PODMAN_COMPOSE_PROVIDER"] = "docker-compose" }, "PODMAN_COMPOSE_PROVIDER"},
		{"a docker path from the editor", func(in Inputs) {
			set(dc(in), "/usr/bin/docker", "customizations", "vscode", "settings", "dev.containers.dockerPath")
		}, "dev.containers.dockerPath"},
		{"no socket check", func(in Inputs) { dc(in)["initializeCommand"] = "true" }, "require-podman-socket.sh"},
		{"wider trust", func(in Inputs) { containerEnv(in)["MISE_TRUSTED_CONFIG_PATHS"] = "/" }, "MISE_TRUSTED_CONFIG_PATHS"},
		{"mise data under home", func(in Inputs) { containerEnv(in)["MISE_DATA_DIR"] = "/root/.local/share/mise" }, "MISE_DATA_DIR"},
		{"no mise shims", func(in Inputs) { containerEnv(in)["PATH"] = "/usr/bin:/bin" }, "/opt/mise/shims"},
		{"quint under home", func(in Inputs) { containerEnv(in)["QUINT_HOME"] = "/root/.quint" }, "QUINT_HOME"},
		{"the profile without quint", func(in Inputs) {
			in[featureInstall] = strings.Replace(featureScriptWithProfile, "export QUINT_HOME=/opt/quint\nPROFILE", "PROFILE", 1)
		}, "QUINT_HOME"},
	})
}
