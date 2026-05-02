# 0006. mise tool version pinning strategy

**Date:** 2026-05-02
**Status:** Proposed
**Blocks:** ADR 0005 (install path rationalization)

## Context

`mise.toml` is the cross-platform source of truth for the
operator's developer-tool versions:

```toml
[tools]
just = "latest"
markdownlint-cli2 = "latest"
prek = "latest"
uv = "latest"
vp = "latest"
```

Three consumers read this file:

1. **Mac host** — operator manually runs `mise install` after
   updating `mise.toml`. "latest" resolves online to whatever the
   tool's registry says is current. mise.lock is **not** committed.
2. **Dev container build (CI)** — the local `dotfiles-tools`
   feature pre-bakes the same tools at specific pinned versions
   (`UV_VERSION="0.11.8"`, `JUST_VERSION="1.40.0"`, etc.) hardcoded
   in `.devcontainer/features/dotfiles-tools/install.sh`. The
   feature also writes a temporary `mise.toml` at
   `/tmp/mise-prebuild/mise.toml` with the same pinned versions,
   runs `mise install` against THAT file, and discards it. The
   production `mise.toml` (which says "latest") is never consulted
   during build.
3. **Coder workspace runtime** — the agent startup script runs
   `mise install` against the workspace's bind-mounted
   `/root/dotfiles/mise.toml`, with `MISE_OFFLINE=0` forced so
   "latest" can resolve. Newer-than-image versions are downloaded
   live and override the baked-in cache for that workspace
   lifetime.

This split has known problems:

- **Image / runtime drift.** Two workspace creations the same
  hour can resolve `just = "latest"` to different versions if
  upstream pushes a release between them. Reproducibility breaks
  silently.
- **Two SoT in two places.** `.devcontainer/features/dotfiles-tools/install.sh`
  hardcodes versions; `mise.toml` says "latest". The feature
  versions are the **actually-installed** ones at build time but
  are invisible to anyone reading the production `mise.toml`.
- **Trust-boundary leak (per ADR 0005 Open Question 7).** "latest"
  resolution at runtime is a per-workspace network call to
  api.github.com. Even with `GITHUB_TOKEN` propagated, this
  expands the runtime trust surface beyond what build-time
  attestation has covered.
- **codex review of ADR 0005** flagged this as a blocker for the
  install-path rationalization: "γを採る前に pin戦略 を先に決め
  ないと不安定化"。

## Decision

(Pending — three strategies considered.)

### Strategy A — Pin in mise.toml directly (boring, reproducible)

```toml
[tools]
just = "1.40.0"
markdownlint-cli2 = "0.22.1"
prek = "0.3.11"
uv = "0.11.8"
vp = "0.1.20"
```

- The dev container feature drops its hardcoded version block;
  it just runs `mise install` against the workspace mise.toml at
  build time. Single SoT.
- Updates are explicit PRs that touch mise.toml.
- mise's own self-update behaviour (e.g. `mise upgrade`) is the
  operator's tool for picking the next pin.
- Pros: simplest to reason about; one number per tool; CI and
  workspace agree.
- Cons: every update requires a manual PR; loses mise's
  "fetch latest" convenience on the Mac host.

### Strategy B — Commit mise.lock (mise's official pin format)

Keep `mise.toml` with `"latest"`. Run `mise install` once, then
commit the resulting `mise.lock` file. mise reads the lock
deterministically across machines.

```toml
# mise.toml
[tools]
just = "latest"
# ...

# mise.lock (committed)
[tools.just]
version = "1.40.0"
backend = "aqua"
```

- Updates: `mise upgrade` then commit the new mise.lock.
- The dev container feature reads the same mise.toml + mise.lock
  pair as the Mac host. Single SoT.
- Pros: matches mise's own design; allows `latest` semantics in
  the toml while still being deterministic at install time.
- Cons: requires un-gitignoring mise.lock (currently ignored
  per existing convention); mise.lock is a binary-ish format that
  generates large diffs on update.

### Strategy C — Status quo + image-tag pin only (ad-hoc)

Keep "latest" in mise.toml. Keep the feature install.sh
hardcoded versions. Rely on the prebuilt image tag (`:main` or
`:<git-sha>` per ADR 0002) for "this workspace's tool versions
are whatever the build that produced this image saw."
Reproducibility comes from pinning the **image** rather than the
**tools inside it**.

- Pros: zero operator change; image-tag pin is already the unit
  of rollback for Coder template.
- Cons: workspace runtime `mise install` still drifts (downloads
  newer-than-image versions if "latest" advanced). Two SoT
  remains. Poor surface for reasoning about supply chain.

## Open questions

1. **mise.lock format stability.** Has mise.lock's schema
   stabilised in 2025/2026 to the point we'd commit it? If lock
   format breaks across mise versions, Strategy B causes pain.
2. **Mac operator UX.** The current Mac flow is `mise install`
   pulls fresh latest. Under Strategy A, the Mac operator would
   get pinned versions and have to opt in to upgrades. Acceptable
   trade-off?
3. **`MISE_OFFLINE` in workspace runtime.** With Strategy A or
   B, can we re-enable `MISE_OFFLINE=1` at runtime (no network
   needed because all versions are pinned)? That would close the
   trust-surface drift identified by codex review 3.
4. **Pinning npm-backed tools** (vp, markdownlint-cli2). mise's
   npm backend currently fails in the workspace because of the
   `/home/hironow:/root` overlay mask (ADR 0005 Open Q5). Strategy
   A or B do not fix this, but make it more visible — a pinned
   "vp = 0.1.20" that mise can't actually install at runtime
   should error rather than warn.

## Recommendation

**Strategy A** (pin in mise.toml directly). It is the simplest
change, gives a single SoT, and aligns with the existing pattern
of explicit version constants elsewhere in this repo
(`UV_VERSION="0.11.8"` in the local feature, action `@<sha> # vX.Y`
pins in workflows, hardcoded SHA in sheldon install).

If the operator strongly prefers `latest` semantics on the Mac
host, Strategy B is a viable alternative — but it introduces
mise.lock as a new file in the repo and needs a one-time
discussion about the gitignore policy.

After this ADR is accepted, ADR 0005 can pick Strategy γ + run
`mise install` at build time with deterministic versions, and
re-enable `MISE_OFFLINE=1` at runtime.

## Consequences (Strategy A, recommended)

### Positive

- **One SoT** for tool versions: mise.toml.
- **Deterministic.** Identical results at build, on Mac, in CI.
- **Re-enables `MISE_OFFLINE=1`** at workspace runtime, narrowing
  the trust surface.

### Negative

- **Manual upgrade cadence.** Operator runs `mise upgrade` and
  commits the diff to bump versions, instead of mise pulling
  fresh on each install.
- **One-time data migration.** The feature install.sh drops the
  hardcoded `UV_VERSION` / `JUST_VERSION` etc. blocks; they move
  into mise.toml. Three places that hardcode versions today
  become one.

### Neutral

- **Tool churn frequency** is low for this set (just / uv / sheldon
  rotate maybe quarterly). Pinning does not block urgent
  upgrades; it just requires a PR.
