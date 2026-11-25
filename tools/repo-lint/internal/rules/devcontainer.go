package rules

import (
	"maps"
	"regexp"
	"slices"
	"strings"
)

const (
	devcontainerPath  = ".devcontainer/devcontainer.json"
	devcontainerLock  = ".devcontainer/devcontainer-lock.json"
	podmanSocketMount = "source=${localEnv:DOTFILES_PODMAN_ENGINE_SOCKET},target=/run/dotfiles-podman/podman.sock,type=bind"
	podmanSocketHost  = "unix:///run/dotfiles-podman/podman.sock"
	baseImage         = "mcr.microsoft.com/devcontainers/base:trixie"
	officialFeature   = "ghcr.io/devcontainers/features/"
	oldMiseShims      = "/root/.local/share/mise/shims"
	trustedConfigs    = "/root/dotfiles:/root/sandbox/dotfiles-fresh"
)

var profileHeredoc = regexp.MustCompile(`(?s)cat > /etc/profile\.d/dotfiles-mise\.sh <<'PROFILE'\n(.*?)\nPROFILE`)

// devcontainerEngineAndPaths: the dev container is built from Microsoft's
// official image and features, each remote feature locked; it reaches exactly
// one engine, the explicitly mounted Podman socket, never a host-forwarded or
// editor-chosen one; mise trusts only the two checkouts; and the baked mise
// and Quint trees live outside $HOME, so a mount over /root cannot hide them
// (ADR 0006).
func devcontainerEngineAndPaths() Rule {
	const id = "devcontainer-engine-and-paths"
	return Rule{
		ID:  id,
		Why: "the dev container uses official locked parts, one explicit Podman socket, two trusted configs, and tool trees outside $HOME",
		Inputs: []Input{
			{Path: devcontainerPath, Format: JSONC},
			{Path: devcontainerLock, Format: JSON},
			{Path: featureInstall, Format: Text},
		},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: devcontainerPath}
			cfg := in[devcontainerPath]
			if image, _ := str(cfg, "image"); image != baseImage {
				r.add("image must be Microsoft's official %s, not %q", baseImage, image)
			}
			features, _ := table(cfg, "features")
			locked, _ := table(in[devcontainerLock], "features")
			var remote []string
			for _, f := range slices.Sorted(maps.Keys(features)) {
				if strings.HasPrefix(f, "./") {
					continue
				}
				remote = append(remote, f)
				if !strings.HasPrefix(f, officialFeature) {
					r.add("feature %s is not an official %s feature", f, officialFeature)
				}
				if strings.Contains(f, "docker-outside-of-docker") {
					r.add("remove feature %s: the container reaches the Podman socket only", f)
				}
			}
			if lock := slices.Sorted(maps.Keys(locked)); !slices.Equal(lock, remote) {
				r.addAt(devcontainerLock, "devcontainer-lock.json must lock exactly the remote features %v, not %v", remote, lock)
			}
			for _, key := range []string{"remoteUser", "containerUser"} {
				if user, _ := str(cfg, key); user != "root" {
					r.add("%s must be root, not %q", key, user)
				}
			}
			if mounts := strs(cfg, "mounts"); !slices.Equal(mounts, []string{podmanSocketMount}) {
				r.add("mounts must be only the engine socket %q, not %v", podmanSocketMount, mounts)
			}
			if init, _ := str(cfg, "initializeCommand"); !strings.Contains(init, "require-podman-socket.sh") {
				r.add("initializeCommand must run require-podman-socket.sh")
			}
			if _, ok := at(cfg, "customizations", "vscode", "settings", "dev.containers.dockerPath"); ok {
				r.add("remove dev.containers.dockerPath: the engine never comes from editor settings")
			}
			env, _ := table(cfg, "containerEnv")
			for _, want := range []struct{ key, value string }{
				{"CONTAINER_HOST", podmanSocketHost},
				{"PODMAN_COMPOSE_PROVIDER", "podman-compose"},
				{"MISE_TRUSTED_CONFIG_PATHS", trustedConfigs},
				{"MISE_DATA_DIR", "/opt/mise"},
				{"QUINT_HOME", "/opt/quint"},
			} {
				if got, _ := str(env, want.key); got != want.value {
					r.add("containerEnv %s must be %q, not %q", want.key, want.value, got)
				}
			}
			path, _ := str(env, "PATH")
			if dirs := strings.Split(path, ":"); !slices.Contains(dirs, "/opt/mise/shims") {
				r.add("containerEnv PATH must include /opt/mise/shims")
			} else if slices.Contains(dirs, oldMiseShims) {
				r.add("containerEnv PATH must not include %s; a mount over $HOME hides it and it shadows /opt/mise/shims", oldMiseShims)
			}
			script, _ := in[featureInstall].(string)
			m := profileHeredoc.FindStringSubmatch(script)
			if m == nil || !slices.Contains(strings.Split(m[1], "\n"), "export QUINT_HOME=/opt/quint") {
				r.addAt(featureInstall, "the /etc/profile.d/dotfiles-mise.sh the feature writes must export QUINT_HOME=/opt/quint")
			}
			return r.out
		},
	}
}
