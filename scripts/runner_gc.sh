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
DIAG_DAYS="${RUNNER_GC_DIAG_DAYS:-7}"
# How many major.minor SERIES of each tool survive (the newest patch of each).
# Must exceed the number of series the workflows on this runner pin between
# them; see the toolcache section below for why series, not versions.
TOOLCACHE_KEEP="${RUNNER_GC_TOOLCACHE_KEEP:-5}"
# Set by the root->runner-user re-entry below: do the docker leg only, so the
# child neither recurses nor repeats the root-only apt/journal/_diag work.
DOCKER_ONLY="${RUNNER_GC_DOCKER_ONLY:-0}"

log() { printf '[runner-gc] %s %s\n' "$(date -Is)" "$*"; }

# --- Windows host: collect BOTH runners -------------------------------------
# This box hosts two self-hosted runners — one inside the WSL distro and one
# native Windows one — so `just runner-gc` from the Windows side must sweep
# both.
case "$(uname -s)" in
  MINGW* | MSYS* | CYGWIN*)
    _here="$(cd "$(dirname "$0")" && pwd)"
    _distro="${RUNNER_GC_WSL_DISTRO:-Ubuntu}"
    _rc=0

    log "host is Windows; collecting WSL distro '${_distro}'"
    # Git Bash would rewrite /usr/local/bin/runner-gc.sh into a Windows path
    # before wsl.exe sees it; disable the conversion for these calls.
    export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'

    # Prefer the installed payload, but fall back to this checkout when
    # runner-gc-install has not run: hard-coding the installed path made a
    # first `just runner-gc` die with `No such file or directory` (exit 127)
    # and collect nothing, which reads as "the GC is broken" rather than
    # "the GC is not installed yet".
    _wsl_self="$(cygpath -m "${_here}/runner_gc.sh" | sed -E 's|^([A-Za-z]):|/mnt/\L\1|')"
    wsl.exe -d "$_distro" -u root -e env \
      "RUNNER_GC_RETENTION=${RETENTION}" \
      "RUNNER_GC_FORCE=${FORCE}" \
      sh -c "if [ -x /usr/local/bin/runner-gc.sh ]; then exec /usr/local/bin/runner-gc.sh; else echo '[runner-gc] not installed; running from the checkout (run: just runner-gc-install)'; exec bash '${_wsl_self}'; fi" || _rc=$?

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
#
# The job-completed hook is invoked *by* Runner.Worker, so the worker of the job
# we are collecting after is always alive and always our own ancestor. Counting
# it would make the hook — the brake that fires at the ideal moment — skip every
# single time. Only a worker that is NOT in our ancestry belongs to a concurrent
# job, and only that is a reason to back off.
_ancestor_pids() {
  _p="$$"
  while [ -n "$_p" ] && [ "$_p" -gt 1 ]; do
    printf '%s\n' "$_p"
    _p="$(ps -o ppid= -p "$_p" 2>/dev/null | tr -d ' ')"
  done
}

_foreign_worker() {
  _anc=" $(_ancestor_pids | tr '\n' ' ') "
  for _w in $(pgrep -x Runner.Worker 2>/dev/null); do
    case "$_anc" in
      *" $_w "*) continue ;;
      *) return 0 ;;
    esac
  done
  return 1
}

if [ "$FORCE" != "1" ] && _foreign_worker; then
  log "SKIP: another runner job is executing (Runner.Worker alive)"
  exit 0
fi

_is_root() { [ "$(id -u)" -eq 0 ]; }

_df_root() { df -h / | awk 'NR==2 {print $3" used, "$4" avail ("$5")"}'; }

log "start (retention=${RETENTION}) — / : $(_df_root)"

