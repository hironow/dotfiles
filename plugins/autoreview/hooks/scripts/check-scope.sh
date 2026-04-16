#!/usr/bin/env bash
# check-scope.sh - Verify Edit/Write target is within review scope
#
# Reads review-config.yaml to get target_paths list.
# If config does not exist, silently allows the operation.
# If target file is outside scope (and not review-results.tsv/review-scan.json),
# warns the user.
#
# Input: JSON on stdin with tool_input.file_path
# Output: JSON with "decision" field

set -euo pipefail

CONFIG="review-config.yaml"

# If no active review, allow silently
if [[ ! -f "$CONFIG" ]]; then
  echo '{"decision": "allow"}'
  exit 0
fi

# Extract file_path from stdin JSON
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"file_path"[[:space:]]*:[[:space:]]*"//' | sed 's/"$//' || echo "")

if [[ -z "$FILE_PATH" ]]; then
  echo '{"decision": "allow"}'
  exit 0
fi

# Get basename for whitelist check
BASENAME=$(basename "$FILE_PATH")

# Whitelist: review artifacts are always allowed
if [[ "$BASENAME" == "review-results.tsv" || "$BASENAME" == "review-scan.json" ]]; then
  echo '{"decision": "allow"}'
  exit 0
fi

# Extract target_paths from config (simple YAML parsing)
IN_SCOPE=false
while IFS= read -r line; do
  target=$(echo "$line" | sed -n 's/^[[:space:]]*-[[:space:]]*"\?\([^"]*\)"\?$/\1/p')
  if [[ -n "$target" ]]; then
    if [[ "$FILE_PATH" == *"$target"* ]]; then
      IN_SCOPE=true
      break
    fi
  fi
done < <(sed -n '/^target_paths:/,/^[^ ]/p' "$CONFIG" | head -n -1)

if [[ "$IN_SCOPE" == "true" ]]; then
  echo '{"decision": "allow"}'
else
  echo '{"decision": "allow", "message": "WARNING: This file is outside the review target scope. Modifying non-target files during a review loop may introduce untracked changes. Proceed with caution."}'
fi
