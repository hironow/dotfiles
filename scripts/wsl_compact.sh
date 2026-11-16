#!/usr/bin/env bash

# ==============================================================================
# WSL vhdx slack report + compaction guidance (ADR 0035)
# ------------------------------------------------------------------------------
# A WSL ext4.vhdx grows to its high-water mark and NEVER shrinks on its own:
# deleting 100 GB inside the distro leaves the Windows-side file just as large.
# scripts/runner_gc.sh stops the *growth*; only compaction returns the slack.
#
# Advisory only, like `just wsl-conf`. Compaction of a non-sparse vhdx needs:
#   - Administrator (diskpart / Optimize-VHD open the volume directly), and
#   - the distro fully stopped (`wsl --shutdown`), which kills the runner.
# Doing that behind the user's back would interrupt CI, so this only measures
# and prints the exact commands. A sparse vhdx gets no compaction steps:
# diskpart and Optimize-VHD refuse it ("must not be sparse").
#
# NOTE on sparse VHD: this host's WSL (3.0.5) offers `--set-sparse` without the
# `--allow-unsafe` older builds demanded, and only warns that it is
# experimental. The repo still does not switch it on (ADR 0035), and
# `wsl --manage --move` drops the flag anyway, so the state is measured, never
# assumed. It also reports who else can open the vhdx: it holds the whole
# distro, runner credentials included, and a move inherits the target
# volume's ACL.
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
  echo "⚠️  No vhdx found for distro '${DISTRO}' via the Lxss registry."
  wsl_vhdx_locate_hint
  exit 0
fi
_vhdx_w="$(cygpath -w "$_vhdx")"
_base_w="$(cygpath -w "$(dirname "$_vhdx")")"

# Logical size is the high-water mark the vhdx has ever reached; it never goes
# down. What actually occupies the volume is the ALLOCATED size, which differs
# whenever the file is sparse. Reporting the logical figure overstates the
# reclaimable slack by exactly the sparse gap (measured here: 227 GB logical vs
# 174 GB allocated, i.e. 53 GB of phantom "slack").
_logical_bytes="$(stat -c '%s' "$_vhdx" 2>/dev/null || echo 0)"
_ondisk_bytes="$(du -B1 -s "$_vhdx" 2>/dev/null | cut -f1)"
[ -n "$_ondisk_bytes" ] || _ondisk_bytes="$_logical_bytes"
_logical_gb="$((_logical_bytes / 1024 / 1024 / 1024))"
_ondisk_gb="$((_ondisk_bytes / 1024 / 1024 / 1024))"

# The sparse flag is the file attribute, read through .NET. fsutil's verdict is
# a localised sentence, and the English "This file is NOT set as sparse"
# contains the word a grep would look for.
_facts="$(wsl_vhdx_facts "$_vhdx_w" || true)"
_sparse="$(printf '%s\n' "$_facts" | awk '$1 == "sparse" { print $2; exit }')"
case "$_sparse" in 0 | 1) ;; *) _sparse="?" ;; esac
_untrusted="$(printf '%s\n' "$_facts" | wsl_vhdx_untrusted_sids)"
_user_sid="$(printf '%s\n' "$_facts" | awk '$1 == "user" { print $2; exit }')"

echo "🗜️  WSL virtual disk"
echo "    file      : ${_vhdx}"
echo "    logical   : ${_logical_gb} GB (high-water mark; never shrinks)"
echo "    on disk   : ${_ondisk_gb} GB (what the volume actually gives up)"
case "$_sparse" in
  1) echo "    sparse    : yes — freed blocks return to Windows on their own" ;;
  0) echo "    sparse    : no — freed blocks stay claimed until compaction" ;;
  *) echo "    sparse    : unknown — could not read the file attribute" ;;
esac

# Reported before the slack figures, whose small-slack exit would swallow it.
case "$_untrusted" in
  "") echo "    ACL       : only this user, SYSTEM, Administrators and WSL itself" ;;
  "?") echo "    ACL       : unknown — could not read it; check with: icacls \"${_vhdx_w}\"" ;;
  *)
    echo
    echo "⚠️  WARN: these accounts can open this vhdx, which holds the whole distro"
    echo "    (runner credentials included):"
    printf '%s\n' "$_untrusted" | sed 's/^/      /'
    echo "    Names: icacls \"${_vhdx_w}\""
    echo "    Fix the folder, not the file (a file-only fix is lost with the next vhdx;"
    echo "    /inheritance:r keeps the entries WSL added itself):"
    echo "      icacls \"${_base_w}\" /inheritance:r /grant:r \"*S-1-5-18:(OI)(CI)F\" \"*S-1-5-32-544:(OI)(CI)F\" \"*${_user_sid:-<your SID>}:(OI)(CI)F\""
    echo
    ;;
esac

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
  if [ "$_sparse" = "1" ]; then
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

if [ "$_sparse" = "1" ]; then
  cat <<EOF

ℹ️  This vhdx is sparse, so space freed inside the distro (\`just runner-gc\`,
    \`just disk-gc\`) already returns to Windows on its own, without stopping
    anything. No compaction steps follow: diskpart and Optimize-VHD refuse a
    sparse vhdx ("must not be sparse"), and the \`wsl --manage ${DISTRO} --compact\`
    in this host's \`wsl --help\` is reported to refuse it too (not verified here).
    Returning the residual slack needs \`wsl --manage ${DISTRO} --set-sparse false\`
    first, which can grow the file on disk by up to ~$((_logical_gb - _ondisk_gb)) GB
    (logical minus on disk) before a compaction shrinks it.
EOF
  exit 0
fi

if [ "$_sparse" != "0" ]; then
  cat <<EOF

ℹ️  The sparse attribute could not be read, so no compaction steps are shown:
    diskpart refuses a sparse vhdx. Check by hand:
      fsutil sparse queryflag "${_vhdx_w}"
EOF
  exit 0
fi

cat <<EOF

⚠️  Compaction stops the distro — the self-hosted runner goes offline for the
    duration. Do it while no job is queued.

Run from an ELEVATED PowerShell:

    # 1. confirm the runner is idle (expect no Runner.Worker)
    wsl -d ${DISTRO} -e pgrep -x Runner.Worker

    # 2. stop every distro
    wsl --shutdown

    # 3. compact (diskpart works on Home editions; Optimize-VHD needs Hyper-V;
    #    the \`wsl --manage ${DISTRO} --compact\` in this host's \`wsl --help\` is
    #    not verified here)
    diskpart
      select vdisk file="${_vhdx_w}"
      attach vdisk readonly
      compact vdisk
      detach vdisk
      exit

    # 4. bring the runner back
    wsl -d ${DISTRO} -e systemctl is-active 'actions.runner.*'
EOF
