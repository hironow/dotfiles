# 0031. Disable mise `node.corepack` on Windows (`just deploy` `$PROFILE` carve-out)

**Date:** 2026-07-04
**Status:** Accepted

## Context

The global mise config (`config/mise/config.toml`, copied to
`~/.config/mise/config.toml` by `just deploy`) sets:

```toml
[settings.node]
corepack = true
```

This makes mise run corepack setup during **every** node install. On a Windows
host with a system Node in `C:\Program Files\nodejs`, that step throws:

```
EPERM: operation not permitted, open 'C:\Program Files\nodejs\pnpx.CMD'
```

Because `mise exec` installs any declared-but-missing required tool *before*
running the requested command, an uninstallable repo-pinned node (`mise.toml`
pins an exact version) blocks **every** mise-wrapped `just` recipe:
`fmt`/`lint`/`check` (the markdownlint + vp steps), `install-hooks`,
`pre-commit`, `test-iac`, `instruction-budget`, `sync-agents*`, `pdoc`.

Verified on a live Windows 11 host (2026-07-04): `MISE_NODE_COREPACK=0 mise
install node@<pin>` succeeds cleanly, and with the setting active every
`mise exec` aborts at the corepack step.

mise `[settings]` cannot be OS-gated the way `[tools]` entries can
(`os = ["linux","macos"]`, as this same config does for sheldon). The override
must therefore be an environment variable applied on Windows only.

## Decision

**`just deploy`'s Windows branch exports `MISE_NODE_COREPACK=0` into PowerShell
7's `$PROFILE`, in a dedicated managed block; `just clean` removes it
symmetrically.**

```powershell
# >>> dotfiles managed block: mise node corepack >>>
$env:MISE_NODE_COREPACK = "0"
# <<< end dotfiles managed block <<<
```

Decisions that matter:

- **Its own managed block (fresh marker), not folded into the ADR 0024
  mise-activate block.** deploy's block writer is *skip-if-marker-present*
  (idempotency via `grep -qF`). Adding the line inside the existing mise block
  would never reach hosts that already carry that block — i.e. exactly the
  broken Windows hosts. A new marker is absent on every existing `$PROFILE`, so
  it is appended on the next `just deploy`. `clean` removes it with the same
  `sed` range-deletion pattern as ADR 0022/0024.
- **Windows only.** Mac/Linux keep `corepack = true`; the env var is written
  solely on the `MINGW*|MSYS*|CYGWIN*` branch.
- **Node is bun-only on Windows (ADR 0027)**, so corepack is never needed there;
  disabling mise's auto-corepack is side-effect-free.
- **Static-parse tests** (`tests/test_justfile_windows_subset.py`) guard both the
  deploy block and the clean removal, matching the ADR 0018/0022/0024 test
  pattern (the Linux sandbox cannot exercise a `uname`=MINGW branch).

## Relationship to prior ADRs (refinement, not reversal)

This ADR **refines**, and does not contradict, the corepack decisions:

- **ADR 0017** (corepack machine-supply) and **ADR 0027** (bun-only agent
  policy) are unchanged. corepack remains installed and provisionable.
- **ADR 0018** implements `install.sh`'s `step_corepack` as an *explicit*
  `corepack enable` on Windows (routed through `mise exec --`). That is a
  **different trigger** from the one addressed here: this ADR disables mise's
  *automatic* corepack run *during node install*, not the explicit
  `corepack enable`. The two coexist — corepack stays provisionable; only mise's
  unprompted auto-invocation (which EPERMs before node is even usable) is
  suppressed.

Open item (not blocking): ADR 0018's premise that routing `corepack enable`
through `mise exec --` avoids the Program Files EPERM is **unverified on the
current Windows host** — the auto-corepack path EPERMs regardless. If a future
task confirms explicit `corepack enable` also EPERMs under `mise exec`, that is
a matter for revisiting ADR 0018, out of scope here.

## Consequences

- Every mise-wrapped `just` recipe becomes runnable on Windows after a
  `just deploy` (and once node is installed with corepack off). A separate
  prerequisite (B1) is that the deployed `~/.config/mise/config.toml` carry the
  sheldon OS-gate; that is a deploy-freshness concern, not this decision.
- A third managed block now lives in the Windows `$PROFILE`; `deploy`/`clean`
  stay symmetric across three blocks: starship (0022), mise-activate (0024),
  mise-corepack (this ADR).
