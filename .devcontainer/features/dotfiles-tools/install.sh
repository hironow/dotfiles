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
#       * gcloud:  Google apt repo (GPG signature + fingerprint pin)
#       * mise:    jdx apt repo  (GPG signature + fingerprint pin)
#       * uv:      .sha256 sidecar + GitHub attestation (SLSA provenance, sigstore)
#       * just:    SHA256SUMS bulk file (no upstream signature; SHA only)
#       * sheldon: pinned SHA256 hardcoded per arch (no upstream signature)
#
# The split is documented in docs/adr/0001-devcontainer-debian-features.md.
# `gh attestation verify` covers uv because astral-sh signs releases via
# GitHub Actions OIDC. casey/just and rossmacarthur/sheldon do not currently
# publish SLSA attestations, so the SHA pin is the strongest assertion we
# can make against artifact integrity until they do.
set -euo pipefail

ARCH=$(uname -m)
export DEBIAN_FRONTEND=noninteractive

# ---- system tools (shellcheck, jq) ----------------------------------
# `just lint` / `just check` invoke `mise x -- shellcheck` which
# falls through to system PATH. shellcheck and jq are apt packages,
# install them up front.
echo "[dotfiles-tools] installing apt prerequisites"
apt-get update -y
apt-get install -y --no-install-recommends \
  apt-transport-https ca-certificates gnupg curl shellcheck jq

# Helper: import an apt-repo GPG key only after verifying its
# fingerprint. Without this, a TOFU fetch from the same TLS
# endpoint that distributes the package would let a compromised
# mirror swap key + package in lock-step. Fingerprints are
# hardcoded below per vendor.
import_apt_key_with_fingerprint() {
  # args: <url> <expected-fingerprint> <output-keyring-path>
  local url="$1" expected="$2" out="$3"
  local tmp_armored="/tmp/dotfiles-apt-key.armored"
  local tmp_keyring="/tmp/dotfiles-apt-key.gpg"
  rm -f "$tmp_armored" "$tmp_keyring"
  curl -fsSL -o "$tmp_armored" "$url"
  gpg --no-default-keyring --keyring "$tmp_keyring" --import "$tmp_armored" 2>/dev/null
  local actual
  actual=$(gpg --no-default-keyring --keyring "$tmp_keyring" \
    --list-keys --with-colons | awk -F: '/^fpr:/ { print $10; exit }')
  if [ "$actual" != "$expected" ]; then
    echo "[dotfiles-tools] GPG fingerprint mismatch for $url" >&2
    echo "  expected: $expected" >&2
    echo "  actual:   $actual" >&2
    rm -f "$tmp_armored" "$tmp_keyring"
    exit 1
  fi
  install -m 0644 "$tmp_keyring" "$out"
  rm -f "$tmp_armored" "$tmp_keyring"
}

# ---- Google Cloud SDK -----------------------------------------------
# Fingerprint published by Google at
# https://cloud.google.com/sdk/docs/install#deb (apt-key fingerprint).
echo "[dotfiles-tools] installing Google Cloud SDK from apt repo"
import_apt_key_with_fingerprint \
  https://packages.cloud.google.com/apt/doc/apt-key.gpg \
  35BAA0B33E9EB396F59CA838C0BA5CE6DC6315A3 \
  /usr/share/keyrings/cloud.google.gpg
echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
  > /etc/apt/sources.list.d/google-cloud-sdk.list
apt-get update -y
apt-get install -y --no-install-recommends google-cloud-cli

