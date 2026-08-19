#!/usr/bin/env bash

# ==============================================================================
# WSL ext4 corruption doctor: diagnose + repair runbook (ADR 0035 sibling)
# ------------------------------------------------------------------------------
# Failure mode (lived 2026-08-19): ext4 metadata corruption in the distro vhdx
# ("EXT4-fs error … bad block bitmap checksum") makes the kernel remount `/`
# read-only; WSL then boots the distro on a tmpfs overlay fallback, printing
# "An error occurred mounting the distribution disk, it was mounted read-only
# as a fallback". The distro LOOKS half-alive: shells open, but every write to
# the real filesystem is lost and services misbehave (the runner turns zombie).
#
# Advisory only, like wsl_compact.sh, and for the same reasons: the repair
# needs `wsl --shutdown` (self-hosted runner offline) plus an elevated
# `wsl --mount`, and an e2fsck against a misidentified or still-mounted device
# destroys the filesystem it was meant to save. This script diagnoses, picks a
# repair-capable helper distro, and prints the exact runbook for a human to
# execute with eyes on the output.
# ==============================================================================

set -eu

case "$(uname -s)" in
  MINGW* | MSYS* | CYGWIN*) ;;
  *)
    echo "ℹ️  Not a Windows host ($(uname -s)); WSL vhdx repair does not apply."
    exit 0
    ;;
esac

DISTRO="${RUNNER_GC_WSL_DISTRO:-Ubuntu}"

# shellcheck source=scripts/wsl_vhdx_lib.sh
. "$(dirname "${BASH_SOURCE[0]}")/wsl_vhdx_lib.sh"
_vhdx="$(wsl_vhdx_path "$DISTRO" || true)"
if [ -z "$_vhdx" ] || [ ! -f "$_vhdx" ]; then
  echo "⚠️  No ext4.vhdx found for distro '${DISTRO}' via the Lxss registry."
  echo "    Locate it with:  wsl --manage ${DISTRO} --get-location"
  exit 1
fi
_vhdx_w="$(cygpath -w "$_vhdx")"

echo "🩺 WSL ext4 doctor — distro '${DISTRO}'"
echo "    vhdx      : ${_vhdx}"

# --- Diagnosis ----------------------------------------------------------------
# The mount table is the authoritative signal: a healthy distro has `/` on
# ext4 rw; the fallback has `/` on overlay (or tmpfs), or ext4 mounted ro.
# dmesg is only corroboration — it is VM-global (errors from ANY distro appear
# everywhere), gone after a shutdown, and often root-gated.
_verdict="unknown"
if MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' wsl.exe -d "$DISTRO" -e true >/dev/null 2>&1; then
  _root="$(MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' \
    wsl.exe -d "$DISTRO" -e findmnt -no FSTYPE,OPTIONS / 2>/dev/null | tr -d '\0\r')"
  echo "    root mount: ${_root:-'(unreadable)'}"
  # Judge fstype + the FIRST mount option only: a healthy root carries
  # `errors=remount-ro` further down the option string, so any substring
  # match on "ro" flags every healthy distro as corrupted.
  # shellcheck disable=SC2086
  set -- $_root ""
  _fstype="$1"
  _firstopt="${2%%,*}"
  case "${_fstype}:${_firstopt}" in
    overlay:* | tmpfs:*)
      _verdict="fallback"
      echo "🔴 '/' is an overlay/tmpfs — WSL is running the READ-ONLY FALLBACK."
      ;;
    ext4:ro)
      _verdict="fallback"
      echo "🔴 '/' is mounted read-only — the kernel demoted it after an ext4 error."
      ;;
    ext4:rw)
      _verdict="healthy"
      echo "✅ '/' is ext4 rw — no read-only fallback."
      ;;
    *)
      echo "⚠️  Unrecognized root mount state; inspect manually."
      ;;
  esac
  # Corroboration only (root-gated on some kernels; best effort).
  _dmesg="$(MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' \
    wsl.exe -d "$DISTRO" -u root -e sh -c \
    "dmesg 2>/dev/null | grep -E 'EXT4-fs error|Remounting filesystem read-only' | tail -3" \
    2>/dev/null | tr -d '\0\r' || true)"
  if [ -n "$_dmesg" ]; then
    echo "    dmesg (corroboration — VM-global, may stem from another distro):"
    printf '%s\n' "$_dmesg" | sed 's/^/      /'
  fi
