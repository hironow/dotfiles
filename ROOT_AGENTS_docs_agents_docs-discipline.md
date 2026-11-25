# Documentation discipline

Read this when you edit docs, write an ADR (architecture decision record)
or PDR (product decision record), or touch `intent.md`,
`handover.md`, `decision-queue.md`, `plan/`, or `research/`. AGENTS.md has the
short version. Write every document in plain language
(docs/agents/plain-language.md).

Each kind of document answers one question. The rows from
`docs/decision-queue.md` down are opt-in: only repos that adopted them have
them.

| file              | answers                                  | mutability             |
| ----------------- | ---------------------------------------- | ---------------------- |
| `docs/*.md`       | What does the system do **now**? (for humans) | generated; never edited by hand |
| `docs/adr/*.md`   | **Why** did we decide X (in the past)?   | immutable once accepted|
| `docs/intent.md`  | **Why** are we doing this right now?     | updated when intent shifts |
| `docs/handover.md`| **Where** are we, what's **next**?       | updated each session   |
| `docs/decision-queue.md` | What awaits a **human decision**? | updated as decisions open/close |
| `docs/pdr/*.md`   | **Why** did we decide X (product/ops)?   | immutable once accepted|
| `docs/plan/*.md`  | **How** will we implement X (phased)?    | mutable until done, then graduates |
| `docs/research/*.md` | What did we **find** (dated)?         | snapshot; superseded by newer |

## `docs/*.md` — generated, for humans

- Documentation explains the system to humans. Generate it from the code and
  the project's provable glossary with a root `just` recipe. Never write it or
  edit it by hand. A check fails when the committed docs differ from what the
  generator makes now, so the docs cannot fall behind the code.
- Agents do not read documentation as the spec. The spec is the code (types,
  tests, recipes, checks) and the glossary's proved terms and claims
  (docs/agents/naming.md).
- To explain something, write it where the generator reads it: a type, a
  test, a recipe's `[doc]` text, a check, or a glossary term or claim. Do not
  add a hand-written doc.
- A README keeps only a few hand-written lines: what the project is, and how
  to generate its docs and where to find them.
- Hand-written docs that a repo already has stay until generated docs replace
  them. While they last, keep them correct, describe only the current
  implementation (no history, no TODOs, no roadmap), and fix in the same
  commit what a code change makes wrong. Do not add new ones or new sections.
- Not documentation, and still written by hand:
    - instruction files: `AGENTS.md`, `CLAUDE.md`, the spokes in
      `docs/agents/`, and skills;
    - working records: `docs/adr/`, `docs/intent.md`, `docs/handover.md`, the
      opt-in `docs/decision-queue.md`, `docs/pdr/`, `docs/plan/`,
      `docs/research/`, and the analysis documents of the provable glossary
      (findings and limits, the comparison with industry practice).

## `docs/adr/` — Architecture Decision Records

An ADR records the *why* behind a decision that the list below covers. Docs
and the glossary record only the *what*.

Write one when you:

- introduce a new technology or framework;
- change an established pattern;
- make a non-obvious tradeoff with significant consequences;
- deprecate or replace an approach;
- make a decision future developers might question.

Name it `docs/adr/NNNN-short-title.md`: a sequential number (`0001`, `0002`,
…) and a lowercase, hyphenated title. Example:
`docs/adr/0001-use-fastapi-for-api-layer.md`.

Template:

```markdown
# {NNNN}. {Title}

**Date:** YYYY-MM-DD
**Status:** Proposed / Accepted / Deprecated / Superseded by [NNNN]

## Context
{The problem, and the limits that applied when you decided.}

## Decision
{What we decided, in one or two sentences.}

## Consequences
### Positive
- {Benefit}
### Negative
- {Tradeoff}
### Neutral
- {An effect that is neither clearly good nor bad}
```

Never change an ADR after it is accepted. To change a decision, write a
**new** ADR that supersedes the old one, and set the old one's status to
`Superseded by [NNNN]`. That status change is the only allowed edit. ADRs add
to docs; they do not replace them.

## `docs/intent.md` — the human's intent for the current work unit

**Before you create or update it, ask the human about anything unclear.
Never guess, and never fill gaps with assumptions.** If any of these are
unclear, STOP and ask: goal, success criteria, scope boundaries, non-goals,
constraints, deadlines, affected components, rollback conditions.

```markdown
# Intent

**Last updated:** YYYY-MM-DD
**Requester:** {name}
**Work unit:** {concise id, e.g. Linear issue}

## Goal
{One or two sentences. What outcome does the requester want?}

## Success Criteria
- {Observable, testable criterion}

## Scope
### In scope
- {Item}
### Out of scope (Non-goals)
- {Item}

## Constraints
- {Technical, deadline, budget, compliance}

## Open Questions
- [ ] {Resolve before implementation}
```

Update it when the requester's intent changes, not for every implementation
detail. Old versions live in git history, not in the file.

## `docs/handover.md` — for the next actor

Write it so a human or an agent can read it in under two minutes.

```markdown
# Handover

**Last updated:** YYYY-MM-DD HH:MM (timezone)
**Updated by:** {human name or AI session id}

## Current State
{What is done. One paragraph.}

## In Progress
{Active work. Branch, PR link, Linear issue.}

## Next Actions
1. {Concrete next step}

## Known Risks / Blockers
- {Item and mitigation}

## Context the Next Actor Needs
- {Non-obvious gotchas, env quirks, external deps}

## Relevant Files and Commands
- `path/to/file.py` — {why it matters}
- `just {command}` — {what it does}
```

Update it at the end of every work session that changed code or plans (per
session, not per commit). Do not copy `intent.md` into it; link to it.

## Opt-in categories (adopt per repo)

Use these only in repos that adopted them. In such a repo, its governance ADR
decides any local changes to these rules.

- **`docs/decision-queue.md` + `docs/pdr/`** — decision-record governance (see
  the `decision-record-governance` skill). The queue is the single source of
  truth for unapproved (Proposed) ADRs and PDRs. The flow: file a record →
  add it to the queue → the human decides → move the row to the decided log.
  Record the adoption itself as an ADR. That ADR sets local profiles (for
  example a solo profile without Slack, or replacing `intent.md` with PDRs).
- **`docs/plan/`** — phased execution plans (the HOW; decisions stay in
  decision records). Keep a standard status header (state / related decision
  records / blocking decisions). Never leave a pending human decision inside a
  plan: file a decision record into the queue and mark the plan blocked. When
  the plan is done, move lasting explanations to the architecture docs or an
  ADR, and mark the plan `done(→destination)`. A plan that contains no new
  decision moves into the architecture docs, not into an ADR with no why.
- **`docs/research/`** — dated investigation snapshots (`YYYY-MM-…` filenames).
  Newer research replaces older research. Never treat them as current-state
  docs.
