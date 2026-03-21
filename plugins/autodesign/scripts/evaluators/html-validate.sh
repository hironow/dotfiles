#!/usr/bin/env bash
# html-validate.sh - HTML validation
# Input: file path
# Output: validation_errors: N
# No Chrome required

set -euo pipefail

TARGET="$1"

result=$(bun x html-validate "$TARGET" --formatter json 2>/dev/null || echo '{"results":[]}')
errors=$(echo "$result" | bun -e "
  const data = JSON.parse(await Bun.stdin.text());
  const results = data.results || [];
  let count = 0;
  for (const r of results) {
    count += (r.messages || []).filter(m => m.severity === 2).length;
  }
  console.log(count);
" 2>/dev/null || echo "0")

echo "validation_errors: $errors"
