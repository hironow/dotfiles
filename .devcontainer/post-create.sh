#!/usr/bin/env bash
# Dev container onCreateCommand — install vendor-official tools that
# are not covered by Microsoft devcontainer features.
#
# Trust policy:
#   - features in devcontainer.json: ONLY ghcr.io/devcontainers/features/* (Microsoft)
#   - tools below: vendor-official artifacts only, NEVER `curl | bash`
#       * gcloud:  Google apt repo (GPG-verified, packages.cloud.google.com)
#       * mise:    jdx apt repo  (GPG-verified, mise.jdx.dev/deb)
#       * uv:      astral-sh GitHub release + .sha256 sidecar
#       * just:    casey/just GitHub release + SHA256SUMS bulk file
#       * sheldon: rossmacarthur/sheldon GitHub release + GH API digest (pinned)
#
# Adding a tool? Pin a version, verify a hash, and never introduce
# `curl | sh` patterns — semgrep flags them with CWE-95.
set -euo pipefail

ARCH=$(uname -m)

# ---- Google Cloud SDK -----------------------------------------------
# Google's debian apt repo. The GPG key is fetched once and pinned
# under /usr/share/keyrings, so subsequent apt updates verify
# package signatures.
if ! command -v gcloud >/dev/null 2>&1; then
  echo "[post-create] installing Google Cloud SDK from apt repo"
  apt-get update -y
  apt-get install -y --no-install-recommends apt-transport-https ca-certificates gnupg curl
  curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
    | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg
  echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
    > /etc/apt/sources.list.d/google-cloud-sdk.list
  apt-get update -y
  apt-get install -y --no-install-recommends google-cloud-cli
fi

# ---- mise (rtx-style version manager) -------------------------------
# jdx's official apt repository at mise.jdx.dev. GPG key pinned.
if ! command -v mise >/dev/null 2>&1; then
  echo "[post-create] installing mise from apt repo"
  install -d -m 0755 /etc/apt/keyrings
  curl -fsSL https://mise.jdx.dev/gpg-key.pub \
    | gpg --dearmor -o /etc/apt/keyrings/mise-archive-keyring.gpg
  echo "deb [signed-by=/etc/apt/keyrings/mise-archive-keyring.gpg arch=amd64,arm64] https://mise.jdx.dev/deb stable main" \
    > /etc/apt/sources.list.d/mise.list
  apt-get update -y
  apt-get install -y --no-install-recommends mise
fi

# ---- uv (Python package manager) ------------------------------------
# Astral publishes a .sha256 sidecar alongside each release tarball.
if ! command -v uv >/dev/null 2>&1; then
  UV_VERSION="0.11.8"
  case "$ARCH" in
    x86_64)  UV_TARGET="x86_64-unknown-linux-gnu" ;;
    aarch64) UV_TARGET="aarch64-unknown-linux-gnu" ;;
    *) echo "[post-create] unsupported arch: $ARCH" >&2; exit 1 ;;
  esac
  UV_FILE="uv-${UV_TARGET}.tar.gz"
  UV_BASE="https://github.com/astral-sh/uv/releases/download/${UV_VERSION}"
  echo "[post-create] installing uv ${UV_VERSION} (${UV_TARGET})"
  # The .sha256 sidecar references the file by its original name, so
  # download into /tmp keeping the same basename and run sha256sum -c
  # from that directory.
  curl -fsSL -o "/tmp/${UV_FILE}" "${UV_BASE}/${UV_FILE}"
  curl -fsSL -o "/tmp/${UV_FILE}.sha256" "${UV_BASE}/${UV_FILE}.sha256"
  ( cd /tmp && sha256sum -c "${UV_FILE}.sha256" )
  tar -xz -f "/tmp/${UV_FILE}" -C /tmp --strip-components=1
  install -m 0755 /tmp/uv /usr/local/bin/uv
  install -m 0755 /tmp/uvx /usr/local/bin/uvx
  rm -f "/tmp/${UV_FILE}" "/tmp/${UV_FILE}.sha256" /tmp/uv /tmp/uvx
fi

# ---- just (command runner) ------------------------------------------
# casey/just publishes a single SHA256SUMS file covering every asset
# in the release. Download it, then `sha256sum -c` against the line
# matching our tarball.
if ! command -v just >/dev/null 2>&1; then
  JUST_VERSION="1.40.0"
  case "$ARCH" in
    x86_64)  JUST_TARGET="x86_64-unknown-linux-musl" ;;
    aarch64) JUST_TARGET="aarch64-unknown-linux-musl" ;;
    *) echo "[post-create] unsupported arch: $ARCH" >&2; exit 1 ;;
  esac
  JUST_FILE="just-${JUST_VERSION}-${JUST_TARGET}.tar.gz"
  JUST_BASE="https://github.com/casey/just/releases/download/${JUST_VERSION}"
  echo "[post-create] installing just ${JUST_VERSION} (${JUST_TARGET})"
  curl -fsSL -o "/tmp/${JUST_FILE}" "${JUST_BASE}/${JUST_FILE}"
  curl -fsSL -o /tmp/just.SHA256SUMS "${JUST_BASE}/SHA256SUMS"
  ( cd /tmp && grep "  ${JUST_FILE}\$" just.SHA256SUMS | sha256sum -c - )
  tar -xz -f "/tmp/${JUST_FILE}" -C /usr/local/bin just
  rm -f "/tmp/${JUST_FILE}" /tmp/just.SHA256SUMS
fi

# ---- sheldon (zsh plugin manager) -----------------------------------
# Vendor does not publish a sums file; pin the GitHub-attested asset
# digest by version so a tampered release surfaces as a checksum
# mismatch.
if ! command -v sheldon >/dev/null 2>&1; then
  SHELDON_VERSION="0.8.4"
  case "$ARCH" in
    x86_64)
      SHELDON_TARGET="x86_64-unknown-linux-musl"
      SHELDON_SHA256="604ebaeccb485da58f5c3c3353d18f2f7ccc8fd9de0d65ee0b424f5b1a0324ce" ;;
    aarch64)
      SHELDON_TARGET="aarch64-unknown-linux-musl"
      SHELDON_SHA256="7fe1007c52ebb2777edfd66f4a4119b1e2b175269150a334467cf8708621fcf6" ;;
    *) echo "[post-create] unsupported arch: $ARCH" >&2; exit 1 ;;
  esac
  SHELDON_URL="https://github.com/rossmacarthur/sheldon/releases/download/${SHELDON_VERSION}/sheldon-${SHELDON_VERSION}-${SHELDON_TARGET}.tar.gz"
  echo "[post-create] installing sheldon ${SHELDON_VERSION} (${SHELDON_TARGET})"
  curl -fsSL -o /tmp/sheldon.tar.gz "$SHELDON_URL"
  echo "${SHELDON_SHA256}  /tmp/sheldon.tar.gz" | sha256sum -c -
  tar -xz -f /tmp/sheldon.tar.gz -C /usr/local/bin
  rm -f /tmp/sheldon.tar.gz
fi

# ---- mise.toml tools provisioning -----------------------------------
# MISE_OFFLINE=1 is set in containerEnv to keep `just test` runs
# hermetic. But the *first* `mise install` needs network to resolve
# `latest` against the GitHub API and download tool binaries — so
# we explicitly clear the flag here. After this script exits, the
# containerEnv setting remains in force for every subsequent process.
echo "[post-create] mise install (mise.toml tools)"
cd /root/dotfiles
mise trust mise.toml >/dev/null 2>&1 || true
touch mise.lock
MISE_OFFLINE=0 mise install

echo "[post-create] done"
