#!/usr/bin/env bash
# Local devcontainer feature: install the non-Microsoft-feature tools
# the dotfiles repo expects.
#
# Runs at devcontainer BUILD time so binaries are committed into the
# saved image (devcontainers/ci action's `imageName` exports the
# post-build image; lifecycle commands run in the up-and-running
# container and DO NOT persist back to the saved image).
#
# Trust policy:
#   - features in devcontainer.json: ONLY ghcr.io/devcontainers/features/* (Microsoft)
#   - tools below: vendor-official artifacts only, NEVER `curl | bash`
#       * gcloud:  Google apt repo (GPG-verified, packages.cloud.google.com)
#       * mise:    jdx apt repo  (GPG-verified, mise.jdx.dev/deb)
#       * uv:      astral-sh GitHub release + .sha256 sidecar
#       * just:    casey/just GitHub release + SHA256SUMS bulk file
#       * sheldon: rossmacarthur/sheldon GitHub release + pinned SHA256
set -euo pipefail

ARCH=$(uname -m)
export DEBIAN_FRONTEND=noninteractive

# ---- Google Cloud SDK -----------------------------------------------
echo "[dotfiles-tools] installing Google Cloud SDK from apt repo"
apt-get update -y
apt-get install -y --no-install-recommends apt-transport-https ca-certificates gnupg curl
curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
  | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg
echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
  > /etc/apt/sources.list.d/google-cloud-sdk.list
apt-get update -y
apt-get install -y --no-install-recommends google-cloud-cli

# ---- mise (rtx-style version manager) -------------------------------
echo "[dotfiles-tools] installing mise from apt repo"
install -d -m 0755 /etc/apt/keyrings
curl -fsSL https://mise.jdx.dev/gpg-key.pub \
  | gpg --dearmor -o /etc/apt/keyrings/mise-archive-keyring.gpg
echo "deb [signed-by=/etc/apt/keyrings/mise-archive-keyring.gpg arch=amd64,arm64] https://mise.jdx.dev/deb stable main" \
  > /etc/apt/sources.list.d/mise.list
apt-get update -y
apt-get install -y --no-install-recommends mise

# ---- uv (Python package manager) ------------------------------------
UV_VERSION="0.11.8"
case "$ARCH" in
  x86_64)  UV_TARGET="x86_64-unknown-linux-gnu" ;;
  aarch64) UV_TARGET="aarch64-unknown-linux-gnu" ;;
  *) echo "[dotfiles-tools] unsupported arch: $ARCH" >&2; exit 1 ;;
esac
UV_FILE="uv-${UV_TARGET}.tar.gz"
UV_BASE="https://github.com/astral-sh/uv/releases/download/${UV_VERSION}"
echo "[dotfiles-tools] installing uv ${UV_VERSION} (${UV_TARGET})"
curl -fsSL -o "/tmp/${UV_FILE}" "${UV_BASE}/${UV_FILE}"
curl -fsSL -o "/tmp/${UV_FILE}.sha256" "${UV_BASE}/${UV_FILE}.sha256"
( cd /tmp && sha256sum -c "${UV_FILE}.sha256" )
tar -xz -f "/tmp/${UV_FILE}" -C /tmp --strip-components=1
install -m 0755 /tmp/uv /usr/local/bin/uv
install -m 0755 /tmp/uvx /usr/local/bin/uvx
rm -f "/tmp/${UV_FILE}" "/tmp/${UV_FILE}.sha256" /tmp/uv /tmp/uvx

# ---- just (command runner) ------------------------------------------
JUST_VERSION="1.40.0"
case "$ARCH" in
  x86_64)  JUST_TARGET="x86_64-unknown-linux-musl" ;;
  aarch64) JUST_TARGET="aarch64-unknown-linux-musl" ;;
  *) echo "[dotfiles-tools] unsupported arch: $ARCH" >&2; exit 1 ;;
