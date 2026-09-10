#!/usr/bin/env bash
# Cursor Cloud Agent environment bootstrap for hironow/dotfiles.
#
# Idempotent, non-interactive. Turns a fresh Ubuntu image into a working
# dotfiles dev box: the mise-managed toolchain the `just` gates expect, the uv
# projects those gates run with --frozen, plus Docker (fuse-overlayfs) and the
# devcontainer CLI so the heavier `just test` / emulator paths also work.
#
# Tool provisioning mirrors the repo's own install paths:
#   - mise via its official apt repo (GPG fingerprint verified), exactly like
#     .devcontainer/features/dotfiles-tools/install.sh.
#   - config/mise/config.toml linked to ~/.config/mise/config.toml as the
#     single source of truth for pinned versions, exactly like `just deploy`.
#   - the FULL pinned toolset is installed because the justfile wraps every
#     tool in `mise exec --`, which materializes all configured tools.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
export DEBIAN_FRONTEND=noninteractive
cd "${REPO_DIR}"

echo "[install] apt prerequisites (docker, fuse-overlayfs, gnupg, ...)"
sudo apt-get update -y
# --force-confold: docker.io ships /etc/fuse.conf which trips a conffile prompt
# under noninteractive apt; keep the existing file and move on.
sudo apt-get install -y --no-install-recommends \
  -o Dpkg::Options::=--force-confold \
  apt-transport-https ca-certificates gnupg curl jq \
  docker.io fuse-overlayfs uidmap

echo "[install] mise (official apt repo, fingerprint verified)"
if ! command -v mise >/dev/null 2>&1; then
  sudo install -d -m 0755 /etc/apt/keyrings
  keytmp="$(mktemp -d)"
  curl -fsSL -o "${keytmp}/mise.asc" https://mise.jdx.dev/gpg-key.pub
  gpg --no-default-keyring --keyring "${keytmp}/mise.gpg" --import "${keytmp}/mise.asc" 2>/dev/null
  fpr="$(gpg --no-default-keyring --keyring "${keytmp}/mise.gpg" --list-keys --with-colons | awk -F: '/^fpr:/{print $10; exit}')"
  if [ "${fpr}" != "24853EC9F655CE80B48E6C3A8B81C9D17413A06D" ]; then
    echo "[install] mise GPG fingerprint mismatch: ${fpr}" >&2
    exit 1
  fi
  sudo install -m 0644 "${keytmp}/mise.gpg" /etc/apt/keyrings/mise-archive-keyring.gpg
  rm -rf "${keytmp}"
  echo "deb [signed-by=/etc/apt/keyrings/mise-archive-keyring.gpg arch=amd64] https://mise.jdx.dev/deb stable main" \
    | sudo tee /etc/apt/sources.list.d/mise.list >/dev/null
  sudo apt-get update -y
  sudo apt-get install -y --no-install-recommends mise
fi
mise --version

echo "[install] link config/mise/config.toml -> ~/.config/mise/config.toml (pinned-version SoT, cf. just deploy)"
mkdir -p "${HOME}/.config/mise"
ln -sf "${REPO_DIR}/config/mise/config.toml" "${HOME}/.config/mise/config.toml"
mise trust "${REPO_DIR}/config/mise/config.toml" >/dev/null 2>&1 || true
mise trust "${HOME}/.config/mise/config.toml" >/dev/null 2>&1 || true

echo "[install] mise install (full pinned toolset; -C / scopes to the global config, cf. just deploy)"
mise -C / install

echo "[install] uv sync --frozen (root tooling + emulator; the gates run --frozen)"
mise exec -- uv sync --frozen
( cd "${REPO_DIR}/emulator" && mise exec -- uv sync --frozen )

echo "[install] devcontainer CLI (bun global, per ADR 0027) for 'just test'"
mise exec -- bun install -g @devcontainers/cli

echo "[install] Docker daemon config: fuse-overlayfs snapshotter"
# Cloud Agent VMs are themselves containers on an overlay root; Docker's default
# overlay-on-overlay graphdriver fails to mount (invalid argument), so pin the
# fuse-overlayfs driver (/dev/fuse is present) and disable the containerd
# snapshotter so the classic graphdriver is used.
sudo mkdir -p /etc/docker
if [ ! -s /etc/docker/daemon.json ]; then
  echo '{"storage-driver":"fuse-overlayfs","features":{"containerd-snapshotter":false}}' \
    | sudo tee /etc/docker/daemon.json >/dev/null
fi
sudo groupadd -f docker
sudo usermod -aG docker "$(id -un)" || true

echo "[install] hironow/skills into the bunx skills store (~/.agents/skills), then place"
# ADR 0043: the skills CLI writes only the store ('-a universal'); consumer
# homes (~/.claude/skills, ...) get relative symlinks from scripts/skills_lock.py
# place. Best-effort so a skills registry/network hiccup never blocks the build;
# the pinned CLI version tracks scripts/skills_lock.py (SKILLS_CLI_VERSION).
skills_cli_ver="$(sed -n 's/^SKILLS_CLI_VERSION = "\(.*\)"/\1/p' "${REPO_DIR}/scripts/skills_lock.py")"
if [ -n "${skills_cli_ver}" ]; then
  mise exec -- bunx "skills@${skills_cli_ver}" add hironow/skills -g -s '*' -a universal -y \
    || echo "[install] WARN: 'skills add hironow/skills' did not complete (best-effort)"
  # place links declared hironow/skills from the store into existing agent
  # homes; it exits non-zero when third-party declared skills are absent from
  # the store (expected here — only hironow/skills is installed), so ignore it.
  mise exec -- just skills-place || true
else
  echo "[install] WARN: could not read SKILLS_CLI_VERSION; skipping skills add"
fi

echo "[install] done"
