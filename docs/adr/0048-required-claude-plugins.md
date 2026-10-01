# 0048. Claude Code plugins dotfiles requires are declared and installed through the plugin CLI

**Date:** 2026-10-01
**Status:** Accepted (operator directive, 2026-10-01).

## Context

j-cc hands Codex work to the `codex:codex-rescue` subagent, and Jev's hook puts
`--model` and `--effort` in front of its prompt (docs/runbook/jev-launchers.md).
That subagent exists only when Claude Code has the Codex plugin
(`codex@openai-codex`, from GitHub `openai/codex-plugin-cc`). Nothing installed
it: one Windows host had it because the operator added it by hand, while this
Windows host and its WSL did not, so `just jev-claude-verify` stayed BLOCKED
there ("the Codex plugin (codex:codex-rescue) is not installed in Claude Code")
although the Claude workers themselves passed.

ADR 0037 deliberately keeps `enabledPlugins` and `extraKnownMarketplaces` out
of the settings fragments: the plugin CLI mutates them at runtime, and the
marketplace entries it writes embed machine-absolute paths. A fragment that
declared them would also replace, on every sync, whatever the CLI installed.

## Decision

The operator ruled the Codex plugin mandatory in every Claude home
(`~/.claude` and `~/.claude-work-a`..`d`), including the work homes, accepting
that a plugin there runs the operator's own Codex login.

1. **Declaration.** `dump/harness/claude-plugins.json` lists the required
   marketplaces, each pinned to a release tag (`owner/repo#vX.Y.Z`), and the
   required plugin ids. The tag is a Class 2 pin (dependency policy): moving it
   is a reviewed edit, so a change upstream in how `codex-rescue` takes
   `--model` / `--effort` cannot reach j-cc unannounced.
2. **Installation through the CLI.** `scripts/claude_plugins.py` runs
   `claude plugin ...` with `CLAUDE_CONFIG_DIR` set to each existing home (it
   never creates one), in that home as working directory, always with
   `--scope user`. The steps come from the CLI's own `--json` inventories,
   not from Claude Code's internal files. Marketplaces are reconciled first,
   because replacing one uninstalls its plugins; the inventory is read again
   before plugins are reconciled and again before judging. An inventory that
   cannot be read stops that home and is reported, never read as "missing".
   A second run changes nothing.
3. **Wiring.** `just deploy` runs it on every OS (best effort, with a WARN);
   `just claude-plugins-install` runs it by hand, `--check` only reports;
   `just doctor` / `just status` show the `claude-plugins` line through the
   same `--check`. A home that `just sync-agents` creates after a deploy is
   reported by doctor and filled by `just claude-plugins-install`.

ADR 0037 stands unchanged: the settings fragments still never declare the
plugin keys (a test enforces it), and the plugin CLI remains their owner. This
ADR adds the declaration that tells the CLI what must be there.

## Consequences

- A required plugin is present in every existing Claude home after a deploy,
  and doctor names any home where it is missing, disabled, at another version,
  or installed only for a project.
- Installed is not the same as working: `jev-claude-verify` still needs a
  login, quota, Jev and the hooks, and checks only the selected home.
- Moving the plugin to a new release means editing the tag and running
  `just claude-plugins-install`; the next run replaces the marketplace and
  reinstalls the plugin at that version.
