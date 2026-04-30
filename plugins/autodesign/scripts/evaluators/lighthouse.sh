#!/usr/bin/env bash
# lighthouse.sh - Lighthouse 4-category average
# Input: URL or file path
# Output: lighthouse_avg: N (0-100)
# Requires: Chrome/Chromium, bun
#
# Uses bun to run lighthouse CLI directly, avoiding Node 24 ESM compat issues.
# For file paths, starts a temporary HTTP server (lighthouse works best with HTTP).

set -euo pipefail

TARGET="$1"
SERVER_PID=""

cleanup() {
  if [[ -n "$SERVER_PID" ]]; then
    kill "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# For file targets, start a temp HTTP server (lighthouse + file:// is unreliable)
if [[ ! "$TARGET" =~ ^https?:// ]]; then
  ABS_PATH="$(cd "$(dirname "$TARGET")" && pwd)/$(basename "$TARGET")"
  DIR="$(dirname "$ABS_PATH")"
  BASENAME="$(basename "$ABS_PATH")"
  PORT=18976
  # lsof returns one PID per line; word-splitting is intentional so kill
  # receives all of them as separate args.
  # shellcheck disable=SC2046
  kill $(lsof -ti:$PORT) 2>/dev/null || true
  sleep 0.3
  python3 -m http.server $PORT --directory "$DIR" &>/dev/null &
  SERVER_PID=$!
  sleep 1
  TARGET="http://localhost:${PORT}/${BASENAME}"
fi

# Resolve lighthouse CLI path (bun x caches to node_modules)
LH_CLI="$(find node_modules/lighthouse/cli -name 'index.js' -maxdepth 1 2>/dev/null | head -1)"
if [[ -z "$LH_CLI" || ! -f "$LH_CLI" ]]; then
  # Install lighthouse if not present
  bun add lighthouse 2>/dev/null
  LH_CLI="$(find node_modules/lighthouse/cli -name 'index.js' -maxdepth 1 2>/dev/null | head -1)"
fi

if [[ -z "$LH_CLI" || ! -f "$LH_CLI" ]]; then
  echo "lighthouse_avg: 0" >&2
  echo "lighthouse_avg: 0"
  exit 0
fi

# Run lighthouse via bun runtime (bypasses Node 24 ESM issues)
result=$(bun "$LH_CLI" "$TARGET" \
  --output=json \
  --quiet \
  --chrome-flags="--headless --no-sandbox --disable-gpu" \
  --only-categories=performance,accessibility,best-practices,seo 2>/dev/null) || true

avg=$(echo "$result" | bun -e "
  const data = JSON.parse(await Bun.stdin.text());
  const cats = data.categories || {};
  const scores = Object.values(cats).map(c => c.score).filter(s => s !== null);
  const avg = scores.length > 0 ? Math.round(scores.reduce((a,b) => a+b, 0) / scores.length * 100) : 0;
  console.log(avg);
" 2>/dev/null || echo "0")

echo "lighthouse_avg: $avg"
