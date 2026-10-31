# Dependency policy

Read this when you add, bump, or triage a dependency (including a Dependabot
PR).

Rule of thumb: **prefer the newest version and the more secure choice.** Staying
current is a security stance: the newest release has the fewest known CVEs
(Common Vulnerabilities and Exposures) and the most people looking at it
upstream. But "newest" is safe only when the package is well tested by wide use.
So sort every dependency into one of two classes, and treat the classes in
opposite ways.

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
- A **preview / release candidate (RC) / canary** major is opt-in and kept
  apart. Do not adopt it just because Dependabot proposed it. Once a repo has
  opted in, moving *forward within that channel* (beta → RC → general
  availability (GA)) is ordinary aggressive adoption. Only **entering** a
  channel from stable is a decision for that repo's maintainer.

## Class 2: niche or little used

Few users, single-maintainer utilities, anything obscure. A compromise here
does more damage through the supply chain.

- Use `cooldown`: a waiting period before you adopt a new release. Upstream
  then finds a malicious or yanked release before you adopt it.
- Read the changelog before you merge a major.
- **If you are unsure which class a dependency belongs to, treat it as Class 2.**

## Cadence and security alerts

- Turn security **alerts** ON and **automatic** security-fix PRs OFF. Adopt
  security fixes promptly, but after review, never by blind merge.
- Prefer one Dependabot PR per repo per week, so separate PRs per ecosystem do
  not flood the CI runner pool. The per-repo CI stays the mechanical gate
  (frozen or locked lockfiles, lint, types). No bot auto-merges a PR because of
  its dependency class.

When a Dependabot PR is red, restore its lockfiles from main. Never re-lock
everything.

## Banned: LiteLLM

**Do not add LiteLLM**, in any repo, language, or Docker image. Its release
channel shipped credential-stealing malware twice in 2026 (1.82.7/1.82.8 in
2026-03 and 1.107.0 on 2026-10-21). Both incidents were yanked within hours, so
the whole exposure window sat inside any cooldown period, and one pull during
that window compromised the environment persistently.

What to do instead:

- Call the provider's SDK directly (OpenAI, Anthropic, Google Gen AI, ...), or
  use a framework model class that does not route through LiteLLM.
- Until an existing use is removed, cap it at `<=1.106.2` (the last release
  before the 2026-10-21 compromise) and keep the seven-day cooldown.
- Removal is the destination, not the cap. Do not extend an existing use.
