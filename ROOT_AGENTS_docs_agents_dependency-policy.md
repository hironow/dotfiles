# Dependency policy

Read this when adding, bumping, or triaging a dependency (including a
Dependabot PR). Motto: **prefer the newest version and the more-secure
choice.** Staying current is a security posture — the newest release has
the fewest known CVEs and the most upstream eyes. "Newest" is safe only
when the package is battle-tested, so split every dependency into two
classes and treat them oppositely.

## Class 1 — foundational / widely-used

Language toolchains and ubiquitous libraries: **TypeScript, bun, Go, uv,
node, rust, Ruff, ty**, and a service's core framework/runtime. Huge user
bases surface and fix regressions fast, so running behind is the riskier
position.

- Adopt latest **aggressively**, including the deliberate moving-tag /
  pre-release exceptions the repo has already opted into (bun `canary`,
  Python 3.15 pre-release line, ...).
- A **stable** major that removes or renames an API is **fix-forward**
  (update the code), never pinned back.
- A **preview / RC / canary** major is opt-in and isolated — not
  auto-adopted just because Dependabot proposed it. Once a repo has opted
  in, moving *forward within that channel* (beta → RC → GA) is ordinary
  aggressive adoption; only **entering** a channel from stable is a
  per-repo maintainer call.

## Class 2 — niche / low-adoption

Few users, single-maintainer utilities, anything obscure. Bigger
supply-chain blast radius.

- `cooldown` lets a malicious or yanked release surface upstream first.
- A major gets a changelog read before merge.
- **When unsure which class a dependency is in, default to Class 2.**

## Cadence and security alerts

- Security **alerts** ON, **auto**-security-fix PRs OFF: adopt security
  fixes promptly but reviewed, never blind-merged.
- Prefer one Dependabot PR per repo per week so the pool is not overrun by
  per-ecosystem PRs. The mechanical gates remain the per-repo CI
  (frozen/locked lockfiles, lint/type) — there is no bot auto-merging by
  class.

Lockfile handling on a red Dependabot PR: restore from main, never blanket
re-lock.
