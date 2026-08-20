#!/usr/bin/env bash

# ==============================================================================
# Disk-GC status across both self-hosted runners (ADR 0035)
# ------------------------------------------------------------------------------
# Answers one question: *is the collection actually happening?*
#
# This exists because "installed" and "working" turned out to be different
# things. The job-completed hook sat in `.env` looking correct for 877 jobs
# while the runner rejected it every single time — the runner validates the
# hook path and refuses anything not ending in .sh/.ps1/.js, and the failure
# only ever surfaced inside the job's own Worker log. So this reports the
# *effect* (did a run happen, did the hook execute) rather than the presence of
# the wiring, and it re-checks the extension explicitly.
#
# Read-only. Shows the Windows and WSL legs together when run from Windows.
# ==============================================================================

set -eu

DISTRO="${RUNNER_GC_WSL_DISTRO:-Ubuntu}"
TASK="${RUNNER_GC_TASK_NAME:-dotfiles-runner-gc}"
AUTOTASK="${RUNNER_GC_AUTOSTART_TASK_NAME:-dotfiles-wsl-autostart}"

_win=0
case "$(uname -s)" in
  MINGW* | MSYS* | CYGWIN*) _win=1 ;;
esac

# Captured ONCE, before either leg runs: the WSL probe itself boots the
# distro, so any check made after it would always read "running" — an
# order-dependent silent pass. --quiet keeps the output to bare names, and
# WSL_UTF8=1 (with a \0-strip fallback) tames wsl.exe's UTF-16 default.
_distro_running=unknown
if [ "$_win" -eq 1 ]; then
  if MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' WSL_UTF8=1 \
      wsl.exe --list --quiet --running 2>/dev/null | tr -d '\r\0' | grep -qxF "$DISTRO"; then
    _distro_running=yes
  else
    _distro_running=no
  fi
fi

_ok()   { printf '  \033[32mOK\033[0m    %s\n' "$1"; }
_warn() { printf '  \033[33mWARN\033[0m  %s\n' "$1"; }
_bad()  { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; }
_info() { printf '        %s\n' "$1"; }

# The runner rejects a hook whose path does not end in one of these, so a value
# that "looks fine" can still never run. Anything with arguments is a command
# line, not a path, and fails the same validation.
_check_hook() {
  case "$1" in
    '')            _bad  "hook: not set" ;;
    *' '*)         _bad  "hook: has arguments, so it is not a path — the runner rejects it: $1" ;;
    *.sh | *.ps1 | *.js) _ok "hook: $1" ;;
    *)             _bad  "hook: missing a .sh/.ps1/.js extension — the runner rejects it: $1" ;;
  esac
}

# --- WSL leg ----------------------------------------------------------------
_wsl_status() {
  echo "── WSL leg (distro '${DISTRO}') ─────────────────────────────"
  if [ "$_win" -eq 1 ]; then
    MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*' \
      wsl.exe -d "$DISTRO" -u root -e bash -lc "$(_wsl_probe)" 2>&1 || \
      _bad "could not query the distro"
  else
    # shellcheck disable=SC2091  # deliberately executing the generated probe
    eval "$(_wsl_probe)"
  fi
  echo
}

