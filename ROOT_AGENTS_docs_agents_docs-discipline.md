# Documentation Discipline

Read this when editing docs, writing an ADR/PDR, or touching `intent.md`/
`handover.md`/`decision-queue.md`/`plan/`/`research/`. Root summary is in AGENTS.md.

Core documentation kinds, one question each (rows below the divider are
opt-in categories — present only in repos that use them):

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

- Document only the current implementation. No history, no "why we changed from
  X to Y" (that's an ADR), no TODOs, no roadmap, no deprecated-feature notes.
- Docs and implementation stay consistent at all times; when code changes, update
  docs in the **same commit**. Outdated docs are bugs.
- Use code references where possible to keep accuracy.
- Exempt from "current state only": `docs/adr/`, `docs/intent.md`,
  `docs/handover.md`, and the opt-in categories `docs/decision-queue.md`,
  `docs/pdr/`, `docs/plan/`, `docs/research/`.

## `docs/adr/` — Architecture Decision Records

Capture the *why* behind significant decisions (docs only capture the *what*).

Create one when: introducing a new technology/framework; changing an established
pattern; making a non-obvious tradeoff with significant consequences; deprecating
or replacing an approach; making a decision future developers might question.

Naming: `docs/adr/NNNN-short-title.md` (sequential `0001`, `0002`, …; lowercase
hyphenated title), e.g. `docs/adr/0001-use-fastapi-for-api-layer.md`.

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

Immutability: ADRs are never modified after acceptance. To change a decision,
write a **new** ADR that supersedes the old one, and set the old one's status to
`Superseded by [NNNN]` — the only allowed edit. ADRs complement docs; they don't
replace them.

## `docs/intent.md` — the human's intent for the current work unit

**Before creating or updating it, clarify ambiguous intent by asking the human.
Never guess; never fill gaps with assumptions.** If any of these are unclear,
STOP and ask: goal, success criteria, scope boundaries, non-goals, constraints,
deadlines, affected components, rollback conditions.

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

Update when the requester's intent changes (not every implementation detail).
Superseded versions live in git history, not in the file.

## `docs/handover.md` — for the next actor

Optimized to be read in under two minutes; consumable by both humans and agents.

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

Update at the end of every significant work session (session-level, not
commit-level). Don't duplicate `intent.md`; reference it.

## Opt-in categories (adopt per repo)

Use these only in repos that have adopted them; the adopting repo's governance
ADR is authoritative for local adaptations.

- **`docs/decision-queue.md` + `docs/pdr/`** — decision-record governance (see
  the `decision-record-governance` skill). The queue is the SSoT of unapproved
  (Proposed) ADR/PDRs: file a record → register it in the queue → the human
  decides → move the row to the decided log. Record the adoption itself as an
  ADR; that ADR governs local profiles (e.g. a solo profile without Slack, or
  retiring `intent.md` in favor of PDRs).
- **`docs/plan/`** — phased execution plans (HOW; decisions stay in DRs). Keep a
  standard status header (state / related DRs / blocking decisions). Never leave
  a pending human decision inside a plan — file a DR into the queue and mark the
  plan blocked. On completion, move permanent explanations to
  architecture/ADR and mark the plan `done(→destination)`; a plan that embodies
  no new decision graduates into architecture, not into a why-less ADR.
- **`docs/research/`** — dated investigation snapshots (`YYYY-MM-…` filenames).
  Newer research supersedes older; never treat them as current-state docs.
