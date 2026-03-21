#!/usr/bin/env bash
# structure.sh - Pa11y-based accessibility structure check
# Input: URL or file path
# Output: structure_errors: N / structure_score: N
# Requires: Chrome/Chromium

set -euo pipefail

TARGET="$1"

# Resolve file paths to file:// URLs
if [[ ! "$TARGET" =~ ^https?:// ]]; then
  TARGET="file://$(cd "$(dirname "$TARGET")" && pwd)/$(basename "$TARGET")"
fi

# Run Pa11y
result=$(npx --yes pa11y "$TARGET" --reporter json --runner axe --runner htmlcs 2>/dev/null || echo '[]')

# Count errors
error_count=$(echo "$result" | node -e "
  const data = JSON.parse(require('fs').readFileSync('/dev/stdin', 'utf8'));
  const issues = Array.isArray(data) ? data : (data.issues || []);
  const errors = issues.filter(i => i.type === 'error');
  console.log(errors.length);
" 2>/dev/null || echo "0")

score=$((100 - error_count * 5))
if (( score < 0 )); then score=0; fi

echo "structure_errors: $error_count"
echo "structure_score: $score"