# --- Runner installs --------------------------------------------------------
# Same globs the installer uses to place the job hook, so both agree on what
# counts as a runner install.
# RUNNER_GC_ROOT sweeps one named install instead of probing the usual places,
# mirroring the Windows leg's -RunnerRoot. The workspace sweep deletes whole
# trees, so it has to be exercisable against a synthetic runner rather than only
# against the live one — on a busy box the idle window it needs may never come.
_each_runner_dir() {
  if [ -n "${RUNNER_GC_ROOT:-}" ]; then
    [ -d "$RUNNER_GC_ROOT" ] && printf '%s\n' "$RUNNER_GC_ROOT"
    return 0
  fi
  for _d in /home/*/actions-runner* /root/actions-runner* /opt/actions-runner*; do
    [ -d "$_d" ] || continue
    [ -f "${_d}/config.sh" ] || continue
    printf '%s\n' "$_d"
  done
}

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

# The docker-only re-entry (see below) stops here: everything past this point
# is either root-only or would be repeated once per runner user.
if [ "$DOCKER_ONLY" = "1" ]; then
  _docker_gc
  log "done (docker-only) — / : $(_df_root)"
  exit 0
fi

_docker_gc

# --- Reach the runner's own daemon ------------------------------------------
# The hourly timer runs as root, and root's docker context is NOT the runner's.
# Where the runner drives ROOTLESS docker, root resolves to /var/run/docker.sock
# — a different daemon, usually empty — so every prune above "succeeds" against
# nothing while the real hoard at /run/user/<uid>/docker.sock keeps growing.
# `docker info` succeeds against that empty daemon too, so nothing surfaces the
# miss: the sweep exits 0 having reclaimed zero.
#
# So re-enter the docker leg as each runner's owning user, whose context points
# at the daemon its jobs actually dirty. Root's own leg above is kept, which is
# what a rootful-only host needs — neither topology regresses.
if _is_root && command -v runuser >/dev/null 2>&1; then
  _each_runner_dir | while read -r _rdir; do
    _ruser="$(stat -c '%U' "$_rdir" 2>/dev/null || true)"
    _ruid="$(stat -c '%u' "$_rdir" 2>/dev/null || true)"
    if [ -z "$_ruser" ] || [ "$_ruser" = "root" ] || [ -z "$_ruid" ]; then
      continue
    fi
    _rhome="$(getent passwd "$_ruser" | cut -d: -f6)"
    [ -n "$_rhome" ] || continue
    log "docker: re-entering as ${_ruser} (uid ${_ruid}) for its own daemon"
    runuser -u "$_ruser" -- env \
      HOME="$_rhome" \
      XDG_RUNTIME_DIR="/run/user/${_ruid}" \
      RUNNER_GC_DOCKER_ONLY=1 \
      RUNNER_GC_RETENTION="$RETENTION" \
      RUNNER_GC_FORCE="$FORCE" \
      "$0" || log "docker: re-entry as ${_ruser} failed (non-fatal)"
  done
elif _is_root; then
  log "docker: runuser missing; cannot reach a rootless runner daemon"
fi

# --- Runner _diag logs ------------------------------------------------------
# The runner never rotates these; left alone they accumulate for the life of
# the box. Age-based so the current job's logs are untouched.
_each_runner_dir | while read -r _rdir; do
  [ -d "${_rdir}/_diag" ] || continue
  _n="$(find "${_rdir}/_diag" -type f -mtime +"${DIAG_DAYS}" 2>/dev/null | wc -l)"
  [ "$_n" -gt 0 ] || continue
  find "${_rdir}/_diag" -type f -mtime +"${DIAG_DAYS}" -delete 2>/dev/null || true
  log "_diag: removed ${_n} file(s) older than ${DIAG_DAYS}d in ${_rdir}"
done

# --- Toolcache generations --------------------------------------------------
# `actions/setup-*` stacks _work/_tool/<tool>/<version>/ per release and never
# removes the old one (CodeQL alone is ~1.7 GB a generation).
#
# Reap by SERIES, not by count. Workflows pin a series — `go-version: 1.25.x`,
# `node-version: 22.x`, `python-version: 3.13` — and setup-* resolves it to the
# newest patch within that series. So "keep the newest N versions" evicts what
# the matrices still need: three repos on this runner pin Python 3.10, 3.13 and
# 3.14 between them, and keeping only the newest would re-download two of them
# on every job. Keeping the newest patch of each series protects exactly what a
# series pin resolves to, while still reaping the patches it has superseded
# (1.25.0 and 1.25.8 sat behind 1.25.11). TOOLCACHE_KEEP then bounds how many
# series survive so the cache cannot grow forever either.
#
# Last-use would be the natural axis, matching the 2h budget elsewhere, but
# there is no usable signal: the filesystem is `relatime`, and any sweep that
# walks _tool (this one included) rewrites every atime it reads. mtime is the
# install time, not the use time — Python 3.10.20 was installed seven weeks ago
# and is still pinned.
#
# Two traps, both silent. Ordering MUST be `sort -V`: lexically `1.25.8` sorts
# above `1.25.11`, so a plain sort keeps the older tool and deletes the newest.
# And the unit of deletion MUST be the whole <version>/ directory, because the
# `<version>/<arch>.complete` marker the runner trusts lives inside it —
# removing anything narrower leaves the cache claiming a tool that is gone.
#
# This re-checks for a live job even under FORCE: losing build cache only costs
# time, but deleting a <version>/ a running job already resolved fails its next
# step outright.
_tool_series() { # 1.25.11 -> 1.25 ; 2.26.2 -> 2.26 ; anything else -> itself
  case "$1" in
    *.*.*) printf '%s' "${1%.*}" ;;
    *) printf '%s' "$1" ;;
  esac
}

# Independent of FORCE, but still ancestry-aware: under the job-completed hook
# our own worker has finished its steps, while a *concurrent* job may be
# mid-resolve and would lose a version out from under it.
if _foreign_worker; then
  log "toolcache: SKIP (another job is executing; deleting an in-use version breaks it)"
else
  _each_runner_dir | while read -r _rdir; do
    [ -d "${_rdir}/_work/_tool" ] || continue
    for _tool in "${_rdir}"/_work/_tool/*/; do
      [ -d "$_tool" ] || continue
      mapfile -t _vers < <(
        find "$_tool" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' 2>/dev/null | sort -V
      )
      [ "${#_vers[@]}" -gt 0 ] || continue

      # Newest TOOLCACHE_KEEP series, then the newest patch inside each.
      mapfile -t _keep_series < <(
        for _v in "${_vers[@]}"; do _tool_series "$_v"; printf '\n'; done |
          sort -V -u | tail -n "$TOOLCACHE_KEEP"
      )
      _keep=()
      for _s in "${_keep_series[@]}"; do
        _newest=""
        for _v in "${_vers[@]}"; do
          if [ "$(_tool_series "$_v")" = "$_s" ]; then _newest="$_v"; fi
        done
        if [ -n "$_newest" ]; then _keep+=("$_newest"); fi
      done

      for _v in "${_vers[@]}"; do
        _hit=0
        for _k in "${_keep[@]}"; do
          if [ "$_v" = "$_k" ]; then _hit=1; break; fi
        done
        if [ "$_hit" -eq 1 ]; then continue; fi
        rm -rf "${_tool}${_v}"
        log "toolcache: removed $(basename "$_tool")/${_v}"
      done
    done
  done
fi

# --- Runner workspaces ------------------------------------------------------
# The mirror of the Windows leg, and the larger half of the problem: `_work/`
# held 23 GB of checkouts here against 3 GB of toolcache. Nothing rotates them
# and the runner is happy to re-clone.
#
# Aged on a marker file rather than the directory mtime: a checkout's top-level
# mtime tracks when files were added or removed directly in it, not when a
# build rewrote something three levels down, so a hot workspace can read cold.
_marker='.runner-gc-last-used'

# Retention is docker's syntax (2h, 90m, 7d); find wants minutes.
_retention_minutes() {
  case "$RETENTION" in
    *m) printf '%s' "${RETENTION%m}" ;;
    *h) printf '%s' "$(( ${RETENTION%h} * 60 ))" ;;
    *d) printf '%s' "$(( ${RETENTION%d} * 1440 ))" ;;
    *) printf '120' ;;   # never widen the window because the input was odd
  esac
}
_ret_min="$(_retention_minutes)"