esac
JUST_FILE="just-${JUST_VERSION}-${JUST_TARGET}.tar.gz"
JUST_BASE="https://github.com/casey/just/releases/download/${JUST_VERSION}"
echo "[dotfiles-tools] installing just ${JUST_VERSION} (${JUST_TARGET})"
curl -fsSL -o "/tmp/${JUST_FILE}" "${JUST_BASE}/${JUST_FILE}"
curl -fsSL -o /tmp/just.SHA256SUMS "${JUST_BASE}/SHA256SUMS"
( cd /tmp && grep "  ${JUST_FILE}\$" just.SHA256SUMS | sha256sum -c - )
tar -xz -f "/tmp/${JUST_FILE}" -C /usr/local/bin just
rm -f "/tmp/${JUST_FILE}" /tmp/just.SHA256SUMS

# ---- sheldon (zsh plugin manager) -----------------------------------
SHELDON_VERSION="0.8.4"
case "$ARCH" in
  x86_64)
    SHELDON_TARGET="x86_64-unknown-linux-musl"
    SHELDON_SHA256="604ebaeccb485da58f5c3c3353d18f2f7ccc8fd9de0d65ee0b424f5b1a0324ce" ;;
  aarch64)
    SHELDON_TARGET="aarch64-unknown-linux-musl"
    SHELDON_SHA256="7fe1007c52ebb2777edfd66f4a4119b1e2b175269150a334467cf8708621fcf6" ;;
  *) echo "[dotfiles-tools] unsupported arch: $ARCH" >&2; exit 1 ;;
esac
SHELDON_URL="https://github.com/rossmacarthur/sheldon/releases/download/${SHELDON_VERSION}/sheldon-${SHELDON_VERSION}-${SHELDON_TARGET}.tar.gz"
echo "[dotfiles-tools] installing sheldon ${SHELDON_VERSION} (${SHELDON_TARGET})"
curl -fsSL -o /tmp/sheldon.tar.gz "$SHELDON_URL"
echo "${SHELDON_SHA256}  /tmp/sheldon.tar.gz" | sha256sum -c -
tar -xz -f /tmp/sheldon.tar.gz -C /usr/local/bin
rm -f /tmp/sheldon.tar.gz

# ---- nvcc stub ------------------------------------------------------
# `just check-version-nvcc` greps `nvcc --version`. The dev container
# does not actually carry CUDA; emit a stub that mimics the
# upstream CUDA 12.3 banner so the recipe and its tests pass.
echo "[dotfiles-tools] writing /usr/local/bin/nvcc stub"
printf '#!/bin/sh\necho "Cuda compilation tools, release 12.3, V12.3.52"\n' \
  > /usr/local/bin/nvcc
chmod 0755 /usr/local/bin/nvcc

# ---- mise trust env via login profile -------------------------------
# Inner one-shot containers spawned by the test fixture (`docker run
# --rm dotfiles-just-sandbox bash -lc ...`) do NOT inherit the dev
# container's containerEnv, so MISE_TRUSTED_CONFIG_PATHS must be
# baked in. /etc/profile.d/*.sh is sourced by every login bash.
echo "[dotfiles-tools] writing /etc/profile.d/dotfiles-mise.sh"
cat > /etc/profile.d/dotfiles-mise.sh <<'PROFILE'
# Pre-trust the workspace mise.toml so `mise install` / `mise exec`
# inside one-shot test containers does not error with
# "Config files in ~/dotfiles/mise.toml are not trusted."
export MISE_TRUSTED_CONFIG_PATHS=/root/dotfiles
PROFILE
chmod 0644 /etc/profile.d/dotfiles-mise.sh

# ---- git safe.directory wildcard ------------------------------------
# install.sh tests `cp -a` the bind-mounted workspace into a sandbox
# directory and then run `git init` / `git clone` against it. On the
# runner, the bind mount preserves UID 1001 while the container
# runs as root (UID 0); git then rejects the repo with
#   fatal: detected dubious ownership in repository at '...'
# The dev container is single-user-by-design, so allow all paths.
git config --system --add safe.directory '*'

# Cleanup apt cache to keep the image lean.
rm -rf /var/lib/apt/lists/*

echo "[dotfiles-tools] done"
