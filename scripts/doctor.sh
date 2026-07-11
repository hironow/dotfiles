#!/usr/bin/env bash
# Environment doctor: diagnostics and guardrails. Entrypoint: `just doctor`.
# Lives as a standalone script (not a justfile shebang body) so the recipe
# can stay a plain-bash one-liner that starts from any shell and any just
# version — a diagnostics tool must not depend on the machinery it diagnoses.
set -euo pipefail

echo '🩺 Running environment doctor...'
ok=0; warn=0; err=0
log_ok(){ printf 'OK   %s%s\n' "$1" "${2:+ - $2}"; ok=$((ok+1)); }
log_warn(){ printf 'WARN %s%s\n' "$1" "${2:+ - $2}"; warn=$((warn+1)); }
log_err(){ printf 'ERR  %s%s\n' "$1" "${2:+ - $2}"; err=$((err+1)); }
has(){ command -v "$1" >/dev/null 2>&1; }

# Core
if has bash; then log_ok 'bash' "$(bash --version | head -n1)"; else log_err 'bash' 'missing'; fi
if has git; then log_ok 'git' "$(git --version 2>/dev/null || true)"; else log_err 'git' 'missing'; fi

# Optional tools
if has docker; then
  if docker info >/dev/null 2>&1; then log_ok 'docker' 'daemon reachable'; else log_warn 'docker' 'cli present, daemon unreachable'; fi
else log_warn 'docker' 'missing'; fi
if has just; then log_ok 'just' "$(just --version 2>/dev/null || true)"; else log_warn 'just' 'missing'; fi
if has uv; then log_ok 'uv' "$(uv --version 2>/dev/null || true)"; else log_warn 'uv' 'missing'; fi
if has mise; then log_ok 'mise' "$(mise --version 2>/dev/null || true)"; else log_warn 'mise' 'missing'; fi
if has brew; then log_ok 'brew' "$(brew --version | head -n1 2>/dev/null || true)"; else log_warn 'brew' 'missing'; fi
if has gcloud; then log_ok 'gcloud' "$(gcloud --version 2>/dev/null | head -n1 || true)"; else log_warn 'gcloud' 'missing'; fi
if has pnpm; then log_ok 'pnpm' "$(pnpm --version 2>/dev/null || true)"; else log_warn 'pnpm' 'missing'; fi
if has npm; then log_ok 'npm' "$(npm --version 2>/dev/null || true)"; else log_warn 'npm' 'missing'; fi
if has rustc; then log_ok 'rustc' "$(rustc --version 2>/dev/null || true)"; else log_warn 'rustc' 'missing'; fi

# PATH duplicates (capture exit without aborting the script)
set +e
dup_out=$(just validate-path-duplicates 2>&1)
rc=$?
# the nested `just` prints its own "error: recipe ... failed" on the
# by-design exit 2; drop it so doctor shows a clean WARN, not a fake error
dup_out=$(printf '%s\n' "$dup_out" | grep -v '^error: recipe .* failed with exit code')
set -e
case $rc in
  0) log_ok 'PATH' 'no duplicate command names';;
  2) log_warn 'PATH' 'duplicate command names found'; echo "$dup_out";;
  *) log_warn 'PATH' 'validation error'; echo "$dup_out";;
esac

# Windows PATH contamination (WSL /mnt leak; no-op on non-WSL hosts)
set +e
win_out=$(just validate-path-windows 2>&1)
rc=$?
win_out=$(printf '%s\n' "$win_out" | grep -v '^error: recipe .* failed with exit code')
set -e
case $rc in
  0) log_ok 'PATH-windows' 'no /mnt Windows leakage';;
  2) log_warn 'PATH-windows' 'Windows dirs leaking into PATH'; echo "$win_out";;
  *) log_warn 'PATH-windows' 'validation error'; echo "$win_out";;
esac

# Rogue npm-global AI CLIs shadowing the mise-managed versions (cross-platform).
# A stray `npm install -g` — codex's built-in `codex update` above all —
# installs into the active node's global and wins PATH over the mise npm
# backend, per node version. scripts/rogue_npm_globals.sh scans every node
# install; a non-zero exit means it could not resolve the installs dir (warn,
# do not claim clean).
set +e
rogue_out=$(bash scripts/rogue_npm_globals.sh detect 2>/dev/null)
rc=$?
set -e
if [ "$rc" -ne 0 ]; then
  log_warn 'npm-rogue' 'could not scan node installs (mise where node failed)'