# The runner owns these; every sibling is a repo checkout. Matching a leading
# underscore instead would permanently exclude a repo actually named `_foo`.
_runner_managed=" _actions _diag _PipelineMapping _temp _tool _update "

# A concurrent job may be building inside one of these trees, so back off — with
# one carve-out: an explicit RUNNER_GC_ROOT names a specific install, which the
# timer and the hook never do. Without it the destructive path could only ever
# be exercised on a runner that happens to be idle, and on a busy box that
# window may not come for hours. The .runner guard and the live-workspace
# exclusions still apply.
if [ -z "${RUNNER_GC_ROOT:-}" ] && _foreign_worker; then
  log "workspaces: SKIP (another job is executing)"
else
  _each_runner_dir | while read -r _rdir; do
    # Deleting whole trees, so demand proof this really is a runner install.
    [ -f "${_rdir}/.runner" ] || { log "workspaces: ${_rdir} has no .runner; skipped"; continue; }
    _work="${_rdir}/_work"
    [ -d "$_work" ] || continue

    # Whatever the ageing says, never touch the checkout a job is using: the
    # hook fires between steps of the job that owns these.
    _live=""
    for _c in "${RUNNER_WORKSPACE:-}" "${GITHUB_WORKSPACE:-}"; do
      [ -n "$_c" ] || continue
      # Resolve to an absolute path when it exists; fall back to the raw value.
      _abs="$(cd "$_c" 2>/dev/null && pwd)"
      [ -n "$_abs" ] || _abs="$_c"
      _live="${_live} ${_abs}"
    done

    # Stamp the workspace of the job that just finished, so the next sweep ages
    # it from now rather than from whenever the tree last changed shape.
    if [ -n "${GITHUB_REPOSITORY:-}" ]; then
      _fin="${_work}/${GITHUB_REPOSITORY##*/}"
      if [ -d "$_fin" ]; then
        _live="${_live} ${_fin}"
        touch "${_fin}/${_marker}" 2>/dev/null || true
      fi
    fi

    for _ws in "$_work"/*/; do
      [ -d "$_ws" ] || continue
      _ws="${_ws%/}"
      _name="${_ws##*/}"
      case "$_runner_managed" in *" $_name "*) continue ;; esac
      case " $_live " in *" $_ws "*) continue ;; esac

      _probe="${_ws}/${_marker}"
      [ -f "$_probe" ] || _probe="$_ws"
      [ -n "$(find "$_probe" -maxdepth 0 -mmin +"$_ret_min" 2>/dev/null)" ] || continue

      _sz="$(du -shx "$_ws" 2>/dev/null | cut -f1)"
      rm -rf "$_ws" && log "workspaces: collected ${_name} (${_sz}, idle > ${RETENTION})"
    done
  done
