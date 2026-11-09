#!/usr/bin/env bash
set -euo pipefail
if [[ -n "${DOTFILES_PODMAN_RUN_MANIFEST:-}" || "${DOTFILES_E2E_REQUIRED:-}" == 1 ]]; then
  echo "Isolated builds run through tests.utils.isolation start, not the shared prebuild helper" >&2
  exit 2
fi
export PODMAN_COMPOSE_PROVIDER=podman-compose

# Pre-build selected compose images to speed up startup and CI waits.
# Usage: bash scripts/prebuild-images.sh [services...]

# ─── Dependency checks ───
command -v podman >/dev/null 2>&1 || { echo "podman not found" >&2; exit 127; }
podman compose --in-pod=false version >/dev/null 2>&1 || { echo "podman compose --in-pod=false not available" >&2; exit 127; }

# ─── Default services to build ───
declare -a services=(a2a-inspector firebase-emulator mcp-inspector)
(( $# > 0 )) && services=("$@")

echo "Pre-building images: ${services[*]}"
for svc in "${services[@]}"; do
  echo "▶️  Building $svc"
  podman compose --in-pod=false build "$svc"
done
echo "Done."
