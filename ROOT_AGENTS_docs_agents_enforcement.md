# Enforcement (hooks, pre-commit, CI)

Read this when a hook blocks an action, when tuning or adding a hook, or when
you need the exact exit-code contract. Root summary is in AGENTS.md.

## The three layers (and why prose isn't enough)

AGENTS.md / CLAUDE.md instructions are advisory — an agent usually complies but
can decide a rule doesn't apply. Rules that must hold every time are enforced
mechanically, at three points:

1. **Claude Code hooks** — fire before/after tool calls, independent of model
   judgment. They are global: the dotfiles repo distributes them via
   `just sync-agents` into `~/.claude/settings.json` + `~/.claude/hooks/*.sh`,
   so they apply in every repo Claude Code touches. Other tools (Codex, Cursor,
   Copilot) do not run them.
2. **Git pre-commit** (`.githooks/pre-commit` → `just check`) — the same gate
   for humans and for any tool that runs `git commit`. Present in repos
   scaffolded from the agent baseline; enable once per clone with
   `just install-hooks`.
3. **CI** (`.github/workflows/quality-gate.yaml`) — the merge gate: `just check`
   plus a `tofu plan` drift check. Also provided by the agent baseline.

Prose still matters: it carries the *why*, which is how you generalize a rule
to cases a hook doesn't pattern-match. Hooks guarantee the common cases; prose
covers the long tail.

## Hook exit-code contract (PreToolUse)

- `exit 0` → allow.
- `exit 2` → **block**; the script's stderr is fed back to the agent as the
  reason. Read it and change approach — never route around a block.
- `exit 1` → non-blocking error; the action **proceeds**. Never use it to block.

## What each hook covers

- `block-prohibited-files.sh` (Write|Edit): `.yml` filenames and deprecated
  Compose v1 names (`docker-compose.y{a,}ml`).
- `block-secrets.sh` (Write|Edit): obvious secrets in file writes.
- `block-prohibited-commands.sh` (Bash): thin wrapper around a stdlib-only
  Python guard (`block-prohibited-commands.py`, same directory) that parses
  the command instead of regex-scanning it. Blocks: `pip`/`poetry`/`pipenv`,
  `npm`/`yarn`, `make` (as command names), root deletion, force-push to
  main/master, drift-causing `gcloud`/`cdr` mutations (open an IaC PR
  instead), and **creating `.yml` files via Bash** (redirect targets,
  `touch`/`tee` args, `cp`/`mv` destinations — reads stay allowed). `pnpm` is
  allowed only when a `pnpm-lock.yaml` governs each pnpm invocation's target
  directory (searched upward; `cd`/`-C`/`--dir` targets resolved, quoted
  paths handled).
- `format-after-edit.sh` (PostToolUse Write|Edit): `ruff format` +
  `ruff check --fix` on edited Python files.

## Parsing semantics (and accepted long tail)

- Quoted strings tokenize into single words, so prose mentions of tool names
  (commit messages, echo strings, multi-line included) never false-trigger
  the tooling guards. Flip side: a quoted invocation (`bash -c "npm i"`) and
  wrapper forms outside the known set (`mise exec -- pnpm …`) slip them —
  accepted long tail; prose rules + review cover it.
- Heredocs are receiver-aware: a body consumed by a data sink (`cat`, `gh`,
  `git`, …) is opaque prose and excluded from **all** guards (so PR bodies
  via `gh pr create --body-file -` or `$(cat <<'EOF' …)` are safe); a body
  fed to an interpreter (`bash`, `python`, `node`, …) is executable code and
  is scanned like the top-level command.
- Destructive/IaC guards still scan quoted text (only data-heredoc bodies are
  excluded): a prose mention of e.g. a gcloud mutation inside `-m "…"` can
  false-block. Over-blocking is the safe side there; put long prose in a
  heredoc or a file (`git commit -F`, `--body-file`).
- An unresolvable pnpm target (variable, subshell) fails safe (block); the
  block message offers the `!` escape hatch for legitimate cross-repo calls.
- Command parsing is best-effort. A pnpm target directory hidden behind a
  variable or subshell can't be resolved; the hook fails safe and blocks. If a
  block is a false positive, ask the user to run the command themselves with
  the `!` prefix.

## Tuning the hooks

Hook sources live in the dotfiles repo as `ROOT_AGENTS_hooks_*.sh` (plus the
`*.py` companion for the command guard), with unit tests in
`tests/unit/test_agent_hooks.py`. Never edit `~/.claude/hooks/*` directly —
the next sync overwrites them. Edit the source, extend the tests, then run
`just sync-agents` (from the dotfiles repo). Test a hook in isolation:

```sh
echo '{"tool_input":{"command":"npm install"}}' | bash ~/.claude/hooks/block-prohibited-commands.sh; echo "exit=$?"
echo '{"tool_input":{"file_path":"config.yml"}}' | bash ~/.claude/hooks/block-prohibited-files.sh; echo "exit=$?"
```

(`exit=2` means the guard would block; `exit=0` means it would allow.)

## Repo-scan self-reference

AGENTS.md and the playbook files in this directory intentionally name
prohibited patterns as examples. When scanning a repo for violations, exclude
the policy files themselves — e.g.:

```sh
git grep <pattern> -- ':(exclude)**/AGENTS.md' ':(exclude)**/CLAUDE.md'
```

Also exclude the repo's agent-playbook directory if it carries one. The
`block-prohibited-files` hook already exempts these paths.
