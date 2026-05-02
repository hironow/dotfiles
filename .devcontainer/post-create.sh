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
# hermetic. The first `mise install` needs network to resolve
# `latest` against the GitHub API and download tool binaries — so we
# explicitly clear the flag for this single invocation. After this
# script exits, the containerEnv setting carries over to every
# subsequent process.
echo "[post-create] mise install (mise.toml tools)"
cd /root/dotfiles
mise trust mise.toml >/dev/null 2>&1 || true
touch mise.lock
MISE_OFFLINE=0 mise install

echo "[post-create] done"
