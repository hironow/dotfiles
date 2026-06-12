# Plan review (codex first, independent subagent fallback)

Read this before presenting any non-trivial implementation plan to the human.
The plan must get an independent second pair of eyes **before** it is shown —
this review is never skipped. Root pointer is in CLAUDE.md.

## The three lenses (carry through the whole review)

- **何も信用しない — trust nothing.** Every claim is a hypothesis to verify —
  the reviewer's, the plan's, and your own. Don't act on a finding you haven't
  confirmed against the actual code, docs, or a live experiment.
- **Even the reviewers get reviewed.** The reviewer is fallible (stale
  knowledge, missing repo context); judge each finding on the evidence and
  push back when it's wrong. Your rebuttal must clear the same bar you hold
  the reviewer to.
- **Don't fix the code — fix the process that generates it.** When a finding
  is real, prefer the change that stops the whole class from recurring (the
  rule, template, or check that produced it) over patching the single instance.

Ask for findings phrased as *actionable* items — each paired with a concrete
fix or resolution, ordered by severity. A reviewer that surfaces observations
it can't turn into a fix just grows the list without moving the plan forward.

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

To counter the reviewer model's stale knowledge, gather current docs/URLs
into a temp file and pass its path in the prompt.

## Fallback: independent subagent (when codex is unavailable)

Codex counts as unavailable on a rate limit (e.g. "You've hit your usage
limit…") or any hard error. Then review the plan yourself in a **separate
context window** — never inline in the authoring context, which defeats the
independence the review exists for:

1. Spawn a fresh subagent with the Agent tool (`general-purpose`, or `Plan`
   for read-only review). A fresh spawn has no memory of authoring the plan —
   that is the point. Do not use a fork of the authoring conversation.
2. Hand it, verbatim in the prompt: the plan's full path, the AGENTS.md full
   path as the ruleset reference, the three lenses above, and the same
   instruction used for codex ("actionable findings only, paired with concrete
   fixes, ordered by severity").
3. Treat its findings exactly as you would codex's: verify each one
   (trust nothing) before acting on it.

## After the review

- Verify every finding before adopting it; record adopted/rebutted findings
  and what confirmed them in the plan file itself or the PR description.
- docs/handover.md is session state, not a review log — only record a risk
  there when it remains unresolved (same line the GRIT rules draw).
