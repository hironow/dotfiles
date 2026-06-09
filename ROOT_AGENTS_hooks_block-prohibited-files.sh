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
file_path="$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty')"

# Nothing to check (e.g. tool input without a path).
[ -z "$file_path" ] && exit 0

base="$(basename "$file_path")"

# Self-reference exemption: the policy files themselves may name prohibited
# patterns as examples.
case "$file_path" in
  */AGENTS.md|AGENTS.md|*/CLAUDE.md|CLAUDE.md|*/docs/agents/*) exit 0 ;;
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

exit 0
