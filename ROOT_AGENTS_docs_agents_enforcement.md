# Enforcement (hooks, pre-commit, CI)

Read this when a hook blocks an action, when you tune or add a hook, or when
you need the exact exit-code contract. AGENTS.md has the short version.

## The three layers, and why written rules are not enough

Instructions in AGENTS.md and CLAUDE.md are advisory. Rules that must hold
every time are enforced at three points:

1. **Claude Code and Codex hooks** run before and after tool calls. The
   dotfiles repo distributes them with `just sync-agents`.
2. **Git pre-commit** (`.githooks/pre-commit` → `just check`) is the gate for
   humans and any tool that runs `git commit` (`just install-hooks` per clone).
3. **CI** (`.github/workflows/quality-gate.yaml`) is the merge gate:
   `just check` plus a `tofu plan` drift check.

Hooks cover the common cases; written rules carry the *why* and cover the long
tail.

## Hook exit-code contract (PreToolUse)

- `exit 0` → allow.
- `exit 2` → **block**. The agent receives the script's stderr as the reason.
  Read it and change your approach. Never route around a block.
- `exit 1` → non-blocking error; the action **goes ahead**. Never use it to
  block.

## What each hook covers

- `block-prohibited-files.sh` (Write|Edit): `.yml` filenames and deprecated
  Compose v1 names (`docker-compose.y{a,}ml`).
- `block-secrets.sh` (Write|Edit): obvious secrets in file writes
  (OpenAI/GitHub/AWS/Slack/GitLab/Google-API-key shapes + PEM headers).
- `block-prohibited-commands.sh` (Bash): wraps `block-prohibited-commands.py`
  (same directory; parser pipeline documented in its module docstring). Blocks:
  `pip`/`poetry`/`pipenv`; `npm`/`yarn`/`pnpm` and `corepack <pm>` (provisioning
  `corepack enable`/`prepare`/`use` stays allowed); `make`; root deletion;
  force-push to main/master; `gcloud` mutations that cause drift; and creating
  `.yml` files via Bash (redirects, `touch`/`tee`, `cp`/`mv` destinations). It
  also unwraps `rtk` (including `rtk proxy|run|err|test|summary|smart <cmd>`) so
  `rtk pnpm install` is blocked like `pnpm install`.
- `rtk-hook-claude.sh` / `rtk-hook-codex.sh` (Bash): wraps `rtk hook` for the
  mandatory output proxy (dotfiles ADR 0047). Fails open (`exit 0` on error)
  and strips `permissionDecision` so rewritten commands keep the normal
  permission flow. Details: docs/agents/rtk.md.
- `format-after-edit.sh` (PostToolUse Write|Edit): runs `ruff format` +
  `ruff check --fix` on the edited Python file, and `gofmt -w` on the edited Go
  file (single file only).

## Avoiding false positives in Bash commands

- Destructive and IaC guards scan quoted strings too, and skip only data-sink
  heredoc bodies (`cat`, `gh`, `git`, `tee`). Put long commit or PR prose that
  mentions `gcloud` or `rm` in a heredoc or file (`git commit -F`,
  `gh pr create --body-file -`) instead of `-m "…"`.
- If a guard blocks a safe command by mistake, ask the human to run it with the
  `!` prefix. Never work around the guard.

## Hook sources and repo scans

Never edit `~/.claude/hooks/*` or `~/.codex/hooks/*` directly: the next
`just sync-agents` overwrites them. Change the sources in the dotfiles repo
(see `docs/agent-sync.md` there).

Policy files name prohibited patterns as examples. Exclude them when scanning a
repo for violations:
`git grep <pattern> -- ':(exclude)**/AGENTS.md' ':(exclude)**/CLAUDE.md'` (plus
any agent-guide directory).
