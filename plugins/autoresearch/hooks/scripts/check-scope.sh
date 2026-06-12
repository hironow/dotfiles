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
# Requires jq (like the global hooks). Without jq the guard FAILS OPEN
# (exit 0): a scope guard is loop hygiene, not a security boundary, and a
# jq-less environment would otherwise drown in asks. The setup skills
# preflight jq so the tradeoff is surfaced, never silent.
#
# Scope matching (entries and file_path are normalized first: leading "./"
# stripped, runs of "/" collapsed):
#   - entry ending in "/" (directory): file_path starts with it, or
#     contains it as a path segment ("src/" matches /repo/src/a.py).
#   - other entries (files): file_path equals it or ends with "/<entry>"
#     (no bare substring matches: "algo.py" must NOT match myalgo.py).
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

# Fail open without jq (see header)
if ! command -v jq >/dev/null 2>&1; then
  exit 0
fi

# Extract file_path from stdin JSON (jq decodes escapes; never grep JSON).
# Malformed input fails open like the no-jq case — never let a payload
# hiccup surface an error (exit 2 would BLOCK the edit).
INPUT=$(cat)
FILE_PATH=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)

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

# Normalize a path for comparison: strip leading "./", collapse "//" runs.
normalize() {
  printf '%s' "$1" | sed 's#^\./##; s#//*#/#g'
}

FP=$(normalize "$FILE_PATH")

# Extract the scope list: "- " items under LIST_KEY, until the next
# top-level key. Hand-edited YAML spellings are tolerated: single or
# double quotes, inline comments, space before the key's colon; indented
# comments and blank lines do not end the list, and a list that closes
# the file keeps its last entry (POSIX awk; full YAML is out of scope —
# the config format is owned by this plugin's setup skill).
IN_SCOPE=false
while IFS= read -r target; do
  [[ -z "$target" ]] && continue
  t=$(normalize "$target")
  if [[ "$t" == */ ]]; then
    # directory entry: prefix (relative payload) or path segment (absolute)
    if [[ "$FP" == "$t"* || "$FP" == *"/$t"* ]]; then
      IN_SCOPE=true
      break
    fi
  else
    # file entry: exact match or suffix at a path-segment boundary
    if [[ "$FP" == "$t" || "$FP" == */"$t" ]]; then
      IN_SCOPE=true
      break
    fi
  fi
done < <(awk -v key="$LIST_KEY" -v sq="'" '
  $0 ~ ("^" key "[[:space:]]*:") { inlist = 1; next }
  inlist {
    if ($0 ~ /^[^[:space:]]/) exit
    line = $0
    sub(/^[[:space:]]+/, "", line)
    if (line == "" || line ~ /^#/) next
    if (line ~ /^-[[:space:]]*/) {
      sub(/^-[[:space:]]*/, "", line)
      sub(/[[:space:]]+#.*$/, "", line)
      sub(/[[:space:]]+$/, "", line)
      gsub("^[\"" sq "]|[\"" sq "]$", "", line)
      if (line != "") print line
    }
  }
' "$CONFIG")

if [[ "$IN_SCOPE" == "true" ]]; then
  exit 0
fi

# Out of scope: escalate to the user instead of auto-approving.
# permissionDecision "allow" would BYPASS the normal permission prompt and
# silently let the edit through; "ask" surfaces it so a stray non-target
# write cannot invalidate the loop.
jq -cn --arg reason "$REASON" \
  '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "ask", permissionDecisionReason: $reason}}'
