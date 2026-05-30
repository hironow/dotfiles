#!/usr/bin/env bash
set -euo pipefail

# Stop emulator services gracefully.
# Usage: bash scripts/stop-services.sh

# ─── Dependency checks (soft fail) ───
command -v docker >/dev/null 2>&1 || { echo "docker not found. Nothing to stop." >&2; exit 0; }
docker compose version >/dev/null 2>&1 || { echo "docker compose not available. Nothing to stop." >&2; exit 0; }

# Show running containers if any
if docker compose ps --quiet 2>/dev/null | grep -q .; then
  echo "📦 Currently running containers:"
  docker compose ps
else
  echo "ℹ️  No emulator containers are running"
  exit 0
fi

echo "🛑 Stopping containers..."
# `docker compose down` is profile-gated: with no profile active it only stops
# the default (lite) services and leaves profiled heavy containers running.
# Enable every profile (full covers all capability services, cli the helpers)
# so a stop after `emu-up-full` / `emu-up-group` tears the whole stack down.
COMPOSE_PROFILES=full,cli docker compose down --remove-orphans
echo "✅ All emulators stopped."
