# grilling

Claude Code plugin with one skill, `grit-grill`. It grills a plan, scores your
resolve, and turns the answers into `docs/intent.md`.

Run it with `/grilling:grit-grill`. It asks one question at a time, then tests
the plan and your resolve on the four GRIT axes (Guts, Resilience, Initiative,
Tenacity). It ends with an ASCII radar scorecard (1-5 per axis), names the
weakest axis, and gives one next move. It writes `docs/intent.md` only after
you confirm the draft. The scorecard stays in the chat. The flow, rubric, and
intent template are in
[skills/grit-grill/SKILL.md](skills/grit-grill/SKILL.md).

## Related workflows

- The standalone `grilling` skill explores a plan's design decisions. This
  plugin adds the resolve check, the scorecard, and intent capture.
- [`intent-handover-governance`](https://github.com/hironow/skills/tree/main/intent-handover-governance)
  writes and maintains `docs/handover.md`, including each repo's tracking
  policy.
- EGM reviews design documents. It does not replace the GRIT interview.
