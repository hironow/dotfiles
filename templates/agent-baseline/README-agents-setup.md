# Agent baseline: per-repo setup

This scaffold adds the per-repo gates that hold the agent rules no matter what
an agent decides. `just scaffold-agent-baseline <dir>` in the dotfiles repo
copies it into a repo.

The agent instructions themselves are not part of the scaffold. The dotfiles
repo writes them to every agent home with `just sync-agents`: the base
`AGENTS.md`, the Claude overlay `CLAUDE.md`, and the guides in `docs/agents/`.
The always-loaded part stays short because an agent follows only about 150-200
instructions reliably (a working heuristic, not a measured constant; the
agent's own system prompt already uses about 50). Detail lives in guides that
are read when needed, and rules that must hold every time live in hooks and CI.

## What the scaffold copies

| file | what it does |
| --- | --- |
| `justfile` | the only task runner; `just check` is the full gate |
| `.githooks/pre-commit` | runs `just check` before every commit |
| `.github/workflows/quality-gate.yaml` | runs `just check` in CI, plus a `tofu plan` drift check when `tofu/` exists; skips draft PRs |
| `.semgrep/` | project rules and their test fixtures (see `.semgrep/README.md`) |
| `.semgrepignore` | keeps `tests/` in Semgrep's scope and leaves out the rule fixtures |
| `README-agents-setup.md` | this file |

The copy overwrites files with the same names in the target repo.

## The three gates

Instructions are advice: an agent usually follows them, but it can decide a
rule does not apply. These gates do not depend on that decision:

1. **Claude Code hooks** run before and after tool calls. The dotfiles repo
   writes them to `~/.claude/settings.json` and `~/.claude/hooks/`, so they
   are not files in this repo. A hook blocks with `exit 2`; `exit 1` is a
   non-blocking error, and the action goes ahead.
2. **Git pre-commit** (`.githooks/pre-commit`) runs `just check` for every
   commit, by a human or any tool.
3. **CI** (`quality-gate.yaml`) is the merge gate.

The instructions still matter: they give the reason for each rule, which is how
an agent applies it to cases a hook does not match.

## Set up a clone once

```sh
uv add --group lint --bounds exact ruff ty  # exact per-repo pins in the group that `just fmt` / `just lint` run
just install-hooks                          # sets core.hooksPath=.githooks and makes the hooks executable
```

`uv`, and the interactive copies of `ruff` and `ty`, come from the global mise
config (dotfiles ADR 0044). The gate and CI run the lint-group pins above, so
those are the ones the lock must hold.

Claude Code hooks need no setup per repo. Check that they load with `/hooks`
inside Claude Code. Put personal experiments in `.claude/settings.local.json`
(Git ignores it).

## e2e tests

An e2e test is a Python test file whose path contains `e2e`: a directory such
as `tests/e2e/`, or a file such as `test_checkout_e2e.py`. `just e2e-tests`
lists them, `just test-e2e` runs them, and the Semgrep rule
`agentcore-testing-no-mock-in-e2e` fails on any mock or patch in them.

## Scanning for banned patterns

`AGENTS.md` and `docs/agents/*.md` name some banned patterns on purpose, as
examples. Leave them out when you scan a repo, for example with
`git grep <pattern> -- ':(exclude)**/AGENTS.md' ':(exclude)**/CLAUDE.md' ':(exclude)docs/agents/**'`,
or in a Semgrep rule with `paths: exclude: [AGENTS.md, CLAUDE.md, "docs/agents/**"]`.
The `block-prohibited-files` hook already skips these paths.

## Changing a hook

The hooks come from the dotfiles repo. Never edit `~/.claude/hooks/*` directly:
the next `just sync-agents` overwrites them. The dotfiles `docs/agent-sync.md`
says how to change and test a hook.
