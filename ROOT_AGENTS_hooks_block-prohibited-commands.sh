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

# Builtins only up to the interpreter lookup (no dirname): PATH may be minimal.
case "${BASH_SOURCE[0]}" in
  */*) dir="${BASH_SOURCE[0]%/*}" ;;
  *) dir=. ;;
esac
dir="$(cd "$dir" && pwd)"
companion=""
for candidate in \
  "$dir/block-prohibited-commands.py" \
  "$dir/ROOT_AGENTS_hooks_block-prohibited-commands.py"; do
  if [ -f "$candidate" ]; then
    companion="$candidate"
    break
  fi
done
if [ -z "$companion" ]; then
  echo "BLOCKED: companion guard block-prohibited-commands.py not found next to the wrapper (incomplete sync?) — failing closed." >&2
  exit 2
fi

# A real interpreter: on Windows `python3` can be the Microsoft Store stub under
# WindowsApps, which runs nothing and exits non-zero (read as "allow").
# Collected into a string and split on newlines (no read loop: stdin carries
# the hook payload for the companion; no array: macOS's bash 3.2 runs this).
interpreters="$(type -aP python3 python 2>/dev/null || true)"
set -f
IFS='
'
python=""
for interpreter in $interpreters; do
  case "$interpreter" in
    */WindowsApps/*) continue ;;
  esac
  python="$interpreter"
  break
done
if [ -n "$python" ]; then
  exec "$python" "$companion"
fi

echo "BLOCKED: no Python found for the command guard (python3 / python) — failing closed. Install one (mise python)." >&2
exit 2
