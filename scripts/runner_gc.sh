#!/usr/bin/env bash

# ==============================================================================
# Disk GC for the WSL self-hosted GitHub Actions runner (ADR 0035)
# ------------------------------------------------------------------------------
# Runs INSIDE the Linux side (WSL distro that hosts the runner). Reclaims the
# three artifacts that ratchet upward forever because nothing prunes them by
# default:
#   - stopped containers      (each devcontainer job leaves one behind)
#   - unreferenced images     (every job builds a fresh tag)
#   - BuildKit build cache    (the dominant one — no GC policy out of the box)
# plus apt lists/archives and the systemd journal when invoked as root.
#
# Retention is TIME-based: anything last used within $RUNNER_GC_RETENTION is
# kept so back-to-back jobs still hit warm cache; everything older is dropped.
#
# Invoked from two places (both installed by scripts/install_runner_gc.sh):
#   - runner-gc.timer                  — hourly floor, catches idle drift
#   - ACTIONS_RUNNER_HOOK_JOB_COMPLETED — right after each job, the ideal moment
# ==============================================================================

set -eu

RETENTION="${RUNNER_GC_RETENTION:-2h}"
FORCE="${RUNNER_GC_FORCE:-0}"

log() { printf '[runner-gc] %s %s\n' "$(date -Is)" "$*"; }

# --- Windows host: collect BOTH runners -------------------------------------
# This box hosts two self-hosted runners — one inside the WSL distro and one
# native Windows one — so `just runner-gc` from the Windows side must sweep
# both. The WSL leg needs install_runner_gc.sh to have placed the payload at
# /usr/local/bin/runner-gc.
case "$(uname -s)" in
  MINGW* | MSYS* | CYGWIN*)
    _here="$(cd "$(dirname "$0")" && pwd)"
    _distro="${RUNNER_GC_WSL_DISTRO:-Ubuntu}"
    _rc=0

    log "host is Windows; collecting WSL distro '${_distro}'"
    # Git Bash would rewrite /usr/local/bin/runner-gc into a Windows path
    # before wsl.exe sees it; disable the conversion for these calls.
    export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'
    wsl.exe -d "$_distro" -u root -e env \
      "RUNNER_GC_RETENTION=${RETENTION}" \
      "RUNNER_GC_FORCE=${FORCE}" \
      /usr/local/bin/runner-gc || _rc=$?

    log "collecting the native Windows runner"
    _ps1="${_here}/runner_gc_win.ps1"
    if [ -f "$_ps1" ]; then
      _force_flag=""
      [ "$FORCE" = "1" ] && _force_flag="-Force"
      powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass \
        -File "$(cygpath -w "$_ps1")" -Retention "$RETENTION" $_force_flag || _rc=$?
    else
      log "windows: ${_ps1} missing; skipping"
    fi

    exit "$_rc"
    ;;
esac

# --- Job safety -------------------------------------------------------------
# Never prune while a job is executing: an in-flight `docker build` can be
# holding cache that the age filter would otherwise consider cold.
#
# Use `pgrep -x` (matches the executable NAME only). `pgrep -f Runner.Worker`
# matches this script's own command line as well and so reports a running job
# 100% of the time — a false positive that silently disables the whole GC.
if [ "$FORCE" != "1" ] && pgrep -x Runner.Worker >/dev/null 2>&1; then
  log "SKIP: a runner job is executing (Runner.Worker alive)"
  exit 0
fi

_is_root() { [ "$(id -u)" -eq 0 ]; }

_df_root() { df -h / | awk 'NR==2 {print $3" used, "$4" avail ("$5")"}'; }

log "start (retention=${RETENTION}) — / : $(_df_root)"

# --- Docker -----------------------------------------------------------------
_docker_gc() {
  if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
    log "docker: not available; skipping"
    return 0
  fi
  log "docker: before — $(docker system df --format '{{.Type}}={{.Size}}' | tr '\n' ' ')"

  # Order matters: containers first so the images they pin become prunable.
  docker container prune -f --filter "until=${RETENTION}" >/dev/null 2>&1 || true
  docker image prune -af --filter "until=${RETENTION}" >/dev/null 2>&1 || true
  docker builder prune -af --filter "until=${RETENTION}" >/dev/null 2>&1 || true

  # buildx `docker-container` builders keep their cache inside their own
  # container, which the daemon-level `builder prune` above does NOT reach.
  docker buildx ls --format '{{.Name}}' 2>/dev/null | awk 'NF' | while read -r _b; do
    [ "$_b" = "default" ] && continue
    docker buildx prune -af --filter "until=${RETENTION}" --builder "$_b" >/dev/null 2>&1 || true
  done

  log "docker: after  — $(docker system df --format '{{.Type}}={{.Size}}' | tr '\n' ' ')"
}

_docker_gc

# --- apt / journal (root only) ----------------------------------------------
# Both need privileges; under the systemd timer we are root, under the runner
# job hook we are the runner user, so degrade quietly instead of failing.
if _is_root; then
  if command -v apt-get >/dev/null 2>&1; then
    apt-get clean >/dev/null 2>&1 || true
    log "apt: archives cleaned"
  fi
  if command -v journalctl >/dev/null 2>&1; then
    journalctl --vacuum-size="${RUNNER_GC_JOURNAL_MAX:-200M}" >/dev/null 2>&1 || true
    log "journal: vacuumed to ${RUNNER_GC_JOURNAL_MAX:-200M}"
  fi
else
  log "apt/journal: not root; skipping (the hourly timer covers these)"
fi

log "done — / : $(_df_root)"
