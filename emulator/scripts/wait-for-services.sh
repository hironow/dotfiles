#!/usr/bin/env bash
set -euo pipefail

# Idempotent waiter for emulator services.
# Usage: bash scripts/wait-for-services.sh [--default <sec>] [--a2a <sec>] [--mcp <sec>] [--postgres <sec>]

# ─── Configurable ports (override via environment) ───
: "${FIREBASE_UI_PORT:=4000}"
: "${ELASTICSEARCH_PORT:=9200}"
: "${QDRANT_REST_PORT:=6333}"
: "${NEO4J_HTTP_PORT:=7474}"
: "${A2A_INSPECTOR_PORT:=8081}"
: "${MCP_INSPECTOR_PORT:=6274}"
: "${MLFLOW_PORT:=5252}"
: "${SPANNER_GRPC_PORT:=9010}"
: "${PGADAPTER_PORT:=55432}"
: "${BIGTABLE_PORT:=8086}"
: "${POSTGRES_PORT:=5433}"

# ─── Timeout defaults ───
DEFAULT_WAIT=30
A2A_WAIT=60
MCP_WAIT=60
POSTGRES_WAIT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --default)  DEFAULT_WAIT="${2:-30}"; shift 2 ;;
    --a2a)      A2A_WAIT="${2:-60}"; shift 2 ;;
    --mcp)      MCP_WAIT="${2:-60}"; shift 2 ;;
    --postgres) POSTGRES_WAIT="${2:-60}"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done
POSTGRES_WAIT="${POSTGRES_WAIT:-$DEFAULT_WAIT}"

echo "Waiting for emulator services..."

# ─── Wait functions ───
wait_http() {
  local name="$1" url="$2" max="${3:-$DEFAULT_WAIT}"
  echo "- Waiting for ${name} at ${url}"
  for ((i=1; i<=max; i++)); do
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null || echo "000")
    [[ "$code" =~ ^[23] ]] && { echo "  ${name} is ready (HTTP ${code})"; return 0; }
    sleep 1
  done
  echo "  ERROR: ${name} not ready in time" >&2
  return 1
}

wait_tcp() {
  local name="$1" host="$2" port="$3" max="${4:-$DEFAULT_WAIT}"
  echo "- Waiting for ${name} at ${host}:${port}"
  for ((i=1; i<=max; i++)); do
    (echo >/dev/tcp/"$host"/"$port") 2>/dev/null && { echo "  ${name} is ready"; return 0; }
    sleep 1
  done
  echo "  ERROR: ${name} not ready in time" >&2
  return 1
}

wait_postgres() {
  local name="$1" host="$2" port="$3" max="${4:-$DEFAULT_WAIT}"
  local restart_count=0
  echo "- Waiting for ${name} at ${host}:${port}"
  for ((i=1; i<=max; i++)); do
    local status
    status=$(docker inspect -f '{{.State.Status}}' postgres-18 2>/dev/null || echo "not-found")
    case "$status" in
      running)
        docker exec postgres-18 pg_isready -U postgres >/dev/null 2>&1 && { echo "  ${name} is ready"; return 0; }
        restart_count=0 ;;
      restarting)
        ((++restart_count >= 5)) && { echo "  ERROR: ${name} in restart loop" >&2; docker logs postgres-18 --tail 30 >&2; return 1; } ;;
      exited|dead)
        echo "  ERROR: ${name} stopped (${status})" >&2; docker logs postgres-18 --tail 30 >&2; return 1 ;;
      not-found)
        echo "  ERROR: postgres-18 container not found" >&2; return 1 ;;
    esac
    sleep 1
  done
  echo "  ERROR: ${name} not ready in time" >&2
  docker logs postgres-18 --tail 30 >&2 || true
  return 1
}

wait_elasticsearch() {
  local name="$1" url="$2" max="${3:-$DEFAULT_WAIT}"
  echo "- Waiting for ${name} at ${url}"
  for ((i=1; i<=max; i++)); do
    local resp
    resp=$(curl -s "$url" 2>/dev/null || true)
    if [[ "$resp" == *'"status":"green"'* || "$resp" == *'"status":"yellow"'* ]] && \
       [[ "$resp" == *'"initializing_shards":0'* ]]; then
      echo "  ${name} is ready (shards initialized)"
      return 0
    fi
    sleep 1
  done
  echo "  ERROR: ${name} not ready in time" >&2
  return 1
}

# ─── Wait for each service ───
wait_http          "Firebase UI"      "http://localhost:${FIREBASE_UI_PORT}"                       "$DEFAULT_WAIT"
wait_elasticsearch "Elasticsearch"    "http://localhost:${ELASTICSEARCH_PORT}/_cluster/health"     "$DEFAULT_WAIT"
wait_http          "Qdrant"           "http://localhost:${QDRANT_REST_PORT}/healthz"               "$DEFAULT_WAIT"
wait_http          "Neo4j HTTP"       "http://localhost:${NEO4J_HTTP_PORT}"                        "$DEFAULT_WAIT"
wait_http          "A2A Inspector"    "http://localhost:${A2A_INSPECTOR_PORT}"                     "$A2A_WAIT"
wait_http          "MCP Inspector"    "http://localhost:${MCP_INSPECTOR_PORT}"                     "$MCP_WAIT"
wait_http          "MLflow"           "http://localhost:${MLFLOW_PORT}/"                           "$DEFAULT_WAIT"
wait_tcp           "Spanner gRPC"     localhost "$SPANNER_GRPC_PORT"                               "$DEFAULT_WAIT"
wait_tcp           "pgAdapter"        localhost "$PGADAPTER_PORT"                                  "$DEFAULT_WAIT"
wait_tcp           "Bigtable"         localhost "$BIGTABLE_PORT"                                   "$DEFAULT_WAIT"
wait_postgres      "PostgreSQL 18"    localhost "$POSTGRES_PORT"                                   "$POSTGRES_WAIT"

echo "All targeted services reported ready."
