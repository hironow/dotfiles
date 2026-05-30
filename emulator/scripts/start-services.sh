#!/usr/bin/env bash
set -euo pipefail

# Start compose services. Idempotent.
#
# Usage: bash scripts/start-services.sh [--no-build] [SERVICE...]
#
#   (no SERVICE)  -> start the default (lite) profile: only services without a
#                    compose `profiles:` key (firebase + spanner + pgadapter +
#                    postgres = the GCP core).
#   SERVICE...    -> start exactly the named services (+ their depends_on).
#                    Naming a service activates it even if it sits behind a
#                    compose profile, so `start-services.sh firebase-emulator`
#                    brings up just Firebase.
#   COMPOSE_PROFILES=<a,b>  -> additionally start every service tagged with
#                    those profiles (compose reads this env natively), e.g.
#                    `COMPOSE_PROFILES=full` for the whole heavy stack.

NO_BUILD=false
SERVICES=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-build) NO_BUILD=true; shift ;;
    --) shift; SERVICES+=("$@"); break ;;
    -*) echo "Unknown flag: $1" >&2; exit 2 ;;
    *) SERVICES+=("$1"); shift ;;
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

# "${SERVICES[@]+...}" guards against an empty array tripping `set -u` on
# bash 3.2 (stock macOS); on an empty array it expands to nothing.
if $NO_BUILD; then
  docker compose up -d --no-build ${SERVICES[@]+"${SERVICES[@]}"}
else
  docker compose up -d ${SERVICES[@]+"${SERVICES[@]}"}
fi

if [[ ${#SERVICES[@]} -gt 0 ]]; then
  echo "Services started (detached): ${SERVICES[*]}"
else
  echo "Services started (detached): default profile${COMPOSE_PROFILES:+ + COMPOSE_PROFILES=$COMPOSE_PROFILES}."
fi
