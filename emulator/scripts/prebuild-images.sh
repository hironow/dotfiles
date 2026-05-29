#!/usr/bin/env bash
set -euo pipefail

# Pre-build selected compose images to speed up startup and CI waits.
# Usage: bash scripts/prebuild-images.sh [services...]

# ─── Dependency checks ───
command -v docker >/dev/null 2>&1 || { echo "docker not found" >&2; exit 127; }
docker compose version >/dev/null 2>&1 || { echo "docker compose not available" >&2; exit 127; }

# ─── Default services to build ───
declare -a services=(a2a-inspector firebase-emulator mcp-inspector)
(( $# > 0 )) && services=("$@")

echo "Pre-building images: ${services[*]}"
for svc in "${services[@]}"; do
  echo "▶️  Building $svc"
  docker compose build "$svc"
done
echo "Done."