# ---- mise (rtx-style version manager) -------------------------------
# Fingerprint from https://mise.jdx.dev/installing-mise.html#apt.
echo "[dotfiles-tools] installing mise from apt repo"
install -d -m 0755 /etc/apt/keyrings
import_apt_key_with_fingerprint \
  https://mise.jdx.dev/gpg-key.pub \
  24853EC9F655CE80B48E6C3A8B81C9D17413A06D \
  /etc/apt/keyrings/mise-archive-keyring.gpg
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
# Defense in depth: astral-sh signs uv release artifacts via
# GitHub Actions OIDC (sigstore-backed). `gh attestation verify`
# checks the SLSA provenance attestation, closing the SHA-sidecar
# TOFU window. Skipped only if `gh` is somehow missing — the
# github-cli feature is in installsAfter so it is normally present.
if command -v gh >/dev/null 2>&1; then
  echo "[dotfiles-tools] verifying uv attestation (SLSA provenance)"
  gh attestation verify "/tmp/${UV_FILE}" --repo astral-sh/uv \
    --predicate-type "https://slsa.dev/provenance/v1"
else
  echo "[dotfiles-tools] gh CLI absent; uv attestation verify SKIPPED" >&2
fi
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

# ---- mise env via login profile -------------------------------------
# Inner one-shot containers spawned by the test fixture (`docker run
# --rm dotfiles-just-sandbox bash -lc ...`) do NOT inherit the dev
# container's containerEnv. Bake the mise env into /etc/profile.d so
# every login shell (and its child processes, including git hooks)
# picks it up.
echo "[dotfiles-tools] writing /etc/profile.d/dotfiles-mise.sh"
cat > /etc/profile.d/dotfiles-mise.sh <<'PROFILE'
# Pre-trust ONLY the workspace mise.toml and install.sh's sandbox
# DOTPATH. Earlier revisions used MISE_TRUSTED_CONFIG_PATHS=/root
# but that exposed the entire home tree as a trusted config path,
# which is a wider trust boundary than the migration needs.
# See GHSA-436v-8fw5-4mj8 / CVE-2026-35533 — trust paths under
# mise should be scoped tightly.
export MISE_TRUSTED_CONFIG_PATHS=/root/dotfiles:/root/sandbox/dotfiles-fresh

# Add mise's shim directory to PATH so tools managed by mise.toml
# (prek, markdownlint-cli2, vp, ...) are reachable without a `mise
# exec` wrapper. Critical for git hooks installed by `prek install`
# — the pre-commit hook execs `prek` directly and sh -c hooks do
# not source profile.d again, so PATH must already carry the shim.
case ":$PATH:" in
  *":/root/.local/share/mise/shims:"*) ;;
  *) export PATH="/root/.local/share/mise/shims:$PATH" ;;
esac
PROFILE
chmod 0644 /etc/profile.d/dotfiles-mise.sh

# ---- git safe.directory (scoped) ------------------------------------
# install.sh tests `cp -a` the bind-mounted workspace into a sandbox
# directory and then run `git init` / `git clone` against it. On the
# runner, the bind mount preserves UID 1001 while the container
# runs as root (UID 0); git then rejects the repo with
#   fatal: detected dubious ownership in repository at '...'
# Earlier revisions allowlisted '*' which disabled the protection
# globally. List only the specific paths the dev container ever
# operates on instead.
git config --system --add safe.directory /root/dotfiles
git config --system --add safe.directory /root/sandbox/dotfiles-fresh

# ---- pre-install mise.toml tools ------------------------------------
# Bake mise.toml's tool versions into the saved image so test
# containers don't re-download every run. Versions pinned to what
# mise resolves "latest" to today; mise install at runtime can
# fetch newer versions if mise.toml advances.
echo "[dotfiles-tools] pre-installing mise.toml tools at build time"
mkdir -p /tmp/mise-prebuild
cat > /tmp/mise-prebuild/mise.toml <<'EOF'
[tools]
just = "1.50.0"
markdownlint-cli2 = "0.22.1"
prek = "0.3.11"
uv = "0.11.8"
vp = "0.1.20"
EOF
(
  cd /tmp/mise-prebuild
  MISE_TRUSTED_CONFIG_PATHS=/tmp/mise-prebuild mise install
)
rm -rf /tmp/mise-prebuild
MISE_TRUSTED_CONFIG_PATHS=/tmp mise reshim || true

# Cleanup apt cache to keep the image lean.
rm -rf /var/lib/apt/lists/*

echo "[dotfiles-tools] done"
