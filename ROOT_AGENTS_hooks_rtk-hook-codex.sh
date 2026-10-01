#!/usr/bin/env bash
# Codex PreToolUse hook (matcher: Bash) — thin wrapper. The logic lives in the
# companion Python file (stdlib-only): rtk's own Codex hook, with the rewrite
# naming rtk's real binary, since a mise shim cannot run in Codex's sandbox.
# See rtk-hook-codex.py and docs/agents/rtk.md.
#
# The companion's filename differs between the dotfiles repo root (sync source
# naming) and a deployed agent home (hooks/), so both are tried.
#
# FAILS OPEN: an optimiser, not a guard. Without a companion or a real Python
# it prints nothing and the command runs unchanged.

case "${BASH_SOURCE[0]}" in
  */*) dir="${BASH_SOURCE[0]%/*}" ;;
  *) dir=. ;;
esac
dir="$(cd "$dir" && pwd)" || exit 0
companion=""
for candidate in \
  "$dir/rtk-hook-codex.py" \
  "$dir/ROOT_AGENTS_hooks_rtk-hook-codex.py"; do
  if [ -f "$candidate" ]; then
    companion="$candidate"
    break
  fi
done
[ -n "$companion" ] || exit 0

# A real interpreter, as the command guard finds one: on Windows `python3` can
# be the Microsoft Store stub, which runs nothing. Collected into a string (no
# read loop: stdin carries the payload; no array: macOS's bash 3.2 runs this).
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
[ -n "$python" ] || exit 0
exec "$python" "$companion"
