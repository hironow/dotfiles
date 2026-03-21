#!/usr/bin/env bash
set -euo pipefail
CONFIG="design-config.yaml"
if [[ ! -f "$CONFIG" ]]; then
  echo '{"decision": "allow"}'
  exit 0
fi
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"file_path"[[:space:]]*:[[:space:]]*"//' | sed 's/"$//' || echo "")
if [[ -z "$FILE_PATH" ]]; then
  echo '{"decision": "allow"}'
  exit 0
fi
BASENAME=$(basename "$FILE_PATH")
if [[ "$BASENAME" == "design-results.tsv" || "$BASENAME" == "run.log" ]]; then
  echo '{"decision": "allow"}'
  exit 0
fi
IN_SCOPE=false
while IFS= read -r line; do
  target=$(echo "$line" | sed -n 's/^[[:space:]]*-[[:space:]]*"\{0,1\}\([^"]*\)"\{0,1\}$/\1/p')
  if [[ -n "$target" && "$FILE_PATH" == *"$target"* ]]; then
    IN_SCOPE=true
    break
  fi
done < <(sed -n '/^target_files:/,/^[^ ]/p' "$CONFIG" | head -n -1)
if [[ "$IN_SCOPE" == "true" ]]; then
  echo '{"decision": "allow"}'
else
  echo '{"decision": "allow", "message": "WARNING: This file is outside the design target scope."}'
fi