elif [ -z "$rogue_out" ]; then
  log_ok 'npm-rogue' 'no rogue npm-global AI CLIs shadowing mise'
else
  n=$(printf '%s\n' "$rogue_out" | grep -c .)
  log_warn 'npm-rogue' "${n} rogue npm-global AI CLI install(s) shadow mise -- run: just prune-rogue-npm-globals"
  printf '%s\n' "$rogue_out" | sed 's/^/    /'
fi

# Native Windows (MSYS/MINGW) environment assurance. Encodes the known
# fresh-Windows-host gotchas so the doctor teaches the fix instead of each
# recipe failing cryptically. WARN, not ERR: Git Bash workflows keep working
# without these, and self-check expects doctor to exit 0.
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    # 1) just needs cygpath to run shebang recipes, and PowerShell sessions
    #    only see the persisted (registry) PATH — which a stock
    #    Git-for-Windows install leaves without Git\usr\bin. The in-process
    #    PATH is useless as a signal (Git Bash always self-prepends
    #    /usr/bin), so read the registry via powershell.exe.
    win_usr_bin="$(cygpath -w /usr/bin)"
    persisted_path="$(powershell.exe -NoProfile -Command \
      "[Environment]::GetEnvironmentVariable('Path','User') + ';' + [Environment]::GetEnvironmentVariable('Path','Machine')" \
      | tr -d '\r')"
    # containment check in pure bash: MSYS grep -i can abort (core dump) on
    # registry PATH strings with non-UTF8 (cp932) bytes
    if [[ "${persisted_path,,}" == *"${win_usr_bin,,}"* ]]; then
      log_ok 'win-cygpath' "persisted PATH reaches ${win_usr_bin}"
    else
      log_warn 'win-cygpath' 'just shebang recipes fail from PowerShell (cygpath not on persisted PATH)'
      echo '    Fix (run in PowerShell, then open a new session):'
      echo "    [Environment]::SetEnvironmentVariable('Path', ([Environment]::GetEnvironmentVariable('Path','User').TrimEnd(';') + ';${win_usr_bin}'), 'User')"
    fi

    # 2) deploy-managed state: PowerShell profile blocks + global mise
    #    config. Stale mise config is the nastiest drift (an ungated
    #    sheldon aborts every `mise exec` recipe), so surface it early.
    ps_profile="$HOME/Documents/PowerShell/Microsoft.PowerShell_profile.ps1"
    stale=''
    for marker in 'starship init' 'mise activate' 'mise node corepack'; do
      grep -qF "dotfiles managed block: ${marker}" "$ps_profile" 2>/dev/null \
        || stale="${stale}${stale:+, }profile:${marker##* }"
    done
    cmp -s config/mise/config.toml "$HOME/.config/mise/config.toml" 2>/dev/null \
      || stale="${stale}${stale:+, }mise-config"
    if [ -z "$stale" ]; then
      log_ok 'win-deploy' 'PowerShell profile blocks + mise config in sync'
    else
      log_warn 'win-deploy' "stale/missing: ${stale} -- run: just deploy"
    fi

    # 3) uv hardening: native Windows uv reads %APPDATA%\uv\uv.toml (not
    #    ~/.config/uv/uv.toml). Without it the 7-day quarantine is off and
    #    any `uv run` rewrites committed uv.locks (blocks commits via the
    #    pre-commit `just lint`).
    if [ -n "${APPDATA:-}" ] && [ -f "$(cygpath -u "$APPDATA")/uv/uv.toml" ]; then
      log_ok 'win-uv-hardening' 'APPDATA uv/uv.toml present (quarantine active)'
    else
      log_warn 'win-uv-hardening' 'APPDATA uv/uv.toml missing (uv quarantine off; uv.lock churn) -- run: just harden-env'
    fi

    # 4) Unix CLIs the hooks and `just check` shell out to (scoop-provided
    #    on Windows; absence fails as cryptic 'command not found's).
    if has jq && has shellcheck; then
      log_ok 'win-clis' 'jq + shellcheck present'
    else
      log_warn 'win-clis' 'missing jq and/or shellcheck -- run: scoop install jq shellcheck'
    fi
    ;;
esac

echo "Doctor summary: ok=$ok warn=$warn err=$err"
if [ "$err" -gt 0 ]; then exit 1; fi
:
