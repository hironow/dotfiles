#!/usr/bin/env bash

# ==============================================================================
# GitHub-truth section of `just status` (fed by scripts/gc_status.sh)
# ------------------------------------------------------------------------------
# The local probes can be ALL GREEN while GitHub shows a runner offline: a dead
# broker session leaves the Listener process up (the "zombie" seen live
# 2026-08-20 — offline + busy=true during a hung-job cancellation), and a
# server-side registration purge rejects a perfectly healthy service. Only the
# server knows; this section asks it.
#
# stdin protocol (one line per local runner, composed by gc_status.sh):
#   name|gitHubUrl|local_up|restart_hint
#   - local_up: 1 when the leg saw the runner running locally, else 0
#   - restart_hint: leg-specific runbook tail, printed verbatim on a zombie
#
# Contract: NEVER hard-fails. Missing gh, a 403 (admin:org scope), or a broken
# response degrade to WARN and exit 0 — status is a read-only report.
# ==============================================================================

set -eu

_ok()   { printf '  \033[32mOK\033[0m    %s\n' "$1"; }
_warn() { printf '  \033[33mWARN\033[0m  %s\n' "$1"; }
_bad()  { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; }
_info() { printf '        %s\n' "$1"; }

echo "── GitHub (the server's view) ───────────────────────────────"

# Test seam: the suite points this at a stub (or a deliberately absent name);
# production leaves it at plain `gh`.
_gh="${GC_GITHUB_GH:-gh}"

if ! command -v "$_gh" >/dev/null 2>&1; then
  _warn "GitHub-side view unchecked (gh not installed)"
  exit 0
fi

# Cache one listing per scope; an org hosts several runners (siblings from
# other machines included), so every local runner usually shares one query.
_scopes=""
_cache=""

_scope_of() {
  _path="${1#https://github.com/}"
  _path="${_path#http://github.com/}"
  printf '%s' "${_path%/}"
}

_ensure_scope() {
  # $1 = gitHubUrl. Fills the cache on first sight. Runs OUTSIDE any command
  # substitution so its WARN actually reaches the report (a $(...) would
  # swallow it into the caller's variable).
  _path="$(_scope_of "$1")"
  case "$_scopes" in *"<${_path}>"*) return 0 ;; esac
  _scopes="${_scopes}<${_path}>"
  case "$_path" in
    # No leading slash on the endpoint: Git Bash rewrites /orgs/... into a
    # Git-install path (MSYS mangling) before gh ever sees it.
    */*) _ep="repos/${_path}/actions/runners" ;;
    *)   _ep="orgs/${_path}/actions/runners" ;;
  esac
  if _tsv="$("$_gh" api --paginate "$_ep" \
      --jq '.runners[] | [.name, .status, (.busy|tostring)] | @tsv' 2>/dev/null)"; then
    _cache="${_cache}=== ${_path}
${_tsv}
"
  else
    _cache="${_cache}=== ${_path}
!ERROR
"
    _warn "GitHub-side view unchecked for '${_path}' (API error; if 403: gh auth refresh -h github.com -s admin:org)"
  fi
}

_listing_for() {
  # $1 = gitHubUrl. Pure cache read; _ensure_scope must have run first.
  printf '%s\n' "$_cache" | awk -v s="=== $(_scope_of "$1")" '
    $0 == s {inblock=1; next} /^=== / {inblock=0} inblock {print}'
}

_saw_any=0
while IFS='|' read -r _name _url _up _hint; do
  [ -n "$_name" ] || continue
  _saw_any=1
  _ensure_scope "$_url"
  _list="$(_listing_for "$_url")"
  case "$_list" in *'!ERROR'*) continue ;; esac
  _found=0
  _rstatus=""
  _rbusy=""
  while IFS="$(printf '\t')" read -r _n _s _b; do
    # EXACT match only: real agent names carry spaces ('trade win'), and a
    # substring match would read a sibling's state.
    if [ "$_n" = "$_name" ]; then
      _found=1
      _rstatus="$_s"
      _rbusy="$_b"
      break
    fi
  done <<EOF
$_list
EOF
  if [ "$_found" -eq 0 ]; then
    _bad "${_name}: not in GitHub's runner list — the registration was purged server-side (long-offline auto-delete); re-register: config.cmd remove + a fresh token"
  elif [ "$_rstatus" = "online" ]; then
    if [ "$_rbusy" = "true" ]; then
      _ok "${_name}: online (busy)"
    else
      _ok "${_name}: online"
    fi
  elif [ "$_up" = "1" ]; then
    # The zombie: GitHub lost the broker session while the local process
    # tree lives. The runner's own job-cancellation timeout usually reaps it.
    _bad "${_name}: offline on GitHub while the local runner is up — zombie session. Wait ~5 min (job-cancellation self-heal); if still offline: ${_hint}"
  else
    _info "${_name}: offline on GitHub (the leg above already carries the local alarm and its fix)"
  fi
done

if [ "$_saw_any" -eq 0 ]; then
  _info "no local runner identities found"
fi
exit 0
