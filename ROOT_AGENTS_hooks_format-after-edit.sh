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
paths="$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty')"
# Codex's apply_patch: the whole patch is tool_input.command; format each file
# it added or updated (a moved file under its new name).
if [ -z "$paths" ]; then
  patch="$(printf '%s' "$input" | jq -r '.tool_input.command // empty')"
  case "$patch" in
    *'*** Begin Patch'*)
      paths="$(printf '%s\n' "$patch" | sed -n -E 's/^\*\*\* (Add File|Update File|Move to): (.*)$/\2/p')"
      ;;
  esac
fi
[ -z "$paths" ] && exit 0

while IFS= read -r file_path; do
[ -f "$file_path" ] || continue

case "$file_path" in
  *.py)
    if command -v uv >/dev/null 2>&1; then
      # --frozen: never touch uv.lock. A bare `uv run` re-resolves under
      # machine-local uv config (e.g. mirror overrides) and rewrites the lock
      # on every .py edit; the lock must only change via explicit `uv lock`.
      uv run --frozen --only-group lint ruff format "$file_path"        >/dev/null 2>&1 || true
      uv run --frozen --only-group lint ruff check --fix "$file_path"   >/dev/null 2>&1 || true
      # Surface anything auto-fix couldn't resolve, as feedback for Claude.
      remaining="$(uv run --frozen --only-group lint ruff check "$file_path" 2>&1 || true)"
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
done <<<"$paths"

exit 0
