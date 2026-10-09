# Documentation Discipline

Read this when you edit docs, write an ADR or PDR, or touch `intent.md`,
`handover.md`, `decision-queue.md`, `plan/`, or `research/`. AGENTS.md has the
short version. Write every document in plain language
(docs/agents/plain-language.md).

Each kind of document answers one question. The rows from
`docs/decision-queue.md` down are opt-in: only repos that adopted them have
them.

| file              | answers                                  | mutability             |
| ----------------- | ---------------------------------------- | ---------------------- |
| `docs/*.md`       | What does the system do **now**?         | always current         |
| `docs/adr/*.md`   | **Why** did we decide X (in the past)?   | immutable once accepted|
| `docs/intent.md`  | **Why** are we doing this right now?     | updated when intent shifts |
| `docs/handover.md`| **Where** are we, what's **next**?       | updated each session   |
| `docs/decision-queue.md` | What awaits a **human decision**? | updated as decisions open/close |
| `docs/pdr/*.md`   | **Why** did we decide X (product/ops)?   | immutable once accepted|
| `docs/plan/*.md`  | **How** will we implement X (phased)?    | mutable until done, then graduates |
| `docs/research/*.md` | What did we **find** (dated)?         | snapshot; superseded by newer |

## `docs/*.md` — current state only

- Describe only the current implementation. No history, no "why we changed
  from X to Y" (that belongs in an ADR), no TODOs, no roadmap, no notes on
  deprecated features.
- Keep docs and code consistent at all times. When code changes, update the
  docs in the **same commit**. Outdated docs are bugs.
- Point to code where you can; it keeps docs accurate.
- These are exempt from "current state only": `docs/adr/`, `docs/intent.md`,
  `docs/handover.md`, and the opt-in categories `docs/decision-queue.md`,
  `docs/pdr/`, `docs/plan/`, `docs/research/`.

## `docs/adr/` — Architecture Decision Records

An ADR records the *why* behind a significant decision. Docs record only the
*what*.

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
{The problem and constraints at the time. What forces are at play?}

## Decision
{What we are doing. State it clearly and concisely.}

## Consequences
### Positive
- {Benefit}
### Negative
- {Tradeoff}
### Neutral
- {Implication that's neither clearly positive nor negative}
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

Update it at the end of every significant work session (per session, not per
commit). Do not copy `intent.md` into it; link to it.

## Opt-in categories (adopt per repo)

Use these only in repos that adopted them. In such a repo, its governance ADR
decides any local changes to these rules.

- **`docs/decision-queue.md` + `docs/pdr/`** — decision-record governance (see
  the `decision-record-governance` skill). The queue is the single source of
  truth for unapproved (Proposed) ADRs and PDRs. The flow: file a record →
  add it to the queue → the human decides → move the row to the decided log.
  Record the adoption itself as an ADR. That ADR sets local profiles (for
  example a solo profile without Slack, or replacing `intent.md` with PDRs).
  This repo adopted the queue for all **new** ADRs and PDRs in
  [ADR-0051](https://github.com/hironow/dotfiles/blob/main/docs/adr/0051-adopt-decision-queue-for-new-records.md):
  consult in a public-safe PR because Issues are disabled, and do not rewrite
  or guess contacts for the older 49 ADRs.
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
