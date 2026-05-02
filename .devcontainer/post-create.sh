#!/usr/bin/env bash
# Dev container onCreateCommand — runtime steps that depend on the
# bind-mounted workspace (devcontainer features cannot reach
# /root/dotfiles because the bind mount is established AFTER build).
#
# Build-time tool installation (gcloud, mise, uv, just, sheldon) lives
# in the local feature .devcontainer/features/dotfiles-tools/ which
# runs during devcontainer build and bakes binaries into the saved
# image.
set -euo pipefail

# MISE_OFFLINE=1 is set in containerEnv to keep `just test` runs
# hermetic. Per ADR 0006 the workspace mise.toml is fully pinned
# and the data dir lives at /opt/mise (outside any bind-mounted
# overlay), so `mise install` here only needs to verify the
# already-installed cache matches the pinned versions — no
# network required.
echo "[post-create] mise install (mise.toml tools, MISE_OFFLINE=1)"
cd /root/dotfiles
mise trust mise.toml >/dev/null 2>&1 || true
touch mise.lock
MISE_DATA_DIR=/opt/mise mise install

echo "[post-create] done"
