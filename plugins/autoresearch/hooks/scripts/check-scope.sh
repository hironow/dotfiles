#!/usr/bin/env bash
# check-scope.sh - Verify Edit/Write target is within experiment scope
#
# Reads experiment-config.yaml to get target_files list.
# If config does not exist, silently allows the operation.
# If target file is outside scope (and not results.tsv/run.log), warns.
#
# Input: JSON on stdin with tool_input.file_path
# Output: JSON with "decision" field

set -euo pipefail

CONFIG="experiment-config.yaml"

# If no active experiment, allow silently
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

# Whitelist: results.tsv and run.log are always allowed
if [[ "$BASENAME" == "results.tsv" || "$BASENAME" == "run.log" ]]; then
  echo '{"decision": "allow"}'
  exit 0
fi

# Extract target_files from config (simple YAML parsing)
IN_SCOPE=false
while IFS= read -r line; do
  # Lines under target_files: that start with "  - "
  target=$(echo "$line" | sed -n 's/^[[:space:]]*-[[:space:]]*"\?\([^"]*\)"\?$/\1/p')
  if [[ -n "$target" ]]; then
    # Check if FILE_PATH ends with the target pattern
    if [[ "$FILE_PATH" == *"$target"* ]]; then
      IN_SCOPE=true
      break
    fi
  fi
done < <(sed -n '/^target_files:/,/^[^ ]/p' "$CONFIG" | head -n -1)

if [[ "$IN_SCOPE" == "true" ]]; then
  echo '{"decision": "allow"}'
else
  echo '{"decision": "allow", "message": "WARNING: This file is outside the experiment target scope. Modifying non-target files during an experiment loop may invalidate results. Proceed with caution."}'
fi
