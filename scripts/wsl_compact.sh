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

# Resolve the vhdx for THE TARGET DISTRO (shared with wsl_fsck.sh).
# shellcheck source=scripts/wsl_vhdx_lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/wsl_vhdx_lib.sh"
_vhdx="$(wsl_vhdx_path "$DISTRO" || true)"

if [ -z "$_vhdx" ] || [ ! -f "$_vhdx" ]; then
  echo "⚠️  No ext4.vhdx found for distro '${DISTRO}' via the Lxss registry."
  echo "    Locate it with:  wsl --manage ${DISTRO} --get-location"
  exit 0
fi

# Logical size is the high-water mark the vhdx has ever reached; it never goes
# down. What actually occupies C: is the ALLOCATED size, which differs whenever
# the file is sparse — and a WSL vhdx usually is. Reporting the logical figure
# overstates the reclaimable slack by exactly the sparse gap (measured here:
# 227 GB logical vs 174 GB allocated, i.e. 53 GB of phantom "slack").
_logical_bytes="$(stat -c '%s' "$_vhdx" 2>/dev/null || echo 0)"
_ondisk_bytes="$(du -B1 -s "$_vhdx" 2>/dev/null | cut -f1)"
[ -n "$_ondisk_bytes" ] || _ondisk_bytes="$_logical_bytes"
_logical_gb="$((_logical_bytes / 1024 / 1024 / 1024))"
_ondisk_gb="$((_ondisk_bytes / 1024 / 1024 / 1024))"

# `fsutil sparse queryflag` is the authority; its wording is localised, so key
# off the exit status plus the presence of the flag rather than the message.
_sparse=0
if fsutil sparse queryflag "$(cygpath -w "$_vhdx")" 2>/dev/null | grep -qi 'sparse'; then
  _sparse=1
fi

echo "🗜️  WSL virtual disk"
echo "    file      : ${_vhdx}"
echo "    logical   : ${_logical_gb} GB (high-water mark; never shrinks)"
echo "    on disk   : ${_ondisk_gb} GB (what C: actually gives up)"
if [ "$_sparse" -eq 1 ]; then
  echo "    sparse    : yes — freed blocks return to Windows on their own"
else
  echo "    sparse    : no — freed blocks stay claimed until compaction"
fi

# Used-inside figure comes from the distro itself; skip if it will not start.
# MSYS would rewrite the bare `/` argument into the Git-Bash root before
# wsl.exe sees it, so the measurement must run with path conversion off.
_used_gb=""
_df="$(MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' \
  wsl.exe -d "$DISTRO" -e bash -lc "df -BG / | awk 'NR==2 {print \$3}'" 2>/dev/null | tr -dc '0-9')"
[ -n "$_df" ] && _used_gb="$_df"

if [ -n "$_used_gb" ]; then
  echo "    used      : ${_used_gb} GB inside the distro"
  # Slack is measured against the ALLOCATED size: blocks the host has handed
  # out that the guest filesystem is no longer using. The logical-minus-used
  # figure is not slack, it is slack plus everything already given back.
  _slack=$((_ondisk_gb - _used_gb))
  [ "$_slack" -lt 0 ] && _slack=0
  echo "    slack     : ~${_slack} GB actually reclaimable by compaction"
  if [ "$_sparse" -eq 1 ]; then
    echo "                (logical-minus-used would read ~$((_logical_gb - _used_gb)) GB;"
    echo "                 the difference has already been returned automatically)"
  fi
  if [ "$_slack" -lt 10 ]; then
    echo "✅ Slack is small; compaction is not worth the CI interruption yet."
    exit 0
  fi
else
  echo "    used      : (distro did not start; cannot measure)"
fi

if [ "$_sparse" -eq 1 ]; then
  cat <<'EOF'

ℹ️  This vhdx is sparse, so reclaiming space inside the distro (`just runner-gc`,
    `just disk-gc`) already returns it to C: without stopping anything. Compact
    only if the residual slack above is worth a CI outage.
EOF
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
