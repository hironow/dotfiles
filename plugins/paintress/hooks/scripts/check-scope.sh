#!/usr/bin/env bash
# check-scope.sh - Verify Edit/Write target is within expedition repository scope
#
# Reads continent-config.yaml to get repository path.
# If config does not exist, silently allows the operation.
# If target file is outside repository scope (and not journal.tsv/continent-config.yaml), warns.
#
# Input: JSON on stdin with tool_input.file_path
# Output: JSON with "decision" field

set -euo pipefail

CONFIG="continent-config.yaml"

# If no active expedition, allow silently
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

# Whitelist: journal.tsv and continent-config.yaml are always allowed
if [[ "$BASENAME" == "journal.tsv" || "$BASENAME" == "continent-config.yaml" ]]; then
  echo '{"decision": "allow"}'
  exit 0
fi

# Extract repository path from config
REPO_PATH=$(grep -E '^\s*repository:' "$CONFIG" | head -1 | sed 's/.*repository:[[:space:]]*//' | tr -d '"' | tr -d "'" || echo "")

if [[ -z "$REPO_PATH" ]]; then
  echo '{"decision": "allow"}'
  exit 0
fi

# Resolve to absolute path
if [[ "$REPO_PATH" != /* ]]; then
  REPO_PATH="$(pwd)/$REPO_PATH"
fi
REPO_PATH=$(cd "$REPO_PATH" 2>/dev/null && pwd || echo "$REPO_PATH")

# Check if file is within repository scope
if [[ "$FILE_PATH" == "$REPO_PATH"* ]]; then
  echo '{"decision": "allow"}'
else
  echo '{"decision": "allow", "message": "WARNING: This file is outside the expedition target repository. Expedition scope is limited to the configured repository. Proceed only if intentional."}'
fi
