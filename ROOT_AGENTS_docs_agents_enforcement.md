# Enforcement (hooks, pre-commit, CI)

Read this when a hook blocks an action, when you tune or add a hook, or when
you need the exact exit-code contract. AGENTS.md has the short version.

## The three layers, and why written rules are not enough

Instructions in AGENTS.md and CLAUDE.md are advisory. An agent usually follows
them, but it can decide a rule does not apply. Rules that must hold every time
are enforced by machines at three points:

1. **Claude Code hooks** run before and after tool calls, whatever the model
   decides. They are global: the dotfiles repo distributes them with
   `just sync-agents` into `~/.claude/settings.json` + `~/.claude/hooks/*.sh`,
   so they apply in every repo Claude Code touches. Other tools (Codex,
   Cursor, Copilot) do not run them.
2. **Git pre-commit** (`.githooks/pre-commit` → `just check`) is the same gate
   for humans and for any tool that runs `git commit`. Repos scaffolded from
   the agent baseline have it; turn it on once per clone with
   `just install-hooks`.
3. **CI** (`.github/workflows/quality-gate.yaml`) is the merge gate:
   `just check` plus a `tofu plan` drift check. The agent baseline provides it
   too.

Written rules still matter: they carry the *why*, and the why lets you apply a
rule to cases a hook does not match. Hooks cover the common cases; written
rules cover the long tail.

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
  The list is minimal on purpose, as an extra layer of defense. The main wall
  is a real secret scanner in CI (for example gitleaks), not this hook.
- `block-prohibited-commands.sh` (Bash): a thin wrapper around a stdlib-only
  Python guard (`block-prohibited-commands.py`, same directory). The guard
  parses the command instead of scanning it with regexes. It blocks:
  `pip`/`poetry`/`pipenv`; `npm`/`yarn`/`pnpm` and `corepack <pm>` (the direct
  `corepack pnpm`/`yarn` run form, `@version` and `--cwd` variants included);
  `make` (as command names); root deletion; force-push to main/master;
  `gcloud` mutations that cause drift (open an IaC PR instead); and
  **creating `.yml` files via Bash** (redirect targets, `touch`/`tee`
  arguments, `cp`/`mv` destinations; reading stays allowed). Node is bun-only
  (ADR 0027). The `corepack enable`/`prepare`/`use` provisioning subcommands
  stay allowed.
- `rtk-hook-claude.sh` (Bash): wraps `rtk hook claude`, the rewriter of the
  mandatory output proxy (ADR 0047). It is not a guard. It **fails open**: on
  any error it exits 0 and leaves the command unchanged, and it is the one hook
  here that may exit non-zero without blocking. It removes rtk's
  `permissionDecision: "allow"`, so rewritten commands keep the normal
  permission flow. Inside a Claude Code isolation worktree it drops rtk's
  `git` rewrite, because there the harness refuses any git command it can only
  see through a launcher. Details: docs/agents/rtk.md.
- `format-after-edit.sh` (PostToolUse Write|Edit): runs `ruff format` +
  `ruff check --fix` on the edited Python file, and `gofmt -w` on the edited Go
  file. It always works on a single file. It does not format TS/JS per edit on
  purpose: a project-wide `just fmt` on every edit adds unrelated changes to
  the diff. The gate is `just check` / CI.

## How the guard parses commands (and the long tail it accepts)

- A quoted string becomes one word. So prose that mentions a tool name (commit
  messages, echo strings, multi-line ones too) never triggers the tooling
  guards. The other side: a quoted invocation (`bash -c "npm i"`) and wrappers
  outside the known set (`mise exec -- pnpm …`) get past them. This long tail
  is accepted; written rules and review cover it.
- The known wrapper set is `env`/`sudo`/`time`/`nohup`/`command`/`xargs` plus
  **`rtk`**. For rtk, the real command is the first operand after rtk's own
  flags. Behind a run-anything subcommand
  (`rtk proxy|run|err|test|summary|smart <cmd>`) it sits one token further
  right. rtk is in the set, not the long tail, because it is mandatory and its
  hook adds it in front of commands by default. So `rtk pnpm install` is
  blocked exactly like `pnpm install` (ADR 0047).
- Heredocs are judged by who receives them. A body read by a data sink
  (`cat`, `gh`, `git`, …) is treated as prose and skipped by **all** guards
  (so PR bodies via `gh pr create --body-file -` or `$(cat <<'EOF' …)` are
  safe). A body fed to an interpreter (`bash`, `python`, `node`, …) is code
  and is scanned like the top-level command.
- The destructive and IaC guards still scan quoted text (only data-heredoc
  bodies are skipped). So a prose mention of, for example, a gcloud mutation
  inside `-m "…"` can block by mistake. Blocking too much is the safe side
  there. Put long prose in a heredoc or a file (`git commit -F`,
  `--body-file`).
- Command parsing is best effort. If a guard blocks something it should not
  (for example a prose mention the tokenizer cannot tell apart), ask the user
  to run the command themselves with the `!` prefix.

## Tuning the hooks

Hook sources live in the dotfiles repo as `ROOT_AGENTS_hooks_*.sh` (plus the
`*.py` companion for the command guard). Their unit tests are in
`tests/unit/test_agent_hooks.py`. Never edit `~/.claude/hooks/*` directly: the
next sync overwrites them. Edit the source, extend the tests, then run
`just sync-agents` (from the dotfiles repo). To test one hook on its own:

```sh
echo '{"tool_input":{"command":"npm install"}}' | bash ~/.claude/hooks/block-prohibited-commands.sh; echo "exit=$?"
echo '{"tool_input":{"file_path":"config.yml"}}' | bash ~/.claude/hooks/block-prohibited-files.sh; echo "exit=$?"
```

(`exit=2` means the guard would block; `exit=0` means it would allow.)

## Policy files name the patterns they forbid

AGENTS.md and the playbook files in this directory name prohibited patterns on
purpose, as examples. When you scan a repo for violations, exclude the policy
files themselves, for example:

```sh
git grep <pattern> -- ':(exclude)**/AGENTS.md' ':(exclude)**/CLAUDE.md'
```

Also exclude the repo's agent-playbook directory if it has one. The
`block-prohibited-files` hook already skips these paths.
