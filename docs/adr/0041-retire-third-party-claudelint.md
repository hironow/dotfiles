# 0041. Retire the third-party claudelint; official-validator-only gate

**Date:** 2026-08-16
**Status:** Accepted

## Context

ADR 0029 gated the distributed Claude artifacts with two checkers: the npm
package `claude-code-lint` ("claudelint") run via pinned `bunx`, and the
official `claude plugin validate --strict` (local-only — the claude CLI was
absent on CI runners, so CI ran the claudelint half exclusively).

On 2026-08-16 the operator reviewed claudelint's provenance and withdrew
trust: npm metadata shows a **single individual maintainer (patdugan), not
Anthropic** — the bare `claude-code-lint` name sits outside the
`@anthropic-ai/` scope. The tool parses every artifact this repo
distributes (agents, settings, hooks, skills, plugin manifests) and runs on
both developer machines and CI. Version pinning and provenance attestations
mitigate tampering of a given release, but they do not change the trust
grade of the author; the operator's call is that a non-official
single-maintainer dependency does not belong in this position. ADR 0029's
own alternative (4) — re-encoding checks in-repo — was rejected then on
drift/duplication grounds; the trust decision now outweighs that cost.

Meanwhile ADR 0040's investigation established that `bunx
@anthropic-ai/claude-code@<pin>` works on a bare runner (bun runs
claude-code's postinstall because the package is on bun's default-trusted
list), which removes the original reason the official validator never ran
in CI.

## Decision

- Remove every `claude-code-lint` invocation from `just lint-claude` and
  `.github/workflows/claude-lint.yaml`.
- The **official `claude plugin validate --strict`** becomes the sole
  external validator: locally via the installed claude CLI (skipped when
  absent), in CI via **version-pinned `bunx @anthropic-ai/claude-code`** —
  a strict upgrade for CI, where the official half previously never ran.
- `scripts/check_effective_settings.py` validates the composed effective
  settings with an in-repo, stdlib-only structural validator
  (`_validate_settings`: env / permissions / hooks shapes; unknown
  top-level keys pass so the evolving upstream schema cannot rot the gate).
- `tests/unit/test_no_third_party_claudelint.py` keeps the retired tool
  from creeping back into the justfile, the workflow, or the checker.

## Consequences

- Root-level agents/, hooks, and standalone settings lose claudelint's
  extra schema depth; what remains is the official validator's coverage
  (marketplace + plugins and the files they reference), the stdlib
  effective-settings checks, and the existing unit tests
  (`test_marketplace_manifest.py`, hook/settings merge suites). Accepted:
  trusted-but-shallower beats deep-but-untrusted for this repo's threat
  model — the artifacts are distributed to every agent home.
- CI newly gates on the official validator (it never did before), pinned
  to a claude-code version; bumping that pin is manual, like every pin.
- ADR 0029's status records the partial supersede: its gate *concept*
  (lint the distributed artifacts on every PR) survives; the claudelint
  half is retired.
