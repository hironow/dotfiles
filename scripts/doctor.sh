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

echo "Doctor summary: ok=$ok warn=$warn err=$err"
if [ "$err" -gt 0 ]; then exit 1; fi
:
