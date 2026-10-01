#!/usr/bin/env bash
# .claude/hooks/block-prohibited-files.sh
# PreToolUse hook (matcher: Write|Edit). Blocks creating/editing files that
# violate the file-naming non-negotiables in AGENTS.md.
#
# Exit-code contract (Claude Code):
#   exit 0  -> allow
#   exit 2  -> BLOCK (stderr is fed back to Claude as the reason)
#   exit 1  -> non-blocking error, action PROCEEDS (do NOT use it to block)
set -euo pipefail

input="$(cat)"
paths="$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty')"

# Codex's apply_patch has no file_path: the whole patch is tool_input.command,
# and its Add File / Update File headers name every file it writes. An Update
# File followed by Move to leaves only the destination, so only that is
# checked (renaming old.yml to old.yaml must pass).
if [ -z "$paths" ]; then
  patch="$(printf '%s' "$input" | jq -r '.tool_input.command // empty')"
  case "$patch" in
    *'*** Begin Patch'*)
      paths="$(printf '%s\n' "$patch" | awk '
        function flush() { if (pending != "") print pending; pending = "" }
        /^\*\*\* Add File: /    { flush(); print substr($0, 15); next }
        /^\*\*\* Update File: / { flush(); pending = substr($0, 18); next }
        /^\*\*\* Move to: /     { pending = substr($0, 14); next }
        /^\*\*\* /              { flush() }
        END                     { flush() }
      ')"
      ;;
  esac
fi

# Nothing to check (e.g. tool input without a path).
[ -z "$paths" ] && exit 0

check() {
  local file_path="$1" base
  base="$(basename "$file_path")"

  # Self-reference exemption: the policy files themselves may name prohibited
  # patterns as examples.
  case "$file_path" in
    */AGENTS.md|AGENTS.md|*/CLAUDE.md|CLAUDE.md|*/docs/agents/*) return 0 ;;
  esac

  # GitHub Actions accepts .yaml, so workflow files are not exempted here; the rule
  # is global. (If you ever must keep a vendored .yml you cannot rename, add an
  # explicit allowlist case above this block.)

  # Rule 1: deprecated Docker Compose v1 filenames.
  case "$base" in
    docker-compose.yaml|docker-compose.yml)
      echo "BLOCKED: '$base' is the deprecated Compose v1 name. Use 'compose.yaml' (Compose Spec v2+)." >&2
      exit 2
      ;;
  esac

  # Rule 2: .yml extension anywhere. Canonical extension is .yaml.
  case "$base" in
    *.yml)
      echo "BLOCKED: '$base' uses '.yml'. This project uses '.yaml' exclusively. Rename to '${base%.yml}.yaml'." >&2
      exit 2
      ;;
  esac
}

while IFS= read -r file_path; do
  [ -n "$file_path" ] && check "$file_path"
done <<<"$paths"

exit 0
