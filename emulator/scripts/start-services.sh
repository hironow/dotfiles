#!/usr/bin/env bash
set -euo pipefail

# Start compose services. Idempotent.
# Usage: bash scripts/start-services.sh [--no-build]

NO_BUILD=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-build) NO_BUILD=true; shift ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

# ─── Dependency checks ───
command -v docker >/dev/null 2>&1 || { echo "docker not found" >&2; exit 127; }
docker compose version >/dev/null 2>&1 || { echo "docker compose not available" >&2; exit 127; }

# Create shared network if needed (for telemetry integration)
docker network inspect shared-otel-net >/dev/null 2>&1 || {
  echo "Creating shared-otel-net network..."
  docker network create shared-otel-net
}

if $NO_BUILD; then
  docker compose up -d --no-build
else
  docker compose up -d
fi

echo "Services started (detached)."
