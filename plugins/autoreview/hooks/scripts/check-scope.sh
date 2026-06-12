#!/usr/bin/env bash
# check-scope.sh - shared PreToolUse guard: is the Edit/Write target inside
# the loop's declared scope?
#
# CANONICAL SOURCE: plugins/_shared/check-scope.sh. Edit it HERE and run
# `just sync-plugin-scope-hook` — the per-plugin copies under
# plugins/*/hooks/scripts/ are distribution artifacts (an installed plugin
# only ships its own directory, so a copy cannot reference this file at
# runtime). tests/unit/test_plugin_check_scope.py gates drift.
#
# usage: check-scope.sh CONFIG_FILE LIST_KEY "WHITELIST BASENAMES" REASON
#   CONFIG_FILE  per-loop config looked up in the cwd (e.g.
#                experiment-config.yaml); absent = no active loop = allow
#   LIST_KEY     top-level YAML key holding the scope list
#                (target_files / target_paths)
#   WHITELIST    space-separated basenames always allowed (loop artifacts;
#                must not contain spaces themselves)
#   REASON       permissionDecisionReason used when escalating to "ask"
#
# Input: PreToolUse JSON on stdin with tool_input.file_path
# Output: empty (exit 0 = allow) or hookSpecificOutput JSON with
#         permissionDecision=ask + the given reason

set -euo pipefail

CONFIG="${1:?usage: check-scope.sh CONFIG_FILE LIST_KEY WHITELIST REASON}"
LIST_KEY="${2:?missing LIST_KEY (e.g. target_files)}"
WHITELIST="${3:-}"
REASON="${4:?missing REASON}"

# If no active loop, allow silently
if [[ ! -f "$CONFIG" ]]; then
  exit 0
fi

# Extract file_path from stdin JSON
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*"file_path"[[:space:]]*:[[:space:]]*"//' | sed 's/"$//' || echo "")

if [[ -z "$FILE_PATH" ]]; then
  exit 0
fi

# Whitelist: loop artifacts are always allowed (compared by basename)
BASENAME=$(basename "$FILE_PATH")
for allowed in $WHITELIST; do
  if [[ "$BASENAME" == "$allowed" ]]; then
    exit 0
  fi
done

# Extract the scope list from the config (simple YAML parsing)
IN_SCOPE=false
while IFS= read -r line; do
  # Lines under the list key that start with "  - "
  target=$(echo "$line" | sed -n 's/^[[:space:]]*-[[:space:]]*"\{0,1\}\([^"]*\)"\{0,1\}$/\1/p')
  if [[ -n "$target" ]]; then
    # Check if FILE_PATH ends with the target pattern
    if [[ "$FILE_PATH" == *"$target"* ]]; then
      IN_SCOPE=true
      break
    fi
  fi
done < <(sed -n "/^${LIST_KEY}:/,/^[^ ]/p" "$CONFIG" | sed '$d')

if [[ "$IN_SCOPE" == "true" ]]; then
  exit 0
fi

# Out of scope: escalate to the user instead of auto-approving.
# permissionDecision "allow" would BYPASS the normal permission prompt and
# silently let the edit through; "ask" surfaces it so a stray non-target
# write cannot invalidate the loop.
printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"%s"}}\n' "$REASON"
