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
# never correctness - but only while no runner job is building from it, so
# `clean` stops before each deletion step while this leg's runner has a job
# (see the runner job guard below). Toolchains, SDKs and project data are
# deliberately out of scope.
# ==============================================================================

set -eu

MODE="${1:-report}"

# Overrides the runner-job guard below. Normalised to 0/1 here because the
# value is embedded in the WSL leg's command line.
_allow_busy=0
[ "${DISK_GC_ALLOW_BUSY:-0}" != "1" ] || _allow_busy=1

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
  # wsl.exe -e starts a fresh environment (WSLENV unset here), so the opt-in
  # knob must ride inside the command line or the WSL leg never sees it.
  MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' \
    wsl.exe -d "$_distro" -e bash -lc "DISK_GC_HUGGINGFACE=${DISK_GC_HUGGINGFACE:-0} DISK_GC_ALLOW_BUSY=${_allow_busy} bash '${_self}' ${MODE}" || \
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

# --- Runner job guard -------------------------------------------------------
# These caches are shared with this leg's self-hosted runner, and a cache that
# is regenerated on demand is still in use while a job builds from it: deleting
# ~/.cargo/registry/src under a running cargo killed rustc mid-compile (its cwd
# is the crate's unpacked source; a CI job on the WSL runner, 2026-11-16).
# Each leg checks its own runner: the WSL leg runs this script inside the
# distro, where _win=0.
#
# Returns 0 = a job is running, 1 = idle, 2 = cannot tell. Callers treat 2 as
# busy: a detection that fails open deletes under a job on a quieter day.
_runner_job_state() {
  if [ "$_win" -eq 1 ]; then
    # tasklist is a native exe, so Git Bash would rewrite /FI into a Windows
    # path and tasklist would error out. The no-match message is localised;
    # the image name in the CSV is not.
    _tl="$(MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' tasklist /FI "IMAGENAME eq Runner.Worker.exe" /FO CSV /NH 2>/dev/null)" || return 2
    case "$_tl" in *'"Runner.Worker.exe"'*) return 0 ;; esac
    return 1
  fi
  # -x, not -f: -f would match this script's own command line.
  _rc=0
  pgrep -x Runner.Worker >/dev/null 2>&1 || _rc=$?
  case "$_rc" in
    0) return 0 ;;
    1) return 1 ;;
    *) return 2 ;;
  esac
}

_runner_job_word() {
  _st=0
  _runner_job_state || _st=$?
  case "$_st" in
    0) printf 'busy' ;;
    1) printf 'idle' ;;
    *) printf 'unknown' ;;
  esac
}

# Runs before EVERY deletion step, not once up front: the sweep takes minutes
# (an 11 GB read-only Go module cache, tens of GB of uv), and a job can start
# in between. It is an observation, not a lock - a job that starts between this
# check and the delete it guards is not stopped.
_guard() { # $1: what is about to be deleted
  [ "$_allow_busy" -ne 1 ] || return 0
  _st=0
  _runner_job_state || _st=$?
  case "$_st" in
    1) return 0 ;;
    0)
      echo "  SKIP: a runner job is executing (Runner.Worker alive); rerun when idle"
      echo "  (stopped before: $1)"
      exit 0
      ;;
    *)
      echo "  SKIP: cannot tell whether a runner job is executing; nothing more deleted"
      echo "  (stopped before: $1)"
      exit 2
      ;;
  esac
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
fi
# ~/.cache/huggingface is deliberately NOT collected by default: a single model
# directory measured 77 GB and re-downloading it is nothing like re-fetching a
# wheel. Opt in per-run once you know the models are disposable. Evaluated on
# EVERY leg (Git Bash $HOME is the Windows profile, so this reaches
# C:/Users/<me>/.cache/huggingface as well as the WSL user's) - it used to sit
# inside the non-Windows branch, which silently skipped the 75 GB Windows copy.
[ "${DISK_GC_HUGGINGFACE:-0}" = "1" ] && _add "$HOME/.cache/huggingface"

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

printf '  runner job: %s (clean deletes only while idle)\n' "$(_runner_job_word)"

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
  _guard "mise prune"
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
  _guard "go module cache"
  if go clean -modcache >/dev/null 2>&1; then
    echo "  go: module cache cleaned"
  else
    echo "  go: modcache clean failed (non-fatal)"
  fi
  _guard "go build cache"
  if go clean -cache >/dev/null 2>&1; then
    echo "  go: build cache cleaned"
  fi
fi

# A here-string, not a pipe: _guard's exit must end the script, and inside a
# `... | while` loop it would only end the pipeline's subshell.
while read -r _c; do
  [ -n "$_c" ] || continue
  _guard "$_c"
  if rm -rf "$_c" 2>/dev/null; then
    echo "  removed: $_c"
  else
    echo "  skipped (in use): $_c"
  fi
done <<< "$(printf '%b' "$_caches" | awk 'NF')"

echo "--- ✅ host caches reclaimed ---"
