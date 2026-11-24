# ADR 0091 — Review against the requirements, accept only bugs and broken requirements, stop after three rounds

- **id**: ADR-0091
- **title**: Review against the requirements, accept only bugs and broken requirements, stop after three rounds
- **status**: Proposed
- **date**: 2026-11-24
- **decided-date**: pending
- **decision-maker**: Hiroto N.
- **decision-maker-contact**: @hironow
- **author**: Claude Code (owner session)
- **author-contact**: @hironow
- **supersedes**: none
- **superseded-by**: none
- **related**: [0088](0088-ci-speed-standard-for-every-language.md)
- **consultation-trace**: the owner shared a discussion on adversarial reviews on 2026-11-23 and asked for Claude's view; Claude recommended this record with two changes and one addition; the owner answered "ではおすすめで、進めてください" (translated: then go ahead with your recommendation)

## Plain summary

A reviewer asked to "review critically" finds something every round, and an author who adopts every finding lets the review set the scope instead of the requirement.
The review rules change so that the reviewer is given the requirements and a neutral question in which "no findings" is a valid answer, only bugs and broken requirements are accepted, reviews stop after three rounds, and tests settle what a test can settle.
The rules apply to code review too, not only plans.

## Context

- The owner shared a discussion: adversarial reviews loop (each round finds something new), agents suggest changes that are not needed and pull code away from the requirements, and every word of the prompt tilts the answer; give the reviewer the requirements, fix only real bugs or broken requirements, cap at three rounds, then test; when relaying findings, let the author decline them.
- Before this record, `docs/agents/plan-review.md` asked Codex to "review critically ... from the most fatal point", with no cap on rounds and no rule on which findings to accept.
- What happened under the old prompt (this repository, 2026-11-22/23, Codex as reviewer):

| Work | Rounds | Verdicts | Findings declined |
| ---- | ------ | -------- | ----------------- |
| CI follow-ups (ADR-0089, `tools/ci-audit`) | 7 | REVISE every round | 0 |
| just modernisation plan | 2 | REVISE, REVISE (3 of round 2's 4 findings were about an option later not taken) | 0 |
| sandbox paths (#675) | 3 | REVISE, REVISE, APPROVE | 0 |

- Late rounds still found real defects (a cancelled push in a "before" sample changed a published p50), and they also grew a measurement tool beyond what the decision needed. Tests and CI found at least six defects that no round found.
- Under the new prompt (2026-11-23, four plans): one finding (a fourth-round exception that broke the three-round requirement); no findings; two findings (a missing Go version in a cache key, a missing before-merge measurement); two findings (one accepted: decide the gain before measuring; one declined with a reason: two requirements conflicted). No plan went past two rounds. Measurements, not review rounds, decided two pull requests (#678 and #679 were closed by their numbers).

## Decision (proposed)

In `docs/agents/plan-review.md` (titled "Plan and code review"; the file name is kept so every reference stays valid) and one sentence in the Claude overlay:

- D1. Brief the reviewer with the requirements: the human's request (quoted), what "done" means, and the rules that apply.
- D2. Ask a neutral question: report only (a) a broken requirement or rule, quoted, or (b) a bug, with the situation and the wrong result; "no findings" is a complete answer and often the right one. Do not ask the reviewer to find problems or improvements.
- D3. Accept a finding only when it shows a bug or a broken requirement or rule and you confirmed it; decline the rest with a one-line reason. Declining every finding is a valid outcome.
- D4. At most three rounds: round 1 the whole, rounds 2 and 3 only the changes and the accepted findings. No fourth round, for any finding; what is left is settled by a test or recorded as an open risk.
- D5. What a test or a measurement can settle is settled by one, instead of another round.
- D6. When two requirements conflict in a finding, the author decides which wins for this work and records the decision and the reason.
- D7. When findings are passed to an author, it evaluates each and may decline all; a request to improve one's own work names the requirement and leaves "no change is needed" open.
- D8. Unchanged: an independent review of every behaviour-changing plan before the human sees it, never in the context that wrote it, Codex first with a fresh subagent as fallback, no whole gate run by a reviewer, and the three lenses.

## Limits of the evidence

One day, one reviewer, about seven plans of different sizes: the effect of the prompt is not separated from the effect of the plans themselves. Revisit this record if work that a review passed with "no findings" breaks repeatedly in CI or on main.

## Options considered

- Keep the critical prompt and only add a round cap. Not chosen: the cap alone still lets every finding set the scope.
- Drop independent review and rely on tests. Not chosen: reviews under the new prompt still found real defects that tests would not have (a cache key that silently stops working after a runner update).

## Consequences

- Fewer rounds and smaller diffs per review; findings that are only preferences are declined on the record.
- A real defect that a capped review misses must be caught by tests, CI or main; D5 and the existing CI gates carry that.

## Reversal

Restore the earlier `docs/agents/plan-review.md` and the overlay sentence from git history.

## Consistency with other decision records

- ADR-0088's rule "measure before and after" is the basis of D5; no record decides on review rounds or prompts.
