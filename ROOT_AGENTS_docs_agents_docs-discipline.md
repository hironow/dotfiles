# Documentation discipline

Read this when you edit docs, manage rules (`docs/rules.toml` or
`provable-glossary`), or touch `intent.md` or `handover.md`. AGENTS.md has the
short version. Write every document in plain language
(docs/agents/plain-language.md).

Each artifact answers one question without duplicating code as prose:

| artifact | answers | mutability |
| --- | --- | --- |
| Code + tests + `glossary/` (`provable-glossary`) | What invariants and domain rules hold **now** (machine-checked)? | updated with code; `glossary/docs/generated/` is generated only |
| `docs/rules.toml` | Which non-codable operational rules and named exceptions apply **now**? | updated via PR + human ruling (`consultation_url`) |
| `docs/rules-retired.toml` | Which rules were retired (never auto-loaded)? | append-only on retirement |
| `docs/intent.md` | **Why** are we doing this right now? | updated when intent shifts |
| `docs/handover.md` | **Where** are we, what's **next**? | updated each session |

## No standalone `docs/adr/` or `docs/pdr/` files

- Do not create standalone `docs/adr/` or `docs/pdr/` prose files.
- Encode verifiable invariants in code, tests, lint/CI checks, or
  `provable-glossary` (`glossary/Glossary/*.lean`, `glossary/Spec/*.qnt`).
- Put non-codable operational policies and named exceptions in `docs/rules.toml`
  following the `decision-record-governance` skill (stable ID, `@handle`
  contacts, human ruling URL, and consistency check).
- Keep pending proposals and rationale ("Why") in GitHub Draft PRs, Issues, and
  commit history.

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
