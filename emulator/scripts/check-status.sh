#!/usr/bin/env bash
set -euo pipefail
if [[ "${DOTFILES_E2E_REQUIRED:-}" == 1 && -z "${DOTFILES_PODMAN_RUN_MANIFEST:-}" ]]; then
  echo "Mandatory tests require DOTFILES_PODMAN_RUN_MANIFEST; refusing shared resources" >&2
  exit 2
fi

if [[ -n "${DOTFILES_PODMAN_RUN_MANIFEST:-}" ]]; then
  cd "$(dirname "${BASH_SOURCE[0]}")/.."
  exec uv run --frozen python -m tests.utils.isolation status --manifest "$DOTFILES_PODMAN_RUN_MANIFEST"
fi
export PODMAN_COMPOSE_PROVIDER=podman-compose

# Show the current status of emulator containers and their host endpoints.
# Idempotent, read-only.
# Usage: bash scripts/check-status.sh

# ─── Configurable ports (override via environment) ───
: "${FIREBASE_UI_PORT:=4000}"
: "${BIGTABLE_PORT:=8086}"
: "${SPANNER_GRPC_PORT:=9010}"
: "${PGADAPTER_PORT:=55432}"
: "${NEO4J_HTTP_PORT:=7474}"
: "${ELASTICSEARCH_PORT:=9200}"
: "${QDRANT_REST_PORT:=6333}"
: "${A2A_INSPECTOR_PORT:=8081}"
: "${MCP_INSPECTOR_PORT:=6274}"
: "${MLFLOW_PORT:=5252}"
: "${POSTGRES_PORT:=5433}"

# Move to repo root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}/.."

# ─── Dependency checks ───
command -v podman >/dev/null 2>&1 || { echo "❌ podman not found" >&2; exit 127; }
podman compose --in-pod=false version >/dev/null 2>&1 || { echo "❌ podman compose --in-pod=false not available" >&2; exit 127; }
command -v curl >/dev/null 2>&1 || { echo "❌ curl not found" >&2; exit 127; }

# ─── Helper functions ───
container_status() {
  local out
  out=$(podman ps -a --filter name="^/${1}$" --format '{{.Status}}' 2>/dev/null || true)
  echo "${out:-not found}"
}

check_http() {
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" "$1" 2>/dev/null || echo "000")
  case "$code" in
    2*|3*) echo "✅ HTTP ${code}" ;;
    000)   echo "❌ no response" ;;
    *)     echo "⚠️  HTTP ${code}" ;;
  esac
}

check_tcp() {
  local host="${1%:*}" port="${1#*:}"
  if nc -z "$host" "$port" 2>/dev/null || (echo >/dev/tcp/"$host"/"$port") 2>/dev/null; then
    echo "✅ open"
  else
    echo "❌ closed"
  fi
}

report() {
  local label="$1" container="$2" mode="$3" target="$4"
  local cstat estat
  cstat=$(container_status "$container")
  if [[ "$mode" == http ]]; then
    estat=$(check_http "$target")
  else
    estat=$(check_tcp "$target")
  fi
  printf "%-18s | %-28s | %s\n" "$label" "$cstat" "$estat"
}

# ─── Output ───
echo "📦 Podman Compose services"
podman compose --in-pod=false ps || true
echo
echo "🔎 Emulator endpoints"
printf "%-18s | %-28s | %s\n" "Service" "Container status" "Endpoint check"
printf "%s\n" "------------------+------------------------------+-------------------------"

report "Firebase UI"       firebase-emulator      http  "http://localhost:${FIREBASE_UI_PORT}"
report "Bigtable gRPC"     bigtable-emulator      tcp   "localhost:${BIGTABLE_PORT}"
report "Spanner gRPC"      spanner-emulator       tcp   "localhost:${SPANNER_GRPC_PORT}"
report "pgAdapter"         pgadapter-emulator     tcp   "localhost:${PGADAPTER_PORT}"
report "Neo4j HTTP"        neo4j-emulator         http  "http://localhost:${NEO4J_HTTP_PORT}"
report "Elasticsearch"     elasticsearch-emulator http  "http://localhost:${ELASTICSEARCH_PORT}/_cluster/health"
report "Qdrant"            qdrant-emulator        http  "http://localhost:${QDRANT_REST_PORT}/healthz"
report "A2A Inspector"     a2a-inspector          http  "http://localhost:${A2A_INSPECTOR_PORT}"
report "MCP Inspector"     mcp-inspector          http  "http://localhost:${MCP_INSPECTOR_PORT}"
report "MLflow"            mlflow-server          http  "http://localhost:${MLFLOW_PORT}/"
report "PostgreSQL 18"     postgres-18            tcp   "localhost:${POSTGRES_PORT}"

echo
echo "Done."
