# Agent instruction set — structure & setup

This replaces the single 1,156-line `ROOT_AGENTS.md` with a **hub-and-spoke**
layout plus a **deterministic enforcement layer**. The reasoning, in one
paragraph: AI coding agents reliably follow only ~150-200 instructions before
adherence degrades (a working heuristic, not a measured constant; the agent's
own system prompt already spends ~50), and a long
instruction file dilutes every rule in it. So the always-loaded files are kept
short, the detail is loaded on demand, and anything that must hold *every time*
is moved out of prose into hooks/CI that don't depend on model judgment.

## File map

```
AGENTS.md                      # always-loaded, cross-tool base (~150 lines)
CLAUDE.md                      # @imports AGENTS.md + Claude-only overlay
justfile                       # the only task runner; `just check` is the gate
README-agents-setup.md         # this file

docs/agents/                   # spokes — read on demand (NOT preloaded)
  tdd-workflow.md
  commit-discipline.md
  python-tooling.md
  testing.md
  observability.md
  iac-drift-policy.md
  semgrep.md
  docs-discipline.md
  project-structure.md

# NOTE: Claude Code hooks are NOT files in this scaffold. The dotfiles repo
# distributes them globally (~/.claude/settings.json + ~/.claude/hooks/*.sh,
# via `just sync-agents`), so they already apply in every repo — including
# this one. See ~/.claude/docs/agents/enforcement.md.

.githooks/pre-commit           # human/git gate -> runs `just check`
.github/workflows/quality-gate.yaml  # CI gate + tofu drift check
.semgrep/                      # project-specific rules (see its README)
```

## Why two files (AGENTS.md + CLAUDE.md) and not one symlink

Codex reads only `AGENTS.md`; Claude Code reads `CLAUDE.md` and pulls in
`AGENTS.md` via the `@AGENTS.md` import at its top. The symlink pattern is for
when the two files are *identical*. Here they're not — `CLAUDE.md` adds
Claude-only behavior (codex plan-review, ASCII-legend rules, response-format
directives). The import keeps the shared base in exactly one place so the two
never drift. Cursor/Copilot read `AGENTS.md` too, so the base is shared across
every tool.

## The three enforcement layers (and why prose isn't enough)

`AGENTS.md`/`CLAUDE.md` instructions are **advisory** — the agent reads them and
*usually* complies, but can decide a rule doesn't apply. For rules that must hold
with zero exceptions, that's not good enough. So:

1. **Claude Code hooks** — fire before/after tool calls, bypassing model
   judgment. Distributed globally from the dotfiles repo via `just sync-agents`
   (`~/.claude/settings.json` + `~/.claude/hooks/*.sh`) — they are not files in
   this repo. PreToolUse hooks **block** with `exit 2` (the script's stderr is
   fed back to the agent as the reason). Critical gotcha baked into every guard:
   `exit 2` blocks, `exit 1` does **not** — `exit 1` is a non-blocking error and
   the action proceeds.
2. **Git pre-commit** (`.githooks/pre-commit` → `just check`) — same gate for
   humans and any tool that runs `git commit`.
3. **CI** (`quality-gate.yaml`) — the merge gate; runs `just check` plus a
   `tofu plan` drift check.

The prose still matters: it carries the **why**, which is how an agent
generalizes a rule to cases the hook doesn't pattern-match. Hooks guarantee the
common cases; prose covers the long tail.

## One-time setup per clone

```sh
just install-hooks      # sets core.hooksPath=.githooks and chmod +x the hooks
```

Claude Code hooks come from the global `~/.claude/settings.json` (synced from
the dotfiles repo) — nothing to enable per repo. Verify they load with `/hooks`
inside Claude Code. Personal-only experiments go in
`.claude/settings.local.json` (auto-gitignored).

## Repo-scan self-reference

`AGENTS.md` and `docs/agents/*.md` deliberately name a few prohibited patterns as
examples. Exclude them when scanning the repo:

```sh
# git grep
git grep <pattern> -- ':(exclude)**/AGENTS.md' ':(exclude)**/CLAUDE.md' ':(exclude)docs/agents/**'
```

```yaml
# semgrep rule
paths:
  exclude: [AGENTS.md, CLAUDE.md, "docs/agents/**"]
```

The `block-prohibited-files` hook already exempts these paths.

## Tuning the hooks

The command/file guards use conservative regexes. If a guard misfires (false
positive) or misses a case you care about (false negative), edit the **source**
in the dotfiles repo (`ROOT_AGENTS_hooks_*.sh`), extend
`tests/unit/test_agent_hooks.py` there, then run `just sync-agents` — never
edit `~/.claude/hooks/*.sh` directly (the next sync overwrites them). Test a
hook in isolation:

```sh
echo '{"tool_input":{"command":"npm install"}}' | bash ~/.claude/hooks/block-prohibited-commands.sh; echo "exit=$?"
echo '{"tool_input":{"file_path":"config.yml"}}' | bash ~/.claude/hooks/block-prohibited-files.sh; echo "exit=$?"
```

(`exit=2` means the guard would block; `exit=0` means it would allow.)

## What changed vs the old ROOT_AGENTS.md (nothing dropped)

Every rule from the original survives — it was relocated, not removed:

| original section                              | now lives in                          |
| --------------------------------------------- | ------------------------------------- |
| role, decision priorities, core principles    | `AGENTS.md`                           |
| GRIT requirement                               | `AGENTS.md` (rubric → grit-grill skill) |
| tooling standards (uv/bun/just/.yaml)          | `AGENTS.md` non-negotiables + hooks   |
| TDD methodology + workflow + example           | `docs/agents/tdd-workflow.md`         |
| Tidy First + commit discipline + Conv. Commits | `docs/agents/commit-discipline.md`    |
| python-tooling (ruff/mypy) + refactoring + encoding | `docs/agents/python-tooling.md`  |
| mock policy + unit/e2e/runn                    | `docs/agents/testing.md`              |
| observability (OTel/Jaeger)                    | `docs/agents/observability.md`        |
| IaC drift policy                               | `docs/agents/iac-drift-policy.md` + command hook |
| semgrep guidelines                             | `docs/agents/semgrep.md` + `.semgrep/`|
| docs / ADR / intent / handover                 | `docs/agents/docs-discipline.md`      |
| project/docker/scripts/experiments structure   | `docs/agents/project-structure.md`    |
| codex plan-review, ASCII-art, response format  | `CLAUDE.md`                           |
| "prohibited actions" list                      | split: hooks (mechanical) + `CLAUDE.md` (judgment) |

The instruction files are kept in English (as the original was) for cross-tool
and cross-model reliability; intentional Japanese (GRIT glosses, the codex review
prompt, ASCII legends) is preserved.
