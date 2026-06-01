# 0025. Wrap mise-managed tools at every justfile call site (補強 of ADR 0023)

**Date:** 2026-06-02
**Status:** Accepted

## Context

ADR 0023 (`mise activate` only in interactive shells, drop manual
`shims` PATH entries) had a known but under-stated bypass candidate:
shell processes that do **not** source `~/.zshrc`. The enforcement
inventory captured cron / launchd / IDE-spawned `bash -c` as the
canonical examples, with the workaround "use `mise exec --` or
add shims to `~/.zshenv`".

What ADR 0023 did **not** call out clearly is that **`just` itself
spawns a non-interactive bash sub-shell for every recipe**: `set shell
:= ["bash", "-eu", "-o", "pipefail", "-c"]` at the top of the justfile
makes every recipe body run under `bash -c …`, which never sources
`.zshrc` and never picks up `mise activate`.

Two consecutive PRs after #134 / #136 exposed this gap in the field:

- **PR #140**: `just test-iac` failed with `tofu: command not found`
  because the recipe body called bare `tofu init / tofu test` from
  inside the `bash -c …` sub-shell. Fixed by `mise x -- tofu` prefix.
- **PR #141**: every other `exe-*` recipe (`exe-init`, `exe-plan`,
  `exe-apply`, `exe-replace`, `exe-down`, `exe-down-all`,
  `exe-validate`, `exe-output`) had the same fail mode. Fixed by adding
  `eval "$(mise activate bash)"` at the top of each shebang-script
  recipe body.

The same bypass existed for `uv`. Bare `uv lock`, `uv run pytest`,
`uv run ruff check / format` calls in `emu-*` recipes plus the
`sync-agents` family relied on inherited PATH coincidence:

- On a machine where `~/.cargo/bin/uv` or `~/.local/bin/uv` is in
  inherited PATH, the recipe runs against whichever stray `uv` ends up
  first in PATH — **not** the mise-pinned version.
- On a freshly-deployed machine with no stray `uv`, the bare call
  fails outright.

PR #140 also surfaced a related but distinct hazard: **brew-installed
shadows of mise-pinned tools** silently win in `bash -c` sub-shells.
On this machine `/opt/homebrew/bin/tofu` (brew, v1.12.1) was masking
the mise-pinned v1.11.5 the moment `just` was involved — same recipe,
different version, depending on whether the caller was a mise-activated
shell or a sub-shell.

## Decision

Establish a per-justfile rule:

1. **For single-command recipes** (one-line bodies or `@cmd` recipes),
   wrap the tool with `mise exec --` (or `mise x --`) at the call
   site. Concretely, introduce `UV`, `UV_RUN`, `PDOC` justfile
   variables alongside the existing `MARKDOWNLINT` variable so the
   wrap is reused without per-line duplication:

   ```just
   MARKDOWNLINT := "mise exec -- markdownlint-cli2"
   PDOC := "mise exec -- uv run pdoc"
   UV := "mise exec -- uv"
   UV_RUN := "mise exec -- uv run"
   ```

   And reference them: `{{UV_RUN}} pytest …`, `{{UV}} lock --upgrade`.

2. **For shebang-script recipes** (`#!/usr/bin/env bash` + multi-line
   body), add `eval "$(mise activate bash)"` after `set -euo pipefail`
   so the entire recipe body runs under a freshly-activated mise
   environment. Bare tool calls inside such a recipe are then
   correctly mise-pinned. This is the pattern PR #141 used for
   `exe-*`; this ADR extends it to `emu-fmt` and `emu-lint`.

3. **Side-effect cleanup**: remove brew-installed shadows that compete
   with mise pins on this machine (`brew uninstall opentofu` because
   mise pins `opentofu = "1.11.5"` while brew installed `1.12.1`).
   The Brewfile (`dump/Brewfile`) should not re-introduce them; mise
   is the SoT for these tools.

## Enforcement inventory

### Entry points

- Every justfile recipe that invokes a mise-managed tool.
- Every shell script invoked from a recipe (`.semgrep` rules, install
  hooks, etc.).
- Every PR that adds a new recipe touching `tofu`, `uv`, `node`,
  `bun`, `python`, etc.

### Persistent / carried data needed at each enforcement point

- For single-command recipes: a justfile variable (`UV`, `UV_RUN`,
  `MARKDOWNLINT`, `PDOC`) referenced via `{{NAME}}`.
- For shebang-script recipes: `eval "$(mise activate bash)"` between
  `set -euo pipefail` and the first tool call.

### Bypass candidates

- **A new recipe added without either guard** silently runs bare,
  exposing the same silent-drift / command-not-found pair.
  Detection: a tests/test_justfile_mise_wrap.py-style scanner could
  grep for bare `(tofu|uv|node|python|bun)` outside the two safe
  forms. Not added in this PR — kept as a follow-up if the pattern
  recurs.
- **A future tool added to mise but invoked directly in justfile**
  without being added to either the variable table or the activate
  preamble. Mitigation: tooling-aware reviewers; same recurrence
  argument.
- **External scripts** (`scripts/*.sh`, `exe/scripts/*.sh`) invoked
  from a recipe inherit the recipe's environment, so an activated
  recipe propagates `mise activate` to its `bash exe/scripts/x.sh`
  call. A script invoked from a non-activated recipe (or directly,
  outside `just`) does not. Today no script in this repo calls mise
  tools bare — leave the rule "explicit `mise exec --` in scripts"
  as a follow-up if such a script is added.

### Tests proving coverage

- `just --list` still lists every recipe after the changes.
- `just sync-agents-preview` (which goes through `UV_RUN` now) runs
  without `command not found` from inside `just` (= the bash
  sub-shell case).
- `bash -c "tofu --version"` resolves to mise-pinned 1.11.5 after
  `brew uninstall opentofu` (= silent-drift fix).

## Consequences

### Positive

- Every mise-managed tool in the justfile resolves to its pinned
  version regardless of the caller's shell environment.
- The variable table at the top of the justfile is now the single
  place to swap a tool's wrap policy (e.g. `mise exec --` → direct
  if mise is ever retired); shebang recipes follow the same pattern
  as the existing `exe-*` family from PR #141.
- Brew-installed shadow tools no longer mask mise pins for tools the
  repo cares about — silent version drift is eliminated, at the cost
  of one-time `brew uninstall` on each host.

### Negative

- More verbose recipe bodies for single-command cases (the diff
  trades bare `uv run X` for `{{UV_RUN}} X`).
- New contributors need to know the rule; relying on social
  convention works for a small dotfiles repo but does not generalise.
- `brew uninstall opentofu` is a per-machine action; documenting it
  in this ADR's Decision section is the only enforcement mechanism.

### Neutral

- ADR 0023's interactive-shell narrative is unchanged. This ADR
  strictly **adds** a justfile call-site rule that 0023 did not
  formalise.