else
  _verdict="no-boot"
  echo "🔴 distro '${DISTRO}' does not start at all."
fi

if [ "$_verdict" = "healthy" ]; then
  exit 0
fi

# --- Helper distro selection --------------------------------------------------
# The fsck must run from a sibling WSL2 distro: docker-desktop* images are not
# general-purpose, WSL1 distros have no VM block-device access, and the helper
# must actually ship e2fsck. `wsl -l -v` output is UTF-16LE + CRLF, hence the
# NUL strip; the VERSION column is numeric and locale-safe.
_helper=""
while IFS= read -r _line; do
  _name="$(printf '%s' "$_line" | sed -e 's/^[* ]*//' | awk '{print $1}')"
  _ver="$(printf '%s' "$_line" | awk '{print $NF}')"
  [ -n "$_name" ] || continue
  [ "$_ver" = "2" ] || continue
  [ "$_name" = "$DISTRO" ] && continue
  case "$_name" in docker-desktop*) continue ;; esac
  if MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' \
    wsl.exe -d "$_name" -u root -e sh -c 'command -v e2fsck' >/dev/null 2>&1; then
    _helper="$_name"
    break
  fi
done <<EOF
$(MSYS_NO_PATHCONV=1 wsl.exe -l -v 2>/dev/null | tr -d '\0\r' | tail -n +2)
EOF

if [ -z "$_helper" ]; then
  cat <<EOF

⚠️  No repair-capable WSL2 helper distro found (need one besides '${DISTRO}',
    not docker-desktop, with e2fsck). Either install one:

        wsl --install -d Debian --no-launch

    or fall back to rebuilding the filesystem via export/import (slow, and the
    filesystem must still be readable):

        wsl --export ${DISTRO} ${DISTRO}-backup.tar
        wsl --unregister ${DISTRO}
        wsl --import ${DISTRO} <install-dir> ${DISTRO}-backup.tar
EOF
  exit 1
fi
echo "    helper    : ${_helper} (WSL2, has e2fsck)"

# --- Runbook ------------------------------------------------------------------
cat <<EOF

⚠️  The repair stops every distro — the self-hosted runner goes offline. Stop
    the runner service first if it still responds, and do not Ctrl-C the fsck.

Run from an ELEVATED PowerShell (wsl --mount needs Administrator):

    # 0. best effort: stop the runner so no job gets killed mid-flight
    wsl -d ${DISTRO} -u root -e sh -c "systemctl stop 'actions.runner.*' || true"

    # 1. stop every distro, then bring up the HELPER first — a bare wsl
    #    command with no VM running would boot the DEFAULT distro, which may
    #    be the corrupted one.
    wsl --shutdown
    wsl -d ${_helper} -e true

    # 2. snapshot block devices, attach the vhdx WITHOUT mounting, diff
    wsl -d ${_helper} -u root -e lsblk -ndo NAME,SIZE
    wsl --mount "${_vhdx_w}" --vhd --bare
    wsl -d ${_helper} -u root -e lsblk -ndo NAME,SIZE
    #    exactly ONE new device (whole-disk ext4, e.g. sdd — no partition
    #    suffix) must appear; abort if zero or several.

    # 3. sanity: right filesystem, and PROVE it is not mounted anywhere
    wsl -d ${_helper} -u root -e blkid /dev/sdX
    wsl -d ${_helper} -u root -e grep /dev/sdX /proc/mounts   # must print nothing

    # 4. dry-run first, read the damage, then repair (exit 1 = fixed = OK)
    wsl -d ${_helper} -u root -e e2fsck -fn /dev/sdX
    wsl -d ${_helper} -u root -e e2fsck -fy /dev/sdX

    # 5. ALWAYS detach — a vhdx left attached has blocked WSL from starting
    wsl --unmount "${_vhdx_w}"

    # 6. restart and verify '/' is ext4 rw again
    wsl --shutdown
    wsl -d ${DISTRO} -e findmnt -no FSTYPE,OPTIONS /
    wsl -d ${DISTRO} -e sh -c "systemctl start 'actions.runner.*' || true"

If e2fsck cannot repair it, rebuild via export/import (needs the filesystem
readable) or restore from backup:

    wsl --export ${DISTRO} ${DISTRO}-backup.tar
EOF
exit 2
