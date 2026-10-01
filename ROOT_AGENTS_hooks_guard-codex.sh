#!/usr/bin/env bash
# Codex PreToolUse adapter for the shared exit-2 guards: guard-codex.sh <guard>.
# Codex runs a hook through the session's shell (codex-rs core/src/session/
# mod.rs build_hooks_config). On Windows that is `pwsh -Command`, which reports
# every non-zero exit as 1, so a guard's exit 2 arrived as a failed hook, and a
# failed hook fails open. A deny decision on stdout survives any shell: this
# turns the guard's exit 2 + stderr into one and passes other exits through.
# The guards keep Claude's exit-code contract and know nothing of Codex.

case "${BASH_SOURCE[0]}" in
  */*) dir="${BASH_SOURCE[0]%/*}" ;;
  *) dir=. ;;
esac

# stdin and stdout go to the guard as they are; only its stderr is captured
{ reason="$("${BASH:-bash}" "$dir/$1" 2>&1 1>&3 3>&-)"; status=$?; } 3>&1

if [ "$status" -ne 2 ]; then
  [ -n "$reason" ] && printf '%s\n' "$reason" >&2
  exit "$status"
fi

# One JSON string: whitespace controls become spaces, other controls go, and
# backslashes and quotes are escaped.
reason="$(printf '%s' "${reason:-blocked by $1}" | tr '\t\r\n' '   ' | tr -d '\000-\037' |
  sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' -e 's/ *$//')"
printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$reason"
