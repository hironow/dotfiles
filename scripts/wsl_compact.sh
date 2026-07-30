#!/usr/bin/env bash

# ==============================================================================
# WSL vhdx slack report + compaction guidance (ADR 0035)
# ------------------------------------------------------------------------------
# A WSL ext4.vhdx grows to its high-water mark and NEVER shrinks on its own:
# deleting 100 GB inside the distro leaves the Windows-side file just as large.
# scripts/runner_gc.sh stops the *growth*; only compaction returns the slack.
#
# Advisory only, like `just wsl-conf`. Compaction needs BOTH:
#   - Administrator (diskpart / Optimize-VHD open the volume directly), and
#   - the distro fully stopped (`wsl --shutdown`), which kills the runner.
# Doing that behind the user's back would interrupt CI, so this only measures
# and prints the exact commands.
#
# NOTE on sparse VHD: `wsl --manage <distro> --set-sparse true` would make the
# slack return automatically, but Microsoft currently ships it DISABLED behind
# `--allow-unsafe` over a data-corruption risk. Not recommended on a CI host.
# ==============================================================================

set -eu

case "$(uname -s)" in
  MINGW* | MSYS* | CYGWIN*) ;;
  *)
    echo "ℹ️  Not a Windows host ($(uname -s)); WSL vhdx compaction does not apply."
    exit 0
    ;;
esac

DISTRO="${RUNNER_GC_WSL_DISTRO:-Ubuntu}"

_lad="$(cygpath -u "$LOCALAPPDATA" 2>/dev/null || printf '%s' "${LOCALAPPDATA:-}")"
_vhdx="$(find "${_lad}/wsl" -name 'ext4.vhdx' -print 2>/dev/null | head -1)"

if [ -z "$_vhdx" ]; then
  echo "⚠️  No ext4.vhdx found under ${_lad}/wsl (distro may be store-installed)."
  echo "    Locate it with:  wsl --manage ${DISTRO} --get-location"
  exit 0
fi

_host_bytes="$(stat -c '%s' "$_vhdx" 2>/dev/null || echo 0)"
_host_gb="$((_host_bytes / 1024 / 1024 / 1024))"

echo "🗜️  WSL virtual disk"
echo "    file      : ${_vhdx}"
echo "    host size : ${_host_gb} GB"

# Used-inside figure comes from the distro itself; skip if it will not start.
# MSYS would rewrite the bare `/` argument into the Git-Bash root before
# wsl.exe sees it, so the measurement must run with path conversion off.
_used_gb=""
_df="$(MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' \
  wsl.exe -d "$DISTRO" -e bash -lc "df -BG / | awk 'NR==2 {print \$3}'" 2>/dev/null | tr -dc '0-9')"
[ -n "$_df" ] && _used_gb="$_df"

if [ -n "$_used_gb" ]; then
  echo "    used      : ${_used_gb} GB inside the distro"
  _slack=$((_host_gb - _used_gb))
  echo "    slack     : ~${_slack} GB reclaimable by compaction"
  if [ "$_slack" -lt 10 ]; then
    echo "✅ Slack is small; compaction is not worth the CI interruption yet."
    exit 0
  fi
else
  echo "    used      : (distro did not start; cannot measure)"
fi

cat <<EOF

⚠️  Compaction stops the distro — the self-hosted runner goes offline for the
    duration. Do it while no job is queued.

Run from an ELEVATED PowerShell:

    # 1. confirm the runner is idle (expect no Runner.Worker)
    wsl -d ${DISTRO} -e pgrep -x Runner.Worker

    # 2. stop every distro
    wsl --shutdown

    # 3. compact (diskpart works on Home editions; Optimize-VHD needs Hyper-V)
    diskpart
      select vdisk file="$(cygpath -w "$_vhdx")"
      attach vdisk readonly
      compact vdisk
      detach vdisk
      exit

    # 4. bring the runner back
    wsl -d ${DISTRO} -e systemctl is-active 'actions.runner.*'
EOF
