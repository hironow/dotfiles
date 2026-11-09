#!/usr/bin/env bash
set -euo pipefail
if [[ -n "${DOTFILES_PODMAN_RUN_MANIFEST:-}" || "${DOTFILES_E2E_REQUIRED:-}" == 1 ]]; then
  echo "Isolated runs export to disposable data on container exit; shared export is refused" >&2
  exit 2
fi
export PODMAN_COMPOSE_PROVIDER=podman-compose

# Export Firebase emulator data if the service is running.
# Usage: bash scripts/export-firebase-data.sh [service] [export_path]

SERVICE="${1:-firebase-emulator}"
EXPORT_PATH="${2:-/firebase/data}"

# ─── Dependency checks (soft fail) ───
command -v podman >/dev/null 2>&1 || { echo "podman not found; skipping" >&2; exit 0; }
podman compose --in-pod=false version >/dev/null 2>&1 || { echo "podman compose --in-pod=false not available; skipping" >&2; exit 0; }

# Only attempt export if container is running
if podman ps --format '{{.Names}}' | grep -qx "$SERVICE"; then
  echo "📤 Exporting Firebase data from ${SERVICE} to ${EXPORT_PATH} ..."
  if podman compose --in-pod=false exec -T "$SERVICE" firebase emulators:export "$EXPORT_PATH" --force 2>/dev/null; then
    echo "✅ Firebase data export completed."
  else
    echo "⚠️  Firebase data export failed or not supported; continuing."
  fi
else
  echo "ℹ️  ${SERVICE} is not running; skipping export."
fi
