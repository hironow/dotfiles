#!/usr/bin/env bash

# ==============================================================================
# Install the runner disk GC mechanism inside a WSL/Linux runner host (ADR 0035)
# ------------------------------------------------------------------------------
# Idempotent. Must run as root (sudo) — it writes to /usr/local/bin and
# /etc/systemd. Installs three independent brakes:
#
#   1. runner-gc.timer   — hourly floor so idle drift still gets collected
#   2. job-completed hook — GC immediately after every job (the ideal moment)
#   3. journald SystemMaxUse cap — stops the journal growing without bound
#
# Re-running after editing scripts/runner_gc.sh re-copies the payload, so the
# repo stays the single source of truth.
# ==============================================================================

set -eu

RETENTION="${RUNNER_GC_RETENTION:-2h}"
JOURNAL_MAX="${RUNNER_GC_JOURNAL_MAX:-200M}"

_here="$(cd "$(dirname "$0")" && pwd)"
_src="${_here}/runner_gc.sh"
_dest="/usr/local/bin/runner-gc"

# --- Windows host dispatch --------------------------------------------------
# The runner (and therefore everything this installs) lives inside WSL. Re-enter
# as root there, translating the Git-Bash path (/c/...) to the WSL mount
# (/mnt/c/...) so the distro can read the repo.
case "$(uname -s)" in
  MINGW* | MSYS* | CYGWIN*)
    _distro="${RUNNER_GC_WSL_DISTRO:-Ubuntu}"
    _wsl_here="$(cygpath -m "$_here" | sed -E 's|^([A-Za-z]):|/mnt/\L\1|')"
    echo "--- host is Windows; installing for BOTH runners ---"
    # Git Bash rewrites any argument that looks like a unix path into a Windows
    # one, which would turn /mnt/c/... into <msys-root>/mnt/c/... before wsl.exe
    # ever sees it. Disable the conversion for these calls.
    export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'
    _rc=0

    echo "==> WSL distro '${_distro}'"
    wsl.exe -d "$_distro" -u root -e env \
      "RUNNER_GC_RETENTION=${RETENTION}" \
      "RUNNER_GC_JOURNAL_MAX=${JOURNAL_MAX}" \
      bash "${_wsl_here}/install_runner_gc.sh" || _rc=$?

    echo "==> native Windows runner"
    _ps1="${_here}/install_runner_gc_win.ps1"
    if [ -f "$_ps1" ]; then
      powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass \
        -File "$(cygpath -w "$_ps1")" -Retention "$RETENTION" || _rc=$?
    else
      echo "    ${_ps1} missing; skipping"
    fi

    exit "$_rc"
    ;;
esac

if [ "$(id -u)" -ne 0 ]; then
  echo "ERROR: must run as root — try: sudo bash $0" >&2
  exit 1
fi
[ -f "$_src" ] || { echo "ERROR: $_src not found" >&2; exit 1; }

echo "--- 🧹 Installing runner disk GC (retention=${RETENTION}) ---"

# 1. payload -----------------------------------------------------------------
install -m 0755 "$_src" "$_dest"
echo "[1/4] script: $_dest"

# 2. systemd timer -----------------------------------------------------------
cat >/etc/systemd/system/runner-gc.service <<EOF
[Unit]
Description=GitHub Actions runner disk GC (dotfiles ADR 0035)
Documentation=https://github.com/hironow/dotfiles

[Service]
Type=oneshot
Environment=RUNNER_GC_RETENTION=${RETENTION}
Environment=RUNNER_GC_JOURNAL_MAX=${JOURNAL_MAX}
ExecStart=${_dest}
Nice=10
IOSchedulingClass=idle
EOF

cat >/etc/systemd/system/runner-gc.timer <<'EOF'
[Unit]
Description=Hourly GitHub Actions runner disk GC (dotfiles ADR 0035)

[Timer]
OnCalendar=hourly
# Catch up after the WSL distro was stopped (laptop suspend, wsl --shutdown).
Persistent=true
RandomizedDelaySec=5m

[Install]
WantedBy=timers.target
EOF
echo "[2/4] systemd: runner-gc.service + runner-gc.timer"

# 3. journald cap ------------------------------------------------------------
mkdir -p /etc/systemd/journald.conf.d
cat >/etc/systemd/journald.conf.d/99-runner-gc.conf <<EOF
# Managed by dotfiles scripts/install_runner_gc.sh (ADR 0035).
[Journal]
SystemMaxUse=${JOURNAL_MAX}
EOF
echo "[3/4] journald: SystemMaxUse=${JOURNAL_MAX}"

# 4. runner job-completed hook ----------------------------------------------
# The runner reads `.env` from its own install dir at service start. Upsert the
# key (portable, no `sed -i`) so re-running never duplicates the line.
_hook_key="ACTIONS_RUNNER_HOOK_JOB_COMPLETED"
_installed_hook=0
for _dir in /home/*/actions-runner* /root/actions-runner* /opt/actions-runner*; do
  [ -d "$_dir" ] || continue
  [ -f "${_dir}/config.sh" ] || continue
  _env="${_dir}/.env"
  _tmp="$(mktemp)"
  if [ -f "$_env" ]; then
    grep -v "^${_hook_key}=" "$_env" >"$_tmp" || true
  fi
  printf '%s=%s\n' "$_hook_key" "$_dest" >>"$_tmp"
  # Preserve the runner user's ownership — the service runs unprivileged.
  _owner="$(stat -c '%u:%g' "$_dir")"
  mv "$_tmp" "$_env"
  chown "$_owner" "$_env"
  chmod 0644 "$_env"
  echo "[4/4] hook: ${_env} -> ${_hook_key}=${_dest}"
  _installed_hook=1
done
[ "$_installed_hook" -eq 1 ] || echo "[4/4] hook: no runner install found; skipped"

# --- activate ---------------------------------------------------------------
systemctl daemon-reload
systemctl enable --now runner-gc.timer
systemctl restart systemd-journald || true

echo "--- ✅ Installed. Next run: $(systemctl list-timers runner-gc.timer --no-pager --no-legend 2>/dev/null | awk '{print $1" "$2}') ---"
echo "NOTE: restart the runner service to pick up the job hook:"
echo "      systemctl restart actions.runner.*.service"
