#!/usr/bin/env bash
# .claude/hooks/block-prohibited-commands.sh
# PreToolUse hook (matcher: Bash) — thin wrapper. The guard logic lives in the
# companion Python file (stdlib-only): correct quote/heredoc handling needs a
# tokenizer, not regexes. See docs/agents/enforcement.md for the semantics.
#
# The companion's filename differs between the dotfiles repo root (sync source
# naming) and a deployed agent home (hooks/), so both are tried.
#
# Exit-code contract:
#   exit 0  -> allow
#   exit 2  -> BLOCK (stderr -> Claude). exit 1 would NOT block.
set -euo pipefail

dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for candidate in \
  "$dir/block-prohibited-commands.py" \
  "$dir/ROOT_AGENTS_hooks_block-prohibited-commands.py"; do
  if [ -f "$candidate" ]; then
    exec python3 "$candidate"
  fi
done

echo "BLOCKED: companion guard block-prohibited-commands.py not found next to the wrapper (incomplete sync?) — failing closed." >&2
exit 2
