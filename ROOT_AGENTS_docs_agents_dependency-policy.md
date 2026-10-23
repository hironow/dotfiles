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

**Do not add LiteLLM**, in any repo, language, or Docker image. This is not a
Class 1 / Class 2 judgement — it is a named exception, because the project's
release channel itself has been the attack twice in one year:

- **2026-03**: `litellm` 1.82.7 and 1.82.8 shipped credential-harvesting
  malware from a compromised pipeline.
- **2026-10-21**: `litellm` 1.107.0 shipped a credential stealer plus an hourly
  remote-code loader in **all seven wheels**. It was live on PyPI for about two
  hours (11:39–13:23 UTC), and the Docker Hub / GHCR tags `v1.107.0`, `latest`,
  `main-latest` and `main-stable` pointed at the same build for about two and a
  half hours. Stolen GitHub CLI tokens let the release workflow build from a
  lookalike repository (`Berri-AI/litellm`), so the git tag and the sdist both
  looked clean — only the built artifacts carried the payload.

Why a cooldown is not enough here: a cooldown is sized for a bad release that
stays up long enough to be noticed and yanked. Both LiteLLM incidents were
pulled within hours, so the whole exposure window sits *inside* the window the
cooldown is meant to cover. One pull during it compromises the machine, and the
payload installs `cook.pth` / `sitecustomize.py` into `site-packages`, so every
later `python` or `pip` run in that environment re-runs it.

What to do instead:

- Call the provider's SDK directly (OpenAI, Anthropic, Google Gen AI, ...), or
  use a framework model class that does not route through LiteLLM.
- Until a use is removed, cap it at `<=1.106.2` — the last release published
  before the 2026-10-21 compromise — and keep the seven-day cooldown. The cap
  matters because raising it must be a deliberate, reviewable act.
- Removal is the destination, not the cap. Do not extend an existing use.

### Inventory (2026-10-22) and the removal for each

Everything here was verified by reading the manifests, locks and call sites;
each entry says which kind of work the removal is.

| Where | How LiteLLM is reached | Removal |
| --- | --- | --- |
| `hironow/advena` `backend/genai` | `smolagents[litellm]` plus `LiteLLMModel` (`src/llm/agent.py`); a separate `import litellm` there is unused | Replace the model class (e.g. a non-LiteLLM smolagents model) or the SDK call. **Deployed service — needs the provider decision first.** |
| `hironow/dotfiles` `emulator` | Declared in `emulator/pyproject.toml`; **no code in the tree imports it** | Delete the declaration, re-lock. No behaviour change. |
| `hironow/adk-stream-protocol` | Transitive: `google-adk[extensions]` pulls it | Stop enabling that extra, or drop whatever requires it. |
| a private experiments repo | `experiments/impl/transport/litellm_transport.py` calls `litellm.acompletion`; the root dev group declares it too | Replace the transport with a provider SDK, or retire that experiment. |
| a private monorepo `backend/cue`, `backend/dune` | Declared in each `pyproject.toml`; **no code imports it** | Delete the declaration, re-lock (`dune` is a workspace member, so the root `uv.lock` carries it). |

`backend/echo` (a private monorepo) has LiteLLM in its lock transitively; it goes
with `cue`/`dune` or with whatever pulls it.
