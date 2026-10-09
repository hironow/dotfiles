# Dependency policy

Read this when you add, bump, or triage a dependency (including a Dependabot
PR).

Rule of thumb: **prefer the newest version and the more secure choice.**
Staying current is a security stance: the newest release has the fewest known
CVEs and the most people looking at it upstream. But "newest" is safe only when
the package is well tested by wide use. So sort every dependency into one of
two classes, and treat the classes in opposite ways.

## Before you add a dependency

1. Check the language's standard library first, including features added in
   its newest version. If it covers the need, use it.
2. If you still need a package, count what it pulls in (Go: `go mod graph`;
   Rust: `cargo tree`; Python: `uv tree`; TS: `bun pm ls --all`). Prefer the
   package with fewer dependencies, or write the small part you need yourself.
3. Write the reason for the new dependency in the PR.

## Class 1: foundational or widely used

Language toolchains and libraries everyone uses: **TypeScript, bun, Go, uv,
node, rust, Ruff, ty**, and a service's core framework or runtime. Their large
user bases find and fix regressions fast, so falling behind is the riskier
position.

- Adopt the latest **aggressively**. This includes the moving-tag and
  pre-release exceptions a repo has already chosen on purpose (bun `canary`,
  the Python 3.15 pre-release line, ...).
- When a **stable** major removes or renames an API, **fix forward**: update the
  code. Never pin back.
- A **preview / RC / canary** major is opt-in and kept apart. Do not adopt it
  just because Dependabot proposed it. Once a repo has opted in, moving
  *forward within that channel* (beta → RC → GA) is ordinary aggressive
  adoption. Only **entering** a channel from stable is a decision for that
  repo's maintainer.

## Class 2: niche or little used

Few users, single-maintainer utilities, anything obscure. A compromise here
does more damage through the supply chain.

- Use `cooldown`, so a malicious or yanked release shows up upstream first.
- Read the changelog before you merge a major.
- **If you are unsure which class a dependency belongs to, treat it as Class 2.**

## Cadence and security alerts

- Turn security **alerts** ON and **automatic** security-fix PRs OFF. Adopt
  security fixes promptly, but after review, never by blind merge.
- Prefer one Dependabot PR per repo per week, so separate PRs per ecosystem do
  not flood the pool. The mechanical gates stay the per-repo CI (frozen or
  locked lockfiles, lint, types). No bot auto-merges by class.

When a Dependabot PR is red, restore its lockfiles from main. Never re-lock
everything.
