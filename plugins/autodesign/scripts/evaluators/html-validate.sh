#!/usr/bin/env bash
# html-validate.sh - HTML validation
# Input: file path
# Output: validation_errors: N
# No Chrome required

set -euo pipefail

TARGET="$1"

result=$(npx --yes html-validate "$TARGET" --formatter json 2>/dev/null || echo '{"results":[]}')
errors=$(echo "$result" | node -e "
  const data = JSON.parse(require('fs').readFileSync('/dev/stdin', 'utf8'));
  const results = data.results || [];
  let count = 0;
  for (const r of results) {
    count += (r.messages || []).filter(m => m.severity === 2).length;
  }
  console.log(count);
" 2>/dev/null || echo "0")

echo "validation_errors: $errors"
