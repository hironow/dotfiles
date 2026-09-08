# 0044. The Python toolchain is uv + ruff + ty; mypy and pyright are retired

**Date:** 2026-09-08
**Status:** Accepted (operator directive, 2026-09-08). Extends the "`uv` only" non-negotiable of the agent hub (`ROOT_AGENTS.md`) to the full toolchain.

## Context

The agent instruction hub already fixed the package manager (`uv`, never
pip/poetry/pipenv) and ruff was the de-facto linter and formatter, but the
type checker was left to each repo: the hub's golden path said `just lint =
ruff check + mypy`, the `python-tooling` spoke had a mypy section, the
agent-baseline scaffold ran `uv run mypy .`, and this Mac had accumulated mypy
1.19.1 (uv tool), pyright 1.1.361 (a rogue npm global under
`/opt/homebrew/lib/node_modules`, invisible to `brew list`), a stale uv-tool
ruff 0.12.11 shadowed by a Homebrew ruff 0.16.6, and a mypy VS Code extension.
Three type checkers with three configuration dialects for one policy.

Astral now ships a type checker, [ty](https://github.com/astral-sh/ty), next to
uv and ruff. It reads the same `pyproject.toml`, is distributed through the same
release channel (GitHub releases with attestations, `aqua:astral-sh/ty` in the
mise registry) and is fast enough to run on every `just lint`. It is pre-1.0
(0.0.77 is the newest release outside the 7-day quarantine at the time of this decision).

## Decision

1. **Every Python project uses exactly three tools: `uv` (packages + runner),
   `ruff` (lint + format), `ty` (types).** The hub non-negotiable becomes
   "Python = the uv + ruff + ty trio, always"; mypy, pyright, flake8, black and
   isort are named as forbidden substitutes. Spokes (`python-tooling`,
   `commit-discipline`, `semgrep`, `tdd-workflow`) and the agent-baseline
   scaffold (`just lint` = `uv run ruff check . && uv run ty check`) follow.
2. **The trio is declared in the shared mise config** (`config/mise/config.toml`)
   so it resolves on every host under the activate-only layout (ADR 0023).
   `uv` stays `latest`; `ruff` is pinned to the exact version the dotfiles gate
   runs (`uvx ruff@0.15.22` in the justfile) so a hand-run `ruff check` in a
   mise-activated shell reports what `just check` reports; `ty` is pinned
   exactly (0.0.77 at acceptance; the number lives in `config/mise/config.toml`
   and the uv projects' dev groups, kept equal by
   `tests/unit/test_ruff_ty_pins.py`) because a pre-1.0 "latest" could change
   diagnostics under a mandatory gate (ADR 0006 pinning rationale). A newer ty
   reaches the uv locks only after the 7-day quarantine, so the mise pin moves
   with them, never ahead. ruff is bumped together with the justfile pin. These global copies are for interactive use: per-repo
   gates and the Claude format-after-edit hook run `uv run [--frozen] ruff`,
   which resolves that repo's own dev-dependency pin, never the mise copy.
3. **mypy and pyright are removed from machines** (uv tool, npm global, VS Code
   extension), and so are the duplicate ruff copies (uv tool, Homebrew): mise
   is the single provider, which the host dump (`dump/macbook/Brewfile`)
   reflects. Per-repo gates pin ruff and ty as uv dev dependencies
   (`uv add --dev ruff ty`, now a step in the agent-baseline scaffold README)
   on top of the global mise copies.

## Consequences

- One vendor, one config file, one release channel for the whole Python
  toolchain; the hub's "never weaken the gates" rule now names `ruff/ty/semgrep`.
- Existing repos that still run mypy (notably hironow/skills' own `just check`)
  are out of policy until they migrate; the `skills-maintenance` spoke says so
  explicitly rather than pretending otherwise. Each migrates in its own PR.
- `.mypy_cache` ignore patterns (`.dockerignore`, `dump/gitignore-global`,
  `emulator/.semgrepignore`) are kept on purpose: checkouts that predate the
  switch still produce the directory.
- ty is pre-1.0. Diagnostics may move between releases; the pin absorbs that,
  and bumps are explicit, reviewable edits.
- ty's suppression comment is `# ty: ignore[rule]`; the spoke asks for a
  one-line justification next to any such comment, as it did for mypy.
