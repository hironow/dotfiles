#!/usr/bin/env bash
# .claude/hooks/block-secrets.sh
# PreToolUse hook (matcher: Write|Edit|NotebookEdit). Blocks writing obvious
# credential patterns into files. Defense-in-depth only — not a substitute for
# a real secret scanner in CI.
#
#   exit 0 -> allow ; exit 2 -> BLOCK (stderr -> Claude)
set -euo pipefail

input="$(cat)"
# Write uses content; Edit uses new_string; NotebookEdit uses new_source.
content="$(printf '%s' "$input" | jq -r '.tool_input.content // .tool_input.new_string // .tool_input.new_source // empty')"
[ -z "$content" ] && exit 0

# Common high-confidence token shapes (OpenAI / Anthropic / GitHub / AWS /
# PEM / Slack / GitLab / Google API key). Deliberately minimal — see the
# enforcement playbook: the primary wall is a real secret scanner in CI.
# Slack requires a digit-led tail: real tokens are digit-led, and the
# looser class blocked doc placeholders like xoxb-your-token-here.
# Modern provider keys carry '-'/'_' in the body (Anthropic sk-ant-, OpenAI
# sk-proj-/sk-svcacct-/sk-admin-, GitHub fine-grained github_pat_), matched by
# scoped-prefix classes — broadening the bare sk- class to allow '-' would
# false-trigger on hyphenated English prose (risk-assessment-...).
if printf '%s' "$content" | grep -Eq 'sk-(ant|proj|svcacct|admin)-[A-Za-z0-9_-]{20,}|sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{36}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|xox[baprs]-[0-9][0-9A-Za-z-]{9,}|glpat-[0-9A-Za-z_-]{20,}|AIza[0-9A-Za-z_-]{35}'; then
  echo "BLOCKED: content looks like a live secret (API key / token / private key). Do not commit secrets; use a secret manager and reference via env var." >&2
  exit 2
fi

exit 0
