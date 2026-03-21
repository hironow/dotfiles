#!/usr/bin/env bash
# lighthouse.sh - Lighthouse 4-category average
# Input: URL or file path
# Output: lighthouse_avg: N (0-100)
# Requires: Chrome/Chromium

set -euo pipefail

TARGET="$1"

# Resolve file paths to file:// URLs
if [[ ! "$TARGET" =~ ^https?:// ]]; then
  TARGET="file://$(cd "$(dirname "$TARGET")" && pwd)/$(basename "$TARGET")"
fi

result=$(npx --yes lighthouse "$TARGET" \
  --output=json \
  --quiet \
  --chrome-flags="--headless --no-sandbox --disable-gpu" \
  --only-categories=performance,accessibility,best-practices,seo 2>/dev/null)

avg=$(echo "$result" | node -e "
  const data = JSON.parse(require('fs').readFileSync('/dev/stdin', 'utf8'));
  const cats = data.categories || {};
  const scores = Object.values(cats).map(c => c.score).filter(s => s !== null);
  const avg = scores.length > 0 ? Math.round(scores.reduce((a,b) => a+b, 0) / scores.length * 100) : 0;
  console.log(avg);
" 2>/dev/null || echo "0")

echo "lighthouse_avg: $avg"
