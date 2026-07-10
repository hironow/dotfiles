<!--
  AGENTS.md — cross-tool agent instructions (read by Codex, Cursor, Copilot,
  Claude Code via @import, and others). Keep this file SHORT and always-loaded.

  Why short: frontier models reliably follow ~150-200 instructions (a working
  heuristic, not a measured constant); the agent's own system prompt already
  spends ~50. Every line here dilutes every other line. Adherence — not token
  cost — is the constraint. Anything that is not needed on turn one lives in
  docs/agents/*.md and is read on demand (see the index below).
  `just instruction-budget` gates a list-item proxy of this file + the overlay
  so the always-loaded set cannot grow unnoticed.

  Self-reference: this file and docs/agents/*.md intentionally name a few
  prohibited patterns as examples. Exclude them from repo scans:
    git grep: add :(exclude)**/AGENTS.md :(exclude)**/CLAUDE.md :(exclude)docs/agents/**
    semgrep : paths.exclude: [AGENTS.md, CLAUDE.md, "docs/agents/**"]
-->

# AGENTS.md

Production code for a solo-operated, human-on-the-loop agentic engineering
ecosystem (Go services + Python tooling on GCP). Treat changes conservatively:
prefer the smallest correct change, prove it, and leave the tree green.

When instructions conflict, the closest file to the edited file wins, and an
explicit chat instruction overrides everything here.

## Non-negotiables (enforced by hooks + CI — see Enforcement)

These are not preferences. Hooks gate them mechanically for Claude Code in every
repo; other tools rely on the pre-commit + CI gate where the agent baseline is
installed. The reasons are given so you generalize correctly to unlisted cases.

- **`uv` only** for Python (`uv sync`, `uv add`, `uv run`). Never `pip`, `poetry`,
  `pipenv` — mixed resolvers desync the lockfile.
- **`bun` only** for Node. Never `npm`/`yarn`/`pnpm` (incl. `corepack pnpm`) —
  same lockfile-desync reason. (corepack stays installed for machine
  provisioning; agents just never invoke a package manager through it.)
- **`just` is the only task runner.** Exactly one `justfile` at the repo root,
  no subdirectory justfiles, no `make`. One entrypoint = one place to look.
- **`.yaml`, never `.yml`.** Compose files are `compose.yaml` (Compose Spec v2+);
  `docker-compose.y{a,}ml` is the deprecated v1 name. One spelling avoids
  tool-discovery misses and review churn.
- **No mocks in e2e tests.** If a real dependency can't be used, it isn't an e2e
  test — move it to integration. Mocked e2e tests assert nothing about reality.
- **No manual mutation of IaC-managed infra.** Production (GCP, IAM, Cloud Run,
  Coder VMs) changes only through OpenTofu + PR + CD. A stray `gcloud ... update`
  creates drift the next `tofu apply` silently reverts. Details:
  docs/agents/iac-drift-policy.md.
- **Never weaken the gates to pass.** Do not edit ruff/mypy/semgrep config to
  silence a finding, and never commit with failing tests or non-zero lint/type
  findings. Fix the cause.

## Golden-path commands

```sh
just            # list all tasks (default: help)
just check      # the full local gate: fmt + lint + types + semgrep + test
just test       # uv run pytest
just lint       # ruff check + mypy
just fmt        # ruff format
just semgrep    # semgrep --config .semgrep/rules/ --error  (when .semgrep/ exists)
just install-hooks   # wire .githooks as core.hooksPath (run once per clone)
```

If a command you need isn't a `just` task, add it to the root `justfile` rather
than inventing a one-off script (see docs/agents/project-structure.md).

## Decision priorities (when principles conflict)

1. Safety & correctness over performance.
2. Passing tests over code elegance.
3. Readability over brevity.
4. Explicit over implicit.

When in doubt, write a test to pin down the requirement before coding.

## How to work here (TDD + Tidy First, in brief)

- Drive every change with a failing test first: **Red → Green → Refactor.**
  Write the minimum to pass; refactor only on green. Full cycle + worked example:
  docs/agents/tdd-workflow.md.
- **Separate structural from behavioral changes** — never in the same commit.
  Structural first, behavioral second. The Conventional Commit *type* encodes
  which is which; mixing types in one commit is forbidden. Full mapping +
  examples: docs/agents/commit-discipline.md.
- **Verify before claiming done.** Run `just check`. State results honestly;
  report failures rather than papering over them.

## GRIT (required both ways — embody it AND demand it from collaborators)

GRIT = Guts (度胸) / Resilience (復元力) / Initiative (主体性) / Tenacity (執念).
**Guts**: hit the scariest/least-known part first; state unknowns plainly.
**Resilience**: failure means change the hypothesis and retry — never stop or
hand back a half-result. **Initiative**: take the obvious next step unprompted;
still confirm irreversible or out-of-scope actions. **Tenacity**: define "done"
concretely and grind to it; never claim success unproven.

On weak resolve — a vague finish line, an unfaced unknown, a "waiting on someone
else" gap — stop and press for a concrete commitment; record uncommitted risks
in docs/handover.md. When delegating, demand a definition of done, a
failure-recovery path, and proof of completion. Rubric (1-5):
`grilling:grit-grill` skill; below 3 on any blocking axis = stop and clarify.

## Documentation contract (short version)

- `docs/*.md` describe the **current** system only — no history, no TODOs, no
  roadmap. Outdated docs are bugs; update docs in the same commit as the code.
- `docs/adr/*.md` capture the **why** behind significant decisions; immutable
  once accepted.
- `docs/intent.md` = "why we're doing this now" (human-authored; never guess it —
  ask). `docs/handover.md` = "where we are, what's next" (update each session).
- Repos may adopt decision-record governance (`decision-record-governance` skill):
  `docs/decision-queue.md` = SSoT of unapproved decisions, `docs/pdr/` = product
  decisions (immutable like ADRs). The adopting repo records the adoption as an
  ADR, which then governs local roles (it may e.g. retire `intent.md` in favor
  of PDRs). Dated working sets `docs/plan/` (execution plans; graduate into
  ADR/architecture when done) and `docs/research/` (dated investigations) are
  exempt from "current only".
- Full rules: docs/agents/docs-discipline.md.

## Detailed playbooks — read on demand (do not preload)

Open the matching file the moment the trigger applies:

| When you are…                                  | Read                                |
| ---------------------------------------------- | ----------------------------------- |
| writing/changing Python                        | docs/agents/python-tooling.md       |
| in the Red/Green/Refactor loop                 | docs/agents/tdd-workflow.md         |
| writing a commit message                       | docs/agents/commit-discipline.md    |
| writing or placing tests / asking "mock?"      | docs/agents/testing.md              |
| adding telemetry, spans, or a service          | docs/agents/observability.md        |
| touching `tofu/`, `gcloud`, `cdr`, Cloud Run   | docs/agents/iac-drift-policy.md     |
| adding/maintaining a Semgrep rule              | docs/agents/semgrep.md              |
| editing docs / writing an ADR / intent / handover | docs/agents/docs-discipline.md   |
| creating dirs/files or unsure where code goes  | docs/agents/project-structure.md    |
| blocked by a hook / tuning or adding a hook    | docs/agents/enforcement.md          |

## Enforcement (deterministic — independent of model judgment)

Instructions in this file are advisory; the rules below are not. They run
regardless of what an agent decides:

- **Claude Code hooks** (global, synced to `~/.claude`): block prohibited
  filenames and commands before they execute; auto-format Python after edits.
- **Git pre-commit** (`.githooks/pre-commit` → `just check`): no commit lands
  red. Enable with `just install-hooks`.
- **CI** (`.github/workflows/quality-gate.yaml`): same gate + `tofu plan` drift
  check, required before merge.

Exit-code contract, full hook coverage, and tuning: docs/agents/enforcement.md.
