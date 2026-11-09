#!/usr/bin/env bash
set -euo pipefail
if [[ "${DOTFILES_E2E_REQUIRED:-}" == 1 && -z "${DOTFILES_PODMAN_RUN_MANIFEST:-}" ]]; then
  echo "Mandatory tests require DOTFILES_PODMAN_RUN_MANIFEST; refusing shared resources" >&2
  exit 2
fi

if [[ -n "${DOTFILES_PODMAN_RUN_MANIFEST:-}" ]]; then
  cd "$(dirname "${BASH_SOURCE[0]}")/.."
  exec uv run --frozen python -m tests.utils.isolation cleanup --manifest "$DOTFILES_PODMAN_RUN_MANIFEST"
fi
export PODMAN_COMPOSE_PROVIDER=podman-compose

# Stop emulator services gracefully.
# Usage: bash scripts/stop-services.sh

# ─── Dependency checks (soft fail) ───
command -v podman >/dev/null 2>&1 || { echo "podman not found. Nothing to stop." >&2; exit 0; }
podman compose --in-pod=false version >/dev/null 2>&1 || { echo "podman compose --in-pod=false not available. Nothing to stop." >&2; exit 0; }

# Show running containers if any
if podman compose --in-pod=false ps --quiet 2>/dev/null | grep -q .; then
  echo "📦 Currently running containers:"
  podman compose --in-pod=false ps
else
  echo "ℹ️  No emulator containers are running"
  exit 0
fi

echo "🛑 Stopping containers..."
# `podman compose --in-pod=false down` is profile-gated: with no profile active it only stops
# the default (lite) services and leaves profiled heavy containers running.
# Enable every profile (full covers all capability services, cli the helpers)
# so a stop after `emu-up-full` / `emu-up-group` tears the whole stack down.
COMPOSE_PROFILES=full,cli podman compose --in-pod=false down --remove-orphans
echo "✅ All emulators stopped."