# Emitted as one script so it runs in a single wsl.exe round trip.
_wsl_probe() {
  cat <<'PROBE'
_ok()   { printf '  \033[32mOK\033[0m    %s\n' "$1"; }
_warn() { printf '  \033[33mWARN\033[0m  %s\n' "$1"; }
_bad()  { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; }
_info() { printf '        %s\n' "$1"; }

if systemctl is-active runner-gc.timer >/dev/null 2>&1; then
  _ok "timer: active ($(systemctl is-enabled runner-gc.timer 2>/dev/null))"
  systemctl list-timers runner-gc.timer --no-pager --no-legend 2>/dev/null |
    awk '{print "next "$1" "$2" "$3", last "$5" "$6" "$7}' | while read -r l; do _info "$l"; done
else
  _bad "timer: not active (run: just runner-gc-install)"
fi

_res="$(systemctl show runner-gc.service -p Result --value 2>/dev/null)"
if [ "$_res" = "success" ]; then
  _ok "last timer run: success"
else
  _warn "last timer run: ${_res:-unknown}"
fi

# Effect, not wiring: did an unattended run actually collect anything?
_ran="$(journalctl -u runner-gc.service --since '-24 hours' -o cat 2>/dev/null | grep -c 'start (retention' || true)"
_skip="$(journalctl -u runner-gc.service --since '-24 hours' -o cat 2>/dev/null | grep -c 'SKIP:' || true)"
if [ "${_ran:-0}" -gt 0 ]; then
  _ok "timer runs in 24h: ${_ran} collected, ${_skip} skipped (a job was running)"
else
  _warn "timer runs in 24h: 0 collected, ${_skip:-0} skipped — jobs may be running back-to-back"
fi

if [ -x /usr/local/bin/runner-gc.sh ]; then
  _ok "payload: /usr/local/bin/runner-gc.sh"
else
  _bad "payload: /usr/local/bin/runner-gc.sh missing (run: just runner-gc-install)"
fi
[ -e /usr/local/bin/runner-gc ] && _warn "legacy extensionless payload still present: /usr/local/bin/runner-gc"

for _d in /home/*/actions-runner* /root/actions-runner* /opt/actions-runner*; do
  [ -f "${_d}/config.sh" ] || continue
  _h="$(grep -h '^ACTIONS_RUNNER_HOOK_JOB_COMPLETED=' "${_d}/.env" 2>/dev/null | cut -d= -f2-)"
  case "$_h" in
    # `continue`, because the verdict below only counts job logs newer than
    # `.env`. Without a hook key those jobs prove nothing, and printing a
    # green "accepted in all N job(s)" under a red "not set" reads as proof
    # the mechanism works.
    '')            _bad  "hook: not set in ${_d}/.env"; continue ;;
    *' '*)         _bad  "hook: has arguments, so it is not a path — the runner rejects it: $_h" ;;
    *.sh|*.ps1|*.js) _ok "hook: $_h" ;;
    *)             _bad  "hook: missing a .sh/.ps1/.js extension — the runner rejects it: $_h" ;;
  esac
  # The rejection is only ever logged inside the job, so surface it here.
  # Only jobs newer than the hook's own configuration count: rejections from
  # before a repair are history, and leaving them red would train the reader to
  # ignore this line.
  # Anchored on the hook path, and literal (-F): a Worker log also carries the
  # job payload, so grepping the bare phrase matches any PR whose body quotes
  # it. That fired here — a PR about this very message turned status red while
  # the hook was fine. The runner always names the path it refused, and a
  # payload quoting the phrase does not carry this runner's hook value.
  _rej="$(find "${_d}/_diag" -name 'Worker_*.log' -newer "${_d}/.env" \
    -exec grep -lF "${_h} is not a valid path to a script" {} + 2>/dev/null | wc -l)"
  _since="$(find "${_d}/_diag" -name 'Worker_*.log' -newer "${_d}/.env" 2>/dev/null | wc -l)"
  if [ "${_rej:-0}" -gt 0 ]; then
    _bad "hook REJECTED in ${_rej} of the ${_since} job(s) since it was configured"
  elif [ "${_since:-0}" -gt 0 ]; then
    _ok "hook: accepted in all ${_since} job(s) since it was configured"
  else
    _warn "hook: no jobs have run since it was configured — unproven"
  fi
done

# Reboot-recovery contract (mirrors wsl_autostart.ps1): systemd must be up
# and a runner unit loaded — `is-active 'actions.runner.*'` exits 0 on ZERO
# matches, so count units instead of trusting a glob.
_sys="$(systemctl is-system-running 2>/dev/null || true)"
case "$_sys" in
  running | degraded) : ;;
  *) _bad "systemd: ${_sys:-absent} — run: just wsl-conf, then wsl --shutdown" ;;
esac
_units="$(systemctl list-units --type=service --all --no-legend --plain 'actions.runner.*' 2>/dev/null | grep -c . || true)"
if [ "${_units:-0}" -eq 0 ]; then
  _bad "runner service: no actions.runner.* unit loaded"
else
  # pgrep exits 1 on zero matches; without `|| true` the `set -e` shell
  # running this probe on a native Linux host would abort mid-report.
  _lis="$(pgrep -cx Runner.Listener || true)"
  if [ "${_lis:-0}" -gt 1 ]; then
    _bad "runner: ${_lis} Runner.Listener processes — a duplicate was launched outside systemd"
  elif [ "${_lis:-0}" -eq 1 ]; then
    _ok "runner: single Runner.Listener"
  else
    _warn "runner: no Runner.Listener — service down?"
  fi
fi

# WSL terminates a distro ~1 min after its last CLIENT exits — systemd
# services inside do not count. The autostart task's keepalive client is what
# lets the runner outlive closed terminals. Bracketed pattern: unescaped it
# would match this probe's own command line.
_ka="$(pgrep -fc 'dotfiles-wsl-keepaliv[e]' || true)"
if [ "${_ka:-0}" -ge 1 ]; then
  _ok "keepalive: attached — distro survives closed terminals"
else
  _warn "keepalive: not attached — distro stops ~1min after the last terminal closes (run: just runner-gc-install)"
fi

printf '        disk: %s\n' "$(df -h / | awk 'NR==2 {print $3" used, "$4" avail ("$5")"}')"
PROBE
}

# --- Windows leg ------------------------------------------------------------
_windows_status() {
  echo "── Windows leg ──────────────────────────────────────────────"

  case "$_distro_running" in
    yes) _ok "distro '${DISTRO}': running" ;;
    no)  _warn "distro '${DISTRO}': stopped — autostart fires at next logon (start now: wsl -d ${DISTRO})" ;;
  esac

  # -NonInteractive so this never blocks; all of it is read-only.
  powershell.exe -NoProfile -NonInteractive -Command "
    \$t = Get-ScheduledTask -TaskName '$TASK' -ErrorAction SilentlyContinue
    if (-not \$t) { 'FAIL|scheduled task ''$TASK'' not registered (run: just runner-gc-install)' }
    else {
      \$i = \$t | Get-ScheduledTaskInfo
      'OK|scheduled task: ' + \$t.State
      \$lt = \$t.Principal.LogonType
      if (\$lt -eq 'S4U' -or \$lt -eq 'Password' -or \$lt -eq 'ServiceAccount') {
        'OK|principal: ' + \$lt + ' (fires while logged off)'
      } else {
        'WARN|principal: ' + \$lt + ' — only fires while that account is signed in'
      }
      if (\$i.LastRunTime.Year -lt 2000) { 'WARN|last run: never since registration' }
      elseif (\$i.LastTaskResult -eq 0)  { 'OK|last run: ' + \$i.LastRunTime + ' (result 0)' }
      else { 'FAIL|last run: ' + \$i.LastRunTime + ' (result ' + \$i.LastTaskResult + ')' }
      'INFO|next run: ' + \$i.NextRunTime
    }
    \$a = Get-ScheduledTask -TaskName '$AUTOTASK' -ErrorAction SilentlyContinue
    if (-not \$a) { 'FAIL|autostart task ''$AUTOTASK'' not registered (run: just runner-gc-install)' }
    else {
      # Judged by trigger shape, not principal: a logon task is Interactive by
      # design (the S4U warning above would be a permanent false alarm here),
      # and LastTaskResult stays 0 even when the already-running valve
      # short-circuits, so the trigger class is the only structural check
      # that means anything before the first real reboot.
      \$trig = @(\$a.Triggers | ForEach-Object { \$_.CimClass.CimClassName })
      if (\$trig -contains 'MSFT_TaskLogonTrigger') { 'OK|autostart task: logon trigger (' + \$a.State + ')' }
      else { 'FAIL|autostart task: no logon trigger — re-run: just runner-gc-install' }
      # The task blocks forever as the keepalive, so while healthy its
      # LastTaskResult is 0x41301 (SCHED_S_TASK_RUNNING = 267009), not 0.
      \$ai = \$a | Get-ScheduledTaskInfo
      if (\$ai.LastRunTime.Year -ge 2000 -and \$ai.LastTaskResult -ne 0 -and \$ai.LastTaskResult -ne 267009) {
        'FAIL|autostart last run: ' + \$ai.LastRunTime + ' (result ' + \$ai.LastTaskResult + ')'
      }
    }
    \$roots = @(\"\$env:USERPROFILE\actions-runner-win\", \"\$env:USERPROFILE\actions-runner\", 'C:\actions-runner') |
      Where-Object { Test-Path (Join-Path \$_ 'config.cmd') }
    if (-not \$roots) { 'INFO|no native Windows runner installed' }
    foreach (\$r in \$roots) {
      # Service state first: a Stopped or Disabled service is the silent
      # killer found live (2026-08-20) — GitHub shows the runner offline and
      # nothing on the host says so.
      # Judged on EFFECT, not mechanism: this host deliberately toggles
      # between service mode and interactive run.cmd mode, so a bare
      # service-Stopped alarm would stand permanently. FAIL only when the
      # service is not Running AND no Runner.Listener process exists.
      \$rc = Join-Path \$r '.runner'
      if (Test-Path \$rc) {
        \$cfgj = Get-Content \$rc | ConvertFrom-Json
        \$ownr = ((\$cfgj.gitHubUrl -replace '^https?://github\.com/','').TrimEnd('/')) -replace '/','-'
        \$sname = 'actions.runner.' + \$ownr + '.' + \$cfgj.agentName
        \$svc = Get-Service -Name \$sname -ErrorAction SilentlyContinue
        \$lsn = @(Get-Process -Name 'Runner.Listener' -ErrorAction SilentlyContinue)
        if (\$svc -and \$svc.Status -eq 'Running') {
          'OK|service: Running (StartType=' + \$svc.StartType + ')'
        } elseif (\$lsn.Count -gt 0) {
          # A listener outside the service is DELIBERATE when the dotfiles
          # interactive-mode logon task exists (GUI e2e boxes; see
          # runner_mode_win.ps1) - report OK, or the standing false alarm
          # trains the reader to ignore the line.
          if (Get-ScheduledTask -TaskName 'dotfiles-runner-interactive' -ErrorAction SilentlyContinue) {
            'OK|interactive mode: logon task + listener in session ' + \$lsn[0].SessionId + ' (service ' + \$(if (\$svc) { [string]\$svc.StartType } else { 'absent' }) + ')'
          } else {
            'WARN|service: ' + \$(if (\$svc) { [string]\$svc.Status } else { 'not installed' }) + ' but Runner.Listener runs outside it (run.cmd mode?) — stops at logoff'
          }
        } elseif (-not \$svc) {
          'FAIL|service ''' + \$sname + ''' not installed and no listener (run: just runner-svc-install)'
        } elseif (\$svc.StartType -eq 'Disabled') {
          'FAIL|service: ' + \$svc.Status + ' + StartType=Disabled — silently offline (run: just runner-svc-install)'
        } else {
          'FAIL|service: ' + \$svc.Status + ' (StartType=' + \$svc.StartType + ') and no listener — run: just runner-svc-install'
        }
      } else { 'WARN|no .runner config in ' + \$r + ' — runner never configured' }
      \$env_ = Join-Path \$r '.env'
      \$h = ''
      if (Test-Path \$env_) {
        \$line = Get-Content \$env_ | Where-Object { \$_ -match '^ACTIONS_RUNNER_HOOK_JOB_COMPLETED=' }
        if (\$line) { \$h = (\$line -split '=',2)[1] }
      }
      if (-not \$h) { 'FAIL|hook: not set in ' + \$env_; continue }
      elseif (\$h -match '\s') { 'FAIL|hook: has arguments, so it is not a path — the runner rejects it: ' + \$h }
      elseif (\$h -match '\.(ps1|sh|js)\$') { 'OK|hook: ' + \$h }
      else { 'FAIL|hook: missing a .sh/.ps1/.js extension — the runner rejects it: ' + \$h }
      # Only jobs newer than the hook's own configuration count; rejections from
      # before a repair are history and would train the reader to ignore this.
      \$cfg = if (Test-Path \$env_) { (Get-Item \$env_).LastWriteTime } else { [datetime]::MaxValue }
      \$since = @(Get-ChildItem (Join-Path \$r '_diag') -Filter 'Worker_*.log' -ErrorAction SilentlyContinue |
        Where-Object { \$_.LastWriteTime -gt \$cfg })
      # -SimpleMatch and anchored on \$h: a Worker log carries the job payload,
      # so the bare phrase also matches a PR body that quotes it.
      \$rej = @(\$since | Where-Object { Select-String -Path \$_.FullName -SimpleMatch -Pattern (\$h + ' is not a valid path to a script') -Quiet -ErrorAction SilentlyContinue })
      if (\$rej.Count -gt 0) { 'FAIL|hook REJECTED in ' + \$rej.Count + ' of the ' + \$since.Count + ' job(s) since it was configured' }
      elseif (\$since.Count -gt 0) { 'OK|hook: accepted in all ' + \$since.Count + ' job(s) since it was configured' }
      else { 'WARN|hook: no jobs have run since it was configured — unproven' }
    }
    \$d = Get-PSDrive C
    'INFO|disk: C: {0:N1} GB free of {1:N1} GB' -f (\$d.Free/1GB), ((\$d.Free+\$d.Used)/1GB)
  " 2>/dev/null | tr -d '\r\0' | while IFS='|' read -r _lvl _msg; do
    case "$_lvl" in
      OK) _ok "$_msg" ;;
      WARN) _warn "$_msg" ;;
      FAIL) _bad "$_msg" ;;
      *) _info "$_msg" ;;
    esac
  done
  echo
}

echo "🧹 disk-GC status"
echo
if [ "$_win" -eq 1 ]; then
  _windows_status
  _wsl_status
else
  _wsl_status
fi
echo "Collect now: just runner-gc    Install/repair: just runner-gc-install"
