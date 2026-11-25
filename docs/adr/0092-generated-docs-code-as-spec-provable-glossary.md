# ADR 0092 — Documentation is generated for humans, code is the spec, a provable glossary proves its words, and Markdown is not tested

- **id**: ADR-0092
- **title**: Documentation is generated for humans, code is the spec, a provable glossary proves its words, and Markdown is not tested
- **status**: Accepted
- **date**: 2026-11-25
- **decided-date**: 2026-11-25
- **decision-maker**: Hiroto N.
- **decision-maker-contact**: @hironow
- **author**: Claude Code (owner session)
- **author-contact**: @hironow
- **supersedes**: part of [0078](0078-frontend-ci-under-two-minutes.md) D8 and of [0080](0080-established-terms-not-private-ones.md) D7 (their clauses that a test keeps the rule text), and part of [0090](0090-keep-one-justfile-no-modules.md) D1 (the provable glossary's module only)
- **superseded-by**: none
- **related**: [0078](0078-frontend-ci-under-two-minutes.md), [0080](0080-established-terms-not-private-ones.md), [0090](0090-keep-one-justfile-no-modules.md), [0088](0088-ci-speed-standard-for-every-language.md), [0091](0091-review-against-requirements-three-rounds.md)
- **consultation-trace**: the owner's request in a Claude Code session on 2026-11-25 (16:24 JST), the owner's answers to four questions (16:35 JST) and to a fifth one raised by the plan review (17:05 JST), quoted in the pull request that adds this record ([PR #686](https://github.com/hironow/dotfiles/pull/686)); the owner accepted the record on 2026-11-25 ("0092 approveします"), quoted in [PR #688](https://github.com/hironow/dotfiles/pull/688)

## Plain summary

Documents that explain a system are written for humans and are generated from the code and a glossary, not written by hand.
Agents read the code as the spec.
A project's own domain terms are defined and proved in a provable glossary, and code names things with those terms, so humans and agents use the same words.
Tests check what code does, never what a Markdown file says.

## Context

- The owner asked to update the global agent instructions with this text (2026-11-25, 16:24 JST):

  > Do not test for markdown
  > Document only exist generated for human reading not ai agent
  > Ai agent should be code as spec and vocabulary is proven by 形式手法
  > Then human and Ai agent use a same words
  > Write codes by ai agent and human that should be 写像 by provable gllosasy

  and summarised it as: refuse tests for Markdown files, and allow documents only as generated artifacts for humans.
- Before this record, `docs/agents/docs-discipline.md` asked for hand-written `docs/*.md` kept current in the same commit as the code; `docs/agents/naming.md` let any glossary skill hold the terms; `docs/agents/formal-methods.md` said Lean is not used; no rule covered tests of Markdown.
- In this repository, about 44 of the 224 files in `tests/unit/` read a Markdown file. Some check the wording of instruction files (for example `test_established_terms_guidance.py`, `test_frontend_ci_guidance.py`, `test_review_rules.py`); others test code that reads Markdown (sync, skills).
- ADR-0078 D8 and ADR-0080 D7 decided that a test keeps the rule text of their spokes.
- The owner's unmerged branch `feat/provable-glossary` (2026-11-21) builds a provable glossary for this repository and moves its decision records into it; it is a separate piece of work.

## Owner's rulings (2026-11-25, 16:35 JST)

Asked four questions in the session, the owner chose the recommended option of each:

1. Markdown tests: ban tests of what Markdown says (wording, sections, whether a rule is there). Lint, link checks, size limits and the check that generated docs match their generator stay. Existing content tests are deleted in a separate pull request; the test clauses of ADR-0078 D8 and ADR-0080 D7 are replaced by a new record (this one).
2. Scope of "generated only": documents that explain the system (`docs/*.md`, the body of a README). A README keeps a few hand-written lines. Instruction files and working records (intent, handover, decision records) are not documentation and stay hand-written.
3. Scope of "code is a mapping of the glossary": every repository that has domain terms. A new domain term goes into the glossary first; a repository without one starts one with its first new domain term; established technical terms stay out; existing names stay until a human decides.
4. Relation to `feat/provable-glossary`: this change edits only the global rules, from `main`; the branch's migration of this repository is not touched.
5. (17:05 JST, after the plan review found the conflict) The `provable-glossary` skill gives an existing repository a `glossary/mod.just` loaded by `mod glossary`, while the global rule keeps exactly one justfile and ADR-0090 D1 uses no `mod`. The owner chose to allow the glossary's module as the one exception.

## Decision

In the hub (`ROOT_AGENTS.md`, "Documentation rules") and the spokes `docs-discipline.md`, `naming.md`, `testing.md` and `formal-methods.md`:

- D1. Documents that explain the system to humans MUST be generated from the code and the project's provable glossary by a root `just` recipe, and MUST NOT be written or edited by hand. A check MUST fail when the committed docs differ from the generator's output. A README MAY keep a few hand-written lines (what the project is, how to generate its docs, where they are).
- D2. Agents MUST read the code (types, tests, recipes, checks) and the glossary's proved terms and claims as the spec, not the docs.
- D3. Hand-written docs a repository already has MAY stay until generated docs replace them; while they last they MUST stay correct and current-state only, and no new hand-written doc or section MAY be added.
- D4. Instruction files (`AGENTS.md`, `CLAUDE.md`, spokes, skills) and working records (`docs/adr/`, `docs/intent.md`, `docs/handover.md`, the opt-in `docs/decision-queue.md`, `docs/pdr/`, `docs/plan/`, `docs/research/`, and the provable glossary's analysis documents) are not documentation and stay hand-written.
- D5. A project's own domain terms MUST be defined, and their claims proved, in its provable glossary (the `provable-glossary` skill). Code MUST be a mapping of it: the core names each domain type, function and value with a glossary term, and the glossary records each term's code anchor. A new domain term MUST enter the glossary before it enters code. A repository without a glossary MUST start one when it adds its first new domain term. Established technical terms need no entry. Existing names stay until a human decides.
- D6. No test MAY check what a Markdown file says (its wording, its sections, whether a rule or phrase is in it). Lint and format, link checks, size limits, the generated-docs check, and tests of code that reads or writes Markdown stay. A change to Markdown alone needs no new test.
- D7. `formal-methods.md` keeps Quint for the distributed-state gate; Lean and the other tools of the provable glossary are used for the glossary.
- D8. The provable glossary's module is the one exception to "exactly one justfile": the root `justfile` MAY load `glossary/mod.just` with `mod glossary`, as the skill writes it. The root `justfile` stays the one entry point. No other `mod` is added by this record.

## Options considered

- A. This record (the owner's recommended options).
  Benefits: one source of truth per fact (code and glossary); docs cannot drift; humans and agents share one vocabulary; no test breaks when a sentence is reworded.
  Costs: every repository with domain terms needs a Lean and Quint glossary and a doc generator; rules in Markdown lose the guard a content test gave them, and rely on review.
- B. Ban only new Markdown tests and keep the existing ones.
  Benefits: no tests are deleted.
  Costs: the rule and the repository disagree for as long as the old tests live. Not chosen by the owner.
- C. Also stop writing decision records (the design of `feat/provable-glossary`).
  Benefits: decisions live in code, tests and the glossary only.
  Costs: a larger migration in every repository, and decision governance (ADR-0051) changes. Not chosen now; the branch stays separate.
- D. Require a glossary only where one already exists.
  Benefits: no new glossary work in other repositories.
  Costs: humans and agents keep different words in most repositories. Not chosen by the owner.

## Consequences

- Positive: docs cannot fall behind the code; a reader, human or agent, finds one word for one concept; Markdown edits no longer break tests.
- Negative: the first new domain term in a repository costs a provable glossary; until generators exist, a repository can only keep its old hand-written docs correct, not add to them; a deleted rule in a spoke is caught by review, not by a test.
- Neutral: the follow-up pull request deletes this repository's Markdown content tests (ADR-0091's consequences name one of them, `test_review_rules.py`; its decisions are unaffected).

## Reversal

Restore the earlier hub section and spokes from git history; the deleted content tests come back from the follow-up pull request's parent commit.

## Consistency with other decision records

- **Contradiction**: ADR-0078 D8 and ADR-0080 D7 (a test keeps the rule text) contradict D6. The owner ruled (ruling 1): this record replaces those clauses; on acceptance their status lines say so and nothing else in them changes.
- **Related, no contradiction**: ADR-0080 D4 (use a glossary skill to choose many terms) stays; D5 adds where the project's own domain terms are kept. ADR-0080 D6 (approved terms are recorded in a glossary or an ADR) holds: a glossary term is an approved term.
- **Contradiction**: ADR-0090 D1 (no `mod` for now, in this repository) contradicts D8 for the glossary's module. The owner ruled (ruling 5): D8 wins for that one module; on acceptance ADR-0090's status line says so, and its other decisions stand.
- **Misreading**: ADR-0088 records that Lean is not used for the distributed-state gate; D7 keeps that and adds the glossary's use.
- **Not affected**: ADR-0051 and the decision-record practice (D4 keeps records hand-written); ADR-0091's decisions.

## Decision (2026-11-25)

- [x] Accept / [ ] Accept with changes / [ ] Reject / [ ] Defer
- Decision-maker and date: Hiroto N. (@hironow), 2026-11-25 17:49 JST. After both pull requests had passed CI and merged (#686, the rules; #687, this repository's Markdown content tests removed), the owner wrote "0092 approveします" (translated: I approve 0092). The decision fields were filled in on the owner's behalf from that ruling, which is quoted in [PR #688](https://github.com/hironow/dotfiles/pull/688).
- Action: ADR-0078, ADR-0080 and ADR-0090 say on their status lines that this record replaced part of them; nothing else in them changes. The content tests were removed in #687.
