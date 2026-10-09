# Plan review (codex first, independent subagent fallback)

Read this before you show any non-trivial implementation plan to the human.
Someone independent must review the plan **before** the human sees it. Never
skip this review. CLAUDE.md has the pointer here.

## The three lenses (use them for the whole review)

- **何も信用しない — trust nothing.** Treat every claim as a hypothesis to
  check: the reviewer's, the plan's, and your own. Do not act on a finding
  until you confirm it against the actual code, the docs, or a live experiment.
- **The reviewers get reviewed too.** The reviewer can be wrong (old
  knowledge, missing repo context). Judge each finding on its evidence, and
  push back when it is wrong. Your rebuttal must meet the same bar you set for
  the reviewer.
- **Fix the process that made the code, not just the code.** When a finding is
  real, prefer the change that stops the whole class of problem from coming
  back (the rule, template, or check that caused it) over patching one
  instance.

Ask for *actionable* findings: each one comes with a concrete fix or
resolution, ordered by severity. Observations that cannot become a fix only
make the list longer; they do not move the plan forward.

## Primary path: codex

```sh
# Model selection is owned by ~/.codex/config.toml — never pin -m here
# (a pinned model id rots when codex retires it and breaks every review).

# First review of a new plan:
codex exec --skip-git-repo-check \
  "このプランを批判的にレビューして。各指摘は具体的な修正・解決策とセットの actionable なものに絞って（直せない感想や瑣末な点で件数を増やさない）、致命的な点から優先して挙げて: {plan_full_path} (ref: {AGENTS.md full_path})"

# Reviewing an updated plan — keep prior context with `resume --last`:
codex exec resume --skip-git-repo-check --last \
  "プランを更新したから批判的にレビューして。各指摘は具体的な修正・解決策とセットの actionable なものに絞って（直せない感想や瑣末な点で件数を増やさない）、致命的な点から優先して挙げて: {plan_full_path} (ref: {AGENTS.md full_path})"
```

The reviewer model's knowledge can be out of date. To correct for that,
collect current docs and URLs into a temp file and pass its path in the
prompt.

## Fallback: independent subagent (when codex is unavailable)

Codex is unavailable when it hits a rate limit (for example "You've hit your
usage limit…") or any hard error. Then review the plan in a **separate context
window**. Never review it inline in the context that wrote it: that removes the
independence the review is for.

1. Spawn a fresh subagent with the Agent tool (`general-purpose`, or `Plan`
   for a read-only review). A fresh spawn does not remember writing the plan,
   which is the point. Do not use a fork of the conversation that wrote the
   plan.
2. Put these in its prompt, word for word: the plan's full path, the
   AGENTS.md full path as the ruleset reference, the three lenses above, and
   the same instruction you give codex ("actionable findings only, paired with
   concrete fixes, ordered by severity").
3. Treat its findings exactly like codex's: check each one (trust nothing)
   before you act on it.

## After the review

- Check every finding before you adopt it. Record which findings you adopted
  or rebutted, and what confirmed each, in the plan file itself or in the PR
  description.
- docs/handover.md holds session state; it is not a review log. Record a risk
  there only if it is still unresolved (the same line the GRIT rules draw).
