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

# --- Reach the WSL runner user's caches -------------------------------------
# These caches are the largest thing on the box and nothing collects them:
# ~/.cache/uv alone measured 44 GB here (126 GB on the sibling host), against
# ~2.5 GB for the whole Windows profile. runner_gc.sh deliberately leaves them
# alone — they are shared with interactive work, so they are collected on
# demand from here rather than by the hourly timer.
#
# Set DISK_GC_NO_WSL=1 to keep this to the Windows profile only.
if [ "$_win" -eq 1 ] && [ "${DISK_GC_NO_WSL:-0}" != "1" ] && command -v wsl.exe >/dev/null 2>&1; then
  _distro="${RUNNER_GC_WSL_DISTRO:-Ubuntu}"
  _self="$(cygpath -m "$0" | sed -E 's|^([A-Za-z]):|/mnt/\L\1|')"
  echo "--- 🐧 WSL distro '${_distro}' (runner user) ---"
  # Run as the distro's default user: these caches live in that user's HOME and
  # root would collect an empty set. Path conversion off, as ever.
  MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' \
    wsl.exe -d "$_distro" -e bash -lc "bash '${_self}' ${MODE}" || \
    echo "  (WSL leg failed; continuing with the Windows profile)"
  echo
fi

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
  # Sizes are the ones measured on the WSL runner host before this landed.
  _add "$HOME/.cache/uv"                 # 44 GB — by far the biggest single item
  _add "$HOME/.npm/_cacache"             # 2.3 GB
  _add "$HOME/.local/share/pnpm/store"   # 2.6 GB
  _add "$HOME/.cache/ms-playwright"      # 1.3 GB — re-installed by the workflow
  _add "$HOME/.cache/pip"
  _add "$HOME/.cache/node-gyp"
  _add "$HOME/.cache/dprint"
  _add "$HOME/.cache/golangci-lint"
  # ~/.cache/huggingface is deliberately NOT here: a single model directory
  # measured 77 GB and re-downloading it is nothing like re-fetching a wheel.
  # Opt in per-run once you know the models are disposable.
  [ "${DISK_GC_HUGGINGFACE:-0}" = "1" ] && _add "$HOME/.cache/huggingface"
fi

echo "--- 💽 host cache report ---"
printf '%b' "$_caches" | awk 'NF' | while read -r _c; do
  printf '  %-8s %s\n' "$(_size "$_c")" "$_c"
done

# The huggingface cache is never collected by default (see above), so report it
# per model instead: 77 GB of one checkpoint is a decision about what CI needs,
# not a hygiene problem, and it cannot be made from a single total.
_hf="$HOME/.cache/huggingface/hub"
if [ -d "$_hf" ]; then
  printf '  %-8s %s (opt-in: DISK_GC_HUGGINGFACE=1)\n' "$(_size "$HOME/.cache/huggingface")" "$HOME/.cache/huggingface"
  for _m in "$_hf"/models--*; do
    [ -d "$_m" ] || continue
    # Newest blob is the closest thing to "when was this last pulled".
    _when="$(find "$_m" -type f -printf '%TY-%Tm-%Td\n' 2>/dev/null | sort -r | head -1)"
    printf '    %-8s %-52s last file %s\n' \
      "$(_size "$_m")" "$(basename "$_m" | sed 's/^models--//; s/--/\//g')" "${_when:-?}"
  done | sort -rh -k1 | head -10
fi

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

# mise-managed tools are not on PATH in a non-interactive shell, which is how
# the WSL leg is invoked; without the shims `uv`/`go` silently resolve to
# "command not found" and their caches (the two biggest) survive untouched.
[ -d "$HOME/.local/share/mise/shims" ] && PATH="$HOME/.local/share/mise/shims:$PATH"

# mise: drop tool versions no tracked config references. `prune` is the
# supported entry point; it never touches versions still pinned by a config.
if command -v mise >/dev/null 2>&1; then
  if mise prune --yes >/dev/null 2>&1; then
    echo "  mise: pruned unreferenced versions"
  else
    echo "  mise: prune failed (non-fatal)"
  fi
fi

# Go's module cache is deliberately read-only, so a recursive delete leaves
# most of it behind (11 GB here). `go clean` is the only supported way to drop
# it. Spelled as if/else rather than `A && B || C`, which shellcheck rightly
# rejects (SC2015): C also runs when A succeeded but B failed.
if command -v go >/dev/null 2>&1; then
  if go clean -modcache >/dev/null 2>&1; then
    echo "  go: module cache cleaned"
  else
    echo "  go: modcache clean failed (non-fatal)"
  fi
  if go clean -cache >/dev/null 2>&1; then
    echo "  go: build cache cleaned"
  fi
fi

printf '%b' "$_caches" | awk 'NF' | while read -r _c; do
  if rm -rf "$_c" 2>/dev/null; then
    echo "  removed: $_c"
  else
    echo "  skipped (in use): $_c"
  fi
done

echo "--- ✅ host caches reclaimed ---"
