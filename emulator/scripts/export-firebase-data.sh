#!/usr/bin/env bash
set -euo pipefail

# Export Firebase emulator data if the service is running.
# Usage: bash scripts/export-firebase-data.sh [service] [export_path]

SERVICE="${1:-firebase-emulator}"
EXPORT_PATH="${2:-/firebase/data}"

# ─── Dependency checks (soft fail) ───
command -v docker >/dev/null 2>&1 || { echo "docker not found; skipping" >&2; exit 0; }
docker compose version >/dev/null 2>&1 || { echo "docker compose not available; skipping" >&2; exit 0; }

# Only attempt export if container is running
if docker ps --format '{{.Names}}' | grep -qx "$SERVICE"; then
  echo "📤 Exporting Firebase data from ${SERVICE} to ${EXPORT_PATH} ..."
  if docker compose exec -T "$SERVICE" firebase emulators:export "$EXPORT_PATH" --force 2>/dev/null; then
    echo "✅ Firebase data export completed."
  else
    echo "⚠️  Firebase data export failed or not supported; continuing."
  fi
else
  echo "ℹ️  ${SERVICE} is not running; skipping export."
fi
