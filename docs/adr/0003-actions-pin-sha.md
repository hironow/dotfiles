# 0003. Pin GitHub Actions to commit SHAs and add Dependabot updates

**Date:** 2026-05-02
**Status:** Accepted (recorded retroactively for PR #48)

## Context

The `hironow` GitHub organisation flipped its **Actions permissions
policy** to require:

1. Allow only verified Marketplace creators OR explicit allowlist.
2. Pin every `uses:` reference to a **full-length commit SHA** (40
   chars). Tag and branch references are blocked.

Before PR #48, the workflows in this repo used moving tag refs
(`@v6`, `@v3`). Even Microsoft- and Docker-published actions get
their tags moved across releases, so a tag-based pin trusts the
publisher to never re-tag a compromised commit. The
`tj-actions/changed-files` incident (March 2025) demonstrated the
real cost of trusting moving refs.

The repo also had no automated mechanism to keep pinned SHAs
fresh, so a manual one-off SHA-pin would rot the moment a security
patch landed upstream.

## Decision

1. **Pin every `uses:` reference to a full-length commit SHA**, with
   a trailing `# vX.Y.Z` comment for human readability:

   ```yaml
   - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
   - uses: docker/setup-buildx-action@4d04d5d9486b7bd6fa91e7baf45bbb4f8b9deedd # v4.0.0
   ```

2. **Allowlist the one non-verified action used in this repo** in
   the org Actions permissions UI:

   ```
   jdx/mise-action@*
   ```

   (devcontainers/ci was added in PR #54 — same allowlist pattern
   applies and is documented in ADR 0002.)

3. **Add `.github/dependabot.yaml`** with three ecosystems on a
   weekly cadence:

   - `github-actions` /                     — rotates pinned SHAs
   - `uv`             /tools/rttm           — Python deps in the rttm tool
   - `docker`         /tests/docker         — sandbox / install / exe Dockerfiles

   Each ecosystem uses Conventional Commits prefixes (`chore(actions)`,
   `chore(rttm)`, `chore(docker)`) so commits land cleanly through
   the prek `conventional-commits` hook.

4. **Bump rttm CVE-affected dependencies** (pytest 9.0.1 → 9.0.3
   GHSA-6w46-j5rx-g56g, Pygments 2.19.2 → 2.20.0
   GHSA-5239-wwwm-4pmq) in the same PR so a clean `main` lands
   without open Dependabot alerts.

## Consequences

### Positive

- **Supply chain hardening.** Even a compromised tag cannot
  swap the SHA we resolve to. Renovate/Dependabot bumps the SHA +
  tag-comment together so re-tagging is visible in PR diffs.
- **Org policy compliance.** Workflows pass the pinned-SHA check
  rather than failing with `startup_failure`.
- **Dependabot continues the maintenance.** Manual SHA bumps would
  rot; the weekly Monday 09:00 JST cadence keeps the pins fresh
  without the operator remembering.
- **Conventional Commits compliance.** Per-ecosystem prefix passes
  the prek pre-commit hook; PRs land without `fix: deps` style
  noise.

### Negative

- **One non-verified Marketplace dependency** (`jdx/mise-action`)
  needs a manual UI step to allowlist on the org. A future move to
  a verified equivalent would remove the step.
- **First-time setup adds friction.** Bumping versions now requires
  resolving commit SHAs (Dependabot does it automatically; manual
  bumps need `gh api repos/<owner>/<repo>/git/refs/tags/<tag>`).

### Neutral

- **rttm CVE bumps were independent of the Actions hardening** but
  bundled into PR #48 because they shared the dependency-update
  theme and let `main` close all open Dependabot alerts at once.
- **Submodules deliberately out of Dependabot scope** (`gitsubmodule`
  ecosystem). The repo's `scripts/sync_agents.py` flow handles
  vendored sources separately.
