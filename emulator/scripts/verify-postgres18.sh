#!/usr/bin/env bash
set -euo pipefail
if [[ -n "${DOTFILES_PODMAN_RUN_MANIFEST:-}" || "${DOTFILES_E2E_REQUIRED:-}" == 1 ]]; then
  echo "Use manifest-aware tests/test_postgres18_features.py for isolated database verification" >&2
  exit 2
fi
export PODMAN_COMPOSE_PROVIDER=podman-compose

# Verify basic PostgreSQL 18 features using psql inside the container.
# - Confirms server version
# - Checks for uuidv7() presence and calls it when available
# - Attempts a virtual generated column; falls back to stored if not supported
# Usage: bash scripts/verify-postgres18.sh

# ─── Configuration ───
SERVICE=postgres
DB=postgres
USER=postgres

# ─── Dependency checks ───
command -v podman >/dev/null 2>&1 || { echo "❌ podman not found" >&2; exit 127; }
podman compose --in-pod=false version >/dev/null 2>&1 || { echo "❌ podman compose --in-pod=false not available" >&2; exit 127; }

echo "🔎 Verifying PostgreSQL 18 features (service: ${SERVICE})"

# Ensure service is running
podman compose --in-pod=false ps --quiet "$SERVICE" 2>/dev/null | grep -q . || {
  echo "❌ Service '${SERVICE}' is not running. Start with: just emu-up or just emu-start" >&2
  exit 2
}

psql_cmd() {
  podman compose --in-pod=false exec -T "$SERVICE" psql -U "$USER" -d "$DB" -Atqc "$1"
}

# Version check
version=$(psql_cmd "show server_version;")
echo "• server_version: ${version}"
major=${version%%.*}
if [[ "$major" == "18" ]]; then
  echo "  ✅ Major version is 18"
else
  echo "  ⚠️  Major version is not 18 (got ${major})"
fi

# uuidv7() presence + sample value
has_uuidv7=$(psql_cmd "select exists (select 1 from pg_proc p join pg_namespace n on n.oid=p.pronamespace where p.proname='uuidv7' and n.nspname='pg_catalog');")
if [[ "$has_uuidv7" == "t" ]]; then
  echo "• uuidv7(): present"
  val=$(psql_cmd "select uuidv7();" || true)
  if [[ -n "${val:-}" ]]; then
    echo "  ✅ uuidv7() sample: ${val}"
  else
    echo "  ⚠️  uuidv7() call did not return a value"
  fi
else
  echo "• uuidv7(): not found"
fi

# Generated column test (try virtual, fallback to stored)
echo "• Generated column test"
psql_cmd "drop table if exists pg18_gen_test;" >/dev/null || true
if podman compose --in-pod=false exec -T "$SERVICE" psql -U "$USER" -d "$DB" -v ON_ERROR_STOP=1 \
    -c "create table pg18_gen_test(x int, y int generated always as (x*2) virtual);" >/dev/null 2>&1; then
  echo "  ✅ Virtual generated column supported"
else
  podman compose --in-pod=false exec -T "$SERVICE" psql -U "$USER" -d "$DB" -v ON_ERROR_STOP=1 \
    -c "create table pg18_gen_test(x int, y int generated always as (x*2) stored);" >/dev/null
  echo "  ⚠️  Virtual not available; created STORED generated column"
fi
podman compose --in-pod=false exec -T "$SERVICE" psql -U "$USER" -d "$DB" -v ON_ERROR_STOP=1 \
  -c "insert into pg18_gen_test(x) values (5);" >/dev/null
pair=$(psql_cmd "select x||'->'||y from pg18_gen_test limit 1;")
echo "  ▶︎ sample row: ${pair}"

echo "✅ Verification complete"
