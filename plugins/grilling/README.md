# grilling

Socratic grilling skills that interview you about a plan or design until you reach
a shared understanding. Derived from the standalone `grill-me` skill.

## Skills

### `grit-grill`

Invoke with `/grilling:grit-grill`.

Grills your plan one question at a time (each with a recommended answer), then
pressure-tests both the plan and your resolve to finish it along the four GRIT axes:

- **G**uts — 度胸・闘志
- **R**esilience — 復元力・粘り強さ
- **I**nitiative — 自発性・主体性
- **T**enacity — 執念・やり切る力

It ends with an ASCII radar-style scorecard (1-5 per axis, anchored to a rubric)
and names the single weakest axis with one concrete next move.

Finally, it crystallizes the shared understanding reached during grilling into
`docs/intent.md` (canonical Goal / Success Criteria / Scope / Constraints / Open
Questions format) — drafted from the answers, written only after you confirm.
Unresolved branches land in **Open Questions**; the scorecard stays in the chat.

### `handover`

Invoke with `/grilling:handover`.

Compacts the current work session into `docs/handover.md` (canonical Current State /
In Progress / Next Actions / Known Risks / Context / Relevant Files format) so the next
actor — a fresh agent, a teammate, or future you — can pick up in under two minutes.
Drafted from the conversation, written only after you confirm. Redacts secrets, references
`docs/intent.md` instead of repeating the goal, and folds suggested skills into Next Actions.
An optional argument describes what the next session will focus on.

Extends the standalone `/handoff` skill, which writes the same kind of summary to the OS
temp directory instead of persisting it in the repo.

## Relation to grill-me / handoff

- `grill-me` (standalone) grills a plan along the design tree only.
- `grit-grill` adds the GRIT resolve interrogation, the scorecard, and `docs/intent.md` output.
- `handoff` (standalone) writes a session handover to the OS temp directory (ephemeral).
- `handover` persists the session handover to `docs/handover.md` (repo, durable).

Together, `grit-grill` captures the **intent** (why / what) and `handover` captures the
**state** (where / next) — the two repo-level docs the project treats as living memory.
