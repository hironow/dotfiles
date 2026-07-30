#!/usr/bin/env bash

# ==============================================================================
# Host-side disk GC + report (ADR 0035)
# ------------------------------------------------------------------------------
# Complements scripts/runner_gc.sh (which handles the Linux/WSL runner side).
# This one collects the caches that accumulate on the *host* profile:
#   - mise    stale tool versions no config references
#   - bun     global install cache
#   - uv      wheel/source cache
#   - cargo   registry archives + unpacked sources
#
# Usage:
#   disk_gc.sh report   — measure only, never deletes (default)
#   disk_gc.sh clean    — reclaim the caches above
#
# Every cache here is regenerated on demand: cleaning costs re-download time,
# never correctness. Toolchains, SDKs and project data are deliberately out of
# scope — this script must stay safe to run unattended.
# ==============================================================================

set -eu

MODE="${1:-report}"

_win=0
case "$(uname -s)" in
  MINGW* | MSYS* | CYGWIN*) _win=1 ;;
esac

# Resolve a Windows env var (e.g. LOCALAPPDATA) to a unix path, empty if unset.
_winpath() {
  _v="$(printenv "$1" 2>/dev/null || true)"
  [ -n "$_v" ] || return 0
  cygpath -u "$_v" 2>/dev/null || printf '%s' "$_v"
}

_size() { # -> human size of $1, or "-" when absent
  [ -d "$1" ] || { printf -- '-'; return 0; }
  du -shx "$1" 2>/dev/null | awk '{print $1}' || printf -- '?'
}

# --- candidate caches -------------------------------------------------------
_caches=""
_add() { [ -n "$1" ] && [ -d "$1" ] && _caches="${_caches}${1}\n"; return 0; }

_add "$HOME/.bun/install/cache"
_add "$HOME/.cargo/registry/cache"
_add "$HOME/.cargo/registry/src"
if [ "$_win" -eq 1 ]; then
  _lad="$(_winpath LOCALAPPDATA)"
  [ -n "$_lad" ] && _add "${_lad}/uv/cache"
  [ -n "$_lad" ] && _add "${_lad}/npm-cache"
else
  _add "$HOME/.cache/uv"
  _add "$HOME/.npm/_cacache"
fi

echo "--- 💽 host cache report ---"
printf '%b' "$_caches" | awk 'NF' | while read -r _c; do
  printf '  %-8s %s\n' "$(_size "$_c")" "$_c"
done

if [ "$_win" -eq 1 ]; then
  # PowerShell is the only portable way to read free space on native Windows;
  # `df` reports the Git-Bash mount table, not the volume.
  # shellcheck disable=SC2016  # $d is a PowerShell variable; bash must not expand it
  powershell.exe -NoProfile -Command \
    '$d=Get-PSDrive C; "  C: free {0} GB / total {1} GB" -f [math]::Round($d.Free/1GB,1), [math]::Round(($d.Free+$d.Used)/1GB,1)' 2>/dev/null | tr -d '\r' || true
else
  printf '  %s\n' "$(df -h "$HOME" | awk 'NR==2 {print $4" avail on "$6}')"
fi

if [ "$MODE" != "clean" ]; then
  echo "--- (report only; run with 'clean' to reclaim) ---"
  exit 0
fi

echo "--- 🧹 reclaiming ---"

# mise: drop tool versions no tracked config references. `prune` is the
# supported entry point; it never touches versions still pinned by a config.
if command -v mise >/dev/null 2>&1; then
  mise prune --yes >/dev/null 2>&1 && echo "  mise: pruned unreferenced versions" || echo "  mise: prune failed (non-fatal)"
fi

printf '%b' "$_caches" | awk 'NF' | while read -r _c; do
  rm -rf "$_c" 2>/dev/null && echo "  removed: $_c" || echo "  skipped (in use): $_c"
done

echo "--- ✅ host caches reclaimed ---"
