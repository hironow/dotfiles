#!/usr/bin/env bash
set -euo pipefail
CONFIG="design-config.yaml"
if [[ ! -f "$CONFIG" ]]; then
  exit 0
fi
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"file_path"[[:space:]]*:[[:space:]]*"//' | sed 's/"$//' || echo "")
if [[ -z "$FILE_PATH" ]]; then
  exit 0
fi
BASENAME=$(basename "$FILE_PATH")
if [[ "$BASENAME" == "design-results.tsv" || "$BASENAME" == "run.log" ]]; then
  exit 0
fi
IN_SCOPE=false
while IFS= read -r line; do
  target=$(echo "$line" | sed -n 's/^[[:space:]]*-[[:space:]]*"\{0,1\}\([^"]*\)"\{0,1\}$/\1/p')
  if [[ -n "$target" && "$FILE_PATH" == *"$target"* ]]; then
    IN_SCOPE=true
    break
  fi
done < <(sed -n '/^target_files:/,/^[^ ]/p' "$CONFIG" | sed '$d')
if [[ "$IN_SCOPE" == "true" ]]; then
  exit 0
fi
# Out of scope: escalate to the user instead of auto-approving. permissionDecision
# "allow" would BYPASS the normal permission prompt; "ask" surfaces a stray
# non-target write so it cannot silently invalidate the design loop.
cat <<'EOF'
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"This file is outside the design target scope. Confirm before proceeding."}}
EOF
