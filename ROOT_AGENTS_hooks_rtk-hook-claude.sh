#!/usr/bin/env bash
# .claude/hooks/rtk-hook-claude.sh
# PreToolUse hook (matcher: Bash) — thin wrapper. The logic lives in the
# companion Python file (stdlib-only), same split as
# block-prohibited-commands.sh. See docs/agents/rtk.md for the semantics.
#
# The companion's filename differs between the dotfiles repo root (sync source
# naming) and a deployed agent home (hooks/), so both are tried.
#
# Exit-code contract: this hook FAILS OPEN. It is an output optimiser, not a
# guard — every failure path exits 0 with no stdout, which leaves the command
# untouched. Never convert this to exit 2: a hiccup in the token filter would
# then kill every Bash call in the session. The guard that *does* fail closed
# is block-prohibited-commands.sh, and it runs independently of this one.
set -uo pipefail

command -v python3 >/dev/null 2>&1 || exit 0

dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || exit 0
for candidate in \
  "$dir/rtk-hook-claude.py" \
  "$dir/ROOT_AGENTS_hooks_rtk-hook-claude.py"; do
  if [ -f "$candidate" ]; then
    exec python3 "$candidate"
  fi
done

exit 0
