# 0033. Windows `just deploy` installs the global mise toolset

**Date:** 2026-07-05
**Status:** Accepted

## Context

ADR 0018's Windows deploy subset was "starship + gitignore only"; ADR 0024 added
the mise-activate `$PROFILE` block so mise-pinned tools win PATH. But the deploy
Windows branch only *copies* `config/mise/config.toml` → `~/.config/mise/
config.toml`; the `mise -C / install` that actually installs the global toolset
lives only in the Unix path, **after** the Windows branch's `exit 0`. So on
Windows the global tools (starship, fzf, eza, portless, the global AI CLIs, …)
are declared but never installed — the ADR 0024 mise-activate block points at
tools that aren't there.

Verified on a live host: native Windows mise *does* read `~/.config/mise/
config.toml` (`mise config ls`), so installing from it works, and node installs
cleanly when corepack is disabled.

## Decision

The deploy Windows branch runs `MISE_NODE_COREPACK=0 mise -C / install` (guarded
by `command -v mise`, best-effort with a loud WARN on failure) after copying the
global config, before "Deploy complete":

- **`-C /`** scopes to the global config only (a HOME-level `~/mise.toml` must
  not widen the set), mirroring the Unix path.
- **`MISE_NODE_COREPACK=0`** avoids the Program-Files-node corepack EPERM (ADR
  0028) during the node install — set inline so it is self-contained and does
  not depend on ADR 0031's separate `$PROFILE` env block. Verified: node 24.18.0
  installed cleanly under it.
- **Best-effort (`|| WARN`)**: a fresh host may need network or `mise trust`; the
  WARN is actionable ("re-run … may need mise trust") rather than a silent
  swallow.

## Relationship to prior ADRs

- **Extends** the ADR 0018 / 0024 Windows deploy subset (now: starship +
  gitignore + mise config + two `$PROFILE` blocks + global mise install).
- **Depends on** ADR 0031's corepack finding (uses `MISE_NODE_COREPACK=0`
  inline).
- **Git aliases `[include]` managed block.** deploy also appends an `[include]`
  for **only** `aliases.gitconfig` (pure `[alias]` entries) to `~/.gitconfig`;
  `clean` removes it (same marker-block pattern as the `$PROFILE` blocks).
  `shared.gitconfig` is deliberately **not** re-included: on a host with a manual
  PC-local `gpgsign` override (e.g. `gpgsign=false` on a keyless machine),
  appending a shared include after the override would re-enable signing. So
  identity / signing / shared config stay manual per **ADR 0021**; only aliases
  — which override nothing — are auto-wired. This fills the observed gap (a
  manual `~/.gitconfig` that included shared but forgot aliases).

## Consequences

- `just deploy` on Windows now installs starship/fzf/eza/portless/etc, so the
  ADR 0024 mise-activate block resolves real tools.
- First deploy is slower (installs the toolset); idempotent thereafter.
