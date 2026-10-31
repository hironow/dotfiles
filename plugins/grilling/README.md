# grilling

Socratic plan grilling with a GRIT resolve check and human-approved intent capture.

## `grit-grill`

Invoke with `/grilling:grit-grill`.

Grills the plan one question at a time, then pressure-tests the plan and resolve
along four axes:

- **Guts**: willingness to face the hardest unknown.
- **Resilience**: recovery when the current approach fails.
- **Initiative**: taking the next concrete action.
- **Tenacity**: commitment to the defined finish line.

It ends with an ASCII radar-style scorecard (1–5 per axis, anchored to a rubric)
and names the weakest axis with one concrete next move. It then drafts
`docs/intent.md` from the answers and writes it only after human confirmation.
Unresolved branches remain in Open Questions; the scorecard stays in chat.

## Related workflows

- The standalone `grilling` skill explores a plan's design decisions.
- This plugin adds resolve interrogation, a GRIT scorecard, and intent capture.
- [`intent-handover-governance`](https://github.com/hironow/skills/tree/main/intent-handover-governance)
  owns session handover creation and maintenance, including repository-specific
  tracking policy. Use that skill to write `docs/handover.md`.
- EGM reviews design documents; it does not replace the GRIT interview.
