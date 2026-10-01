#!/usr/bin/env bash
# Codex PreToolUse hook (matcher: Bash): rtk's own Codex hook. Codex accepts a
# rewrite (updatedInput) only together with permissionDecision:"allow" and
# grants no approval from it (codex-rs hooks/src/engine/output_parser.rs), so
# unlike the Claude wrapper nothing is stripped: rtk's answer passes through.
# Fails open: without rtk the command runs unchanged. Not `rtk init --codex`:
# dotfiles owns this hook (ADR 0047; see docs/agents/rtk.md).
command -v rtk >/dev/null 2>&1 || exit 0
exec rtk hook codex
