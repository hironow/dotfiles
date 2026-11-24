# ADR 0091 — Review against the requirements, accept only bugs and broken requirements, stop after three rounds

- **id**: ADR-0091
- **title**: Review against the requirements, accept only bugs and broken requirements, stop after three rounds
- **status**: Accepted
- **date**: 2026-11-24
- **decided-date**: 2026-11-25
- **decision-maker**: Hiroto N.
- **decision-maker-contact**: @hironow
- **author**: Claude Code (owner session)
- **author-contact**: @hironow
- **supersedes**: none
- **superseded-by**: none
- **related**: [0088](0088-ci-speed-standard-for-every-language.md)
- **consultation-trace**: the owner shared a discussion on adversarial reviews on 2026-11-23 and asked for Claude's view; Claude recommended this record with two changes and one addition; the owner answered "ではおすすめで、進めてください" (translated: then go ahead with your recommendation); the owner accepted the record on 2026-11-25 ("ADR-0091 を approveします"), quoted in [PR #685](https://github.com/hironow/dotfiles/pull/685)

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

## Decision

In `docs/agents/plan-review.md` (titled "Plan and code review"; the file name is kept so every reference stays valid) and one sentence in the Claude overlay, every review of a plan or of code follows these rules:

- D1. The author MUST brief the reviewer with the requirements: the human's request (quoted), what "done" means, and the rules that apply.
- D2. The author MUST ask a neutral question: report only (a) a broken requirement or rule, quoted, or (b) a bug, with the situation and the wrong result, and the question MUST say that "no findings" is a complete answer and often the right one. The author MUST NOT ask the reviewer to find problems or improvements.
- D3. The author MUST accept a finding only when it shows a bug or a broken requirement or rule and the author confirmed it, and MUST decline every other finding with a one-line reason. Declining every finding is a valid outcome.
- D4. A review MUST NOT take more than three rounds: round 1 reviews the whole, rounds 2 and 3 only the changes and the accepted findings. There MUST NOT be a fourth round for any finding; what is left MUST be settled by a test or recorded as an open risk.
- D5. What a test or a measurement can settle MUST be settled by one, instead of another round.
- D6. When two requirements conflict in a finding, the author MUST decide which wins for this work and MUST record the decision and the reason.
- D7. When findings are passed to an author, the author MUST evaluate each and MAY decline all of them; a request to improve one's own work MUST name the requirement and MUST leave "no change is needed" open as an answer.
- D8. These stay as they were and MUST still be followed: an independent review of every behaviour-changing plan before the human sees it, never in the context that wrote it, Codex first with a fresh subagent as fallback, no whole gate run by a reviewer, and the three lenses.

## Limits of the evidence

One day, one reviewer, about seven plans of different sizes: the effect of the prompt is not separated from the effect of the plans themselves. Revisit this record if work that a review passed with "no findings" breaks repeatedly in CI or on main.

## Options considered

- A. This record: requirements, a neutral question, only bugs and broken requirements, three rounds, tests for the rest.
  Benefits: rounds end; findings that are only preferences stop setting the scope; the reviewer may say "no findings".
  Costs: a defect that a capped review misses must be caught by tests, CI or main. Chosen.
- B. Keep the critical prompt and only add a round cap.
  Benefits: the smallest change; the reviewer keeps looking hard.
  Costs: the prompt still asks for findings, so each round still finds something and every finding still sets the scope. Not chosen for that reason.
- C. Drop independent review and rely on tests.
  Benefits: no review time at all.
  Costs: reviews under the new prompt still found real defects that tests would not have (a cache key that silently stops working after a runner update). Not chosen for that reason.

## Consequences

- Positive: fewer rounds and smaller diffs per review; findings that are only preferences are declined on the record.
- Negative: a real defect that a capped review misses must be caught by tests, CI or main; D5 and the existing CI gates carry that.
- Neutral: the review rules live in one spoke and one overlay sentence, pinned by `tests/unit/test_review_rules.py`.

## Reversal

Restore the earlier `docs/agents/plan-review.md` and the overlay sentence from git history.

## Consistency with other decision records

- ADR-0088's rule "measure before and after" is the basis of D5; no record decides on review rounds or prompts.

## Decision (2026-11-25)

- [x] Accept / [ ] Accept with changes / [ ] Reject / [ ] Defer
- Decision-maker and date: Hiroto N. (@hironow), 2026-11-25 02:31 JST. After the rules had run on four pull requests (#681 to #684), the owner wrote "ADR-0091 を approveします" (translated: I approve ADR-0091). The decision fields were filled in on the owner's behalf from that ruling, which is quoted in [PR #685](https://github.com/hironow/dotfiles/pull/685).
- Action: none beyond this record; the rules are already in `docs/agents/plan-review.md` and the Claude overlay, distributed to every agent home on 2026-11-24.
