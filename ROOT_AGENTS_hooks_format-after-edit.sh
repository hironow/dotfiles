#!/usr/bin/env bash
# .claude/hooks/format-after-edit.sh
# PostToolUse hook (matcher: Write|Edit). Runs after a file is written/edited.
# PostToolUse CANNOT undo the action; it formats and surfaces remaining issues so
# Claude fixes them on the next turn. Always exit 0 (this is not a gate; the gate
# is `just check` at commit time + CI).
#
# Loop-safety: this hook does not write files via a tool, so it won't retrigger
# PostToolUse. It calls formatters directly.
set -uo pipefail

input="$(cat)"
file_path="$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty')"
[ -z "$file_path" ] && exit 0
[ -f "$file_path" ] || exit 0

case "$file_path" in
  *.py)
    if command -v uv >/dev/null 2>&1; then
      uv run ruff format "$file_path"        >/dev/null 2>&1 || true
      uv run ruff check --fix "$file_path"   >/dev/null 2>&1 || true
      # Surface anything auto-fix couldn't resolve, as feedback for Claude.
      remaining="$(uv run ruff check "$file_path" 2>&1 || true)"
      if [ -n "$remaining" ] && ! printf '%s' "$remaining" | grep -q "All checks passed"; then
        echo "ruff still reports issues in $file_path:" >&2
        printf '%s\n' "$remaining" >&2
      fi
    fi
    ;;
  *.go)
    if command -v gofmt >/dev/null 2>&1; then
      gofmt -w "$file_path" >/dev/null 2>&1 || true
    fi
    ;;
  # TS/JS is intentionally not formatted here: there is no project-agnostic
  # single-file formatter, and running `just fmt` (project-wide) per edit
  # pollutes unrelated diffs. The gate is `just check` / CI.
esac

exit 0
