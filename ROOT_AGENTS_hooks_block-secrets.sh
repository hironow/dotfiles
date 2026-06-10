#!/usr/bin/env bash
# .claude/hooks/block-secrets.sh
# PreToolUse hook (matcher: Write|Edit). Blocks writing obvious credential
# patterns into files. Defense-in-depth only — not a substitute for a real
# secret scanner in CI.
#
#   exit 0 -> allow ; exit 2 -> BLOCK (stderr -> Claude)
set -euo pipefail

input="$(cat)"
# Edit uses new_string; Write uses content.
content="$(printf '%s' "$input" | jq -r '.tool_input.content // .tool_input.new_string // empty')"
[ -z "$content" ] && exit 0

# Common high-confidence token shapes.
if printf '%s' "$content" | grep -Eq 'sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{36}|AKIA[A-Z0-9]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----'; then
  echo "BLOCKED: content looks like a live secret (API key / token / private key). Do not commit secrets; use a secret manager and reference via env var." >&2
  exit 2
fi

exit 0