fi

# --- Superseded runner versions ---------------------------------------------
# self-update leaves the previous bin.<ver>/externals.<ver> behind (1.5 GB here)
# plus the installer archive it unpacked. A 24 h floor rather than the 2 h
# retention: the runner stages an update and only then swings the symlinks, so
# a short window could catch one mid-flight. Reaped only where bin/externals
# really are symlinks — a plain install keeps the live runner in bin.* itself.
_each_runner_dir | while read -r _rdir; do
  if [ ! -L "${_rdir}/bin" ] || [ ! -L "${_rdir}/externals" ]; then continue; fi
  _live_bin="$(readlink -f "${_rdir}/bin" 2>/dev/null)"
  _live_ext="$(readlink -f "${_rdir}/externals" 2>/dev/null)"
  for _old in "${_rdir}"/bin.* "${_rdir}"/externals.*; do
    [ -d "$_old" ] || continue
    _real="$(readlink -f "$_old" 2>/dev/null)"
    [ "$_real" = "$_live_bin" ] && continue
    [ "$_real" = "$_live_ext" ] && continue
    [ -n "$(find "$_old" -maxdepth 0 -mmin +1440 2>/dev/null)" ] || continue
    _sz="$(du -shx "$_old" 2>/dev/null | cut -f1)"
    rm -rf "$_old" && log "runner: removed superseded $(basename "$_old") (${_sz})"
  done
  # The tarball the current version was unpacked from, and any staged update.
  for _junk in "${_rdir}"/actions-runner-*.tar.gz "${_rdir}/_work/_update"; do
    [ -e "$_junk" ] || continue
    [ -n "$(find "$_junk" -maxdepth 0 -mmin +1440 2>/dev/null)" ] || continue
    _sz="$(du -shx "$_junk" 2>/dev/null | cut -f1)"
    rm -rf "$_junk" && log "runner: removed $(basename "$_junk") (${_sz})"
  done
done

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

# --- Return the freed blocks to the host (root only) ------------------------
# Everything above only frees ext4 blocks *inside* the distro. The vhdx keeps
# them claimed from Windows until something discards them, which is why a big
# prune can leave C: unchanged and make the GC look useless.
#
# On a sparse vhdx — what WSL creates by default — `fstrim` punches those holes
# straight back out: no downtime, no elevation, the runner stays online. On this
# host one call returned 43.5 GB to C: immediately. A non-sparse vhdx simply
# ignores the discard, so this is unconditional; compaction (`just wsl-compact`)
# stays the fallback for that case.
if _is_root && command -v fstrim >/dev/null 2>&1; then
  if fstrim / >/dev/null 2>&1; then
    log "fstrim: freed blocks discarded back to the host"
  else
    log "fstrim: discard unsupported here (non-fatal; see just wsl-compact)"
  fi
fi

log "done — / : $(_df_root)"
