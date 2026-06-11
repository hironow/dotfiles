<!--
  CLAUDE.md — Claude Code overlay. The shared, cross-tool base lives in AGENTS.md
  and is imported below. Put ONLY Claude-specific behavior here so the two files
  never drift. Codex reads AGENTS.md and ignores this file; Claude Code reads both.
  Keep this short for the same adherence-budget reason AGENTS.md is short.
-->

@AGENTS.md

# CLAUDE.md (Claude-specific overlay)

Everything in AGENTS.md applies. The items below are additional behaviors that
only make sense for Claude Code.

## Response format

- Always label which TDD phase a suggestion belongs to: **[Red] / [Green] /
  [Refactor]**.
- When proposing code, **show the failing test first**, then the implementation.
- All Python suggestions include type annotations.
- Propose commit messages in Conventional Commits form; the type prefix already
  encodes structural-vs-behavioral, so never add `[STRUCTURAL]`/`[BEHAVIORAL]`
  tags (see docs/agents/commit-discipline.md).

## Plan review with codex (before showing a plan to the human)

For any non-trivial implementation plan, run a codex review **before** presenting
it. Codex is the *preferred* reviewer, but the plan must always get an independent
second pair of eyes — so the review is never skipped. If codex is unavailable
(rate-limit — e.g. "You've hit your usage limit…" — or any hard error), review it
yourself in a **separate context window**: spawn a subagent whose context is
independent of the one that wrote the plan, hand it the same lenses below, and
treat its findings exactly as you would codex's. Never self-review inline in the
authoring context — that defeats the independence the review exists for.

Carry three lenses through the whole review:

- **何も信用しない — trust nothing.** Every claim is a hypothesis to verify —
  codex's, the plan's, and your own. Don't act on a finding you haven't confirmed.
- **Even the reviewers get reviewed.** codex is fallible (stale knowledge — see
  below); judge each finding on the evidence and push back when it's wrong. Your
  rebuttal must clear the same bar you hold codex to.
- **Don't fix the code — fix the process that generates it.** When a finding is
  real, prefer the change that stops the whole class from recurring (the rule,
  template, or check that produced it) over patching the single instance.

Ask for findings phrased as *actionable* items — each paired with a concrete fix
or resolution, ordered by severity. The point is to keep the finding list
bounded and clear: a reviewer that surfaces observations it can't turn into a fix
just grows the list without moving the plan forward.

```sh
# First review of a new plan:
codex exec -m gpt-5.5 --skip-git-repo-check \
  "このプランを批判的にレビューして。各指摘は具体的な修正・解決策とセットの actionable なものに絞って（直せない感想や瑣末な点で件数を増やさない）、致命的な点から優先して挙げて: {plan_full_path} (ref: {AGENTS.md full_path})"

# Reviewing an updated plan — keep prior context with `resume --last`:
codex exec resume --skip-git-repo-check --last -m gpt-5.5 \
  "プランを更新したから批判的にレビューして。各指摘は具体的な修正・解決策とセットの actionable なものに絞って（直せない感想や瑣末な点で件数を増やさない）、致命的な点から優先して挙げて: {plan_full_path} (ref: {AGENTS.md full_path})"
```

To counter the reviewer model's stale knowledge, gather current docs/URLs into a
temp file and pass its path in the prompt.

## ASCII diagrams in responses

- Use **single-byte ASCII only** inside diagrams — no Japanese/Chinese/Korean/
  emoji (multi-byte chars break monospace alignment).
- Always add a legend directly below, with Japanese glosses unless told
  otherwise (`English term: 日本語`).

```
+-------------------+
|  Request Handler  |
+-------------------+
         |
         v
+-------------------+
|     Validator     |
+-------------------+

Legend / 凡例:
- Request Handler: リクエストハンドラー
- Validator: バリデーター
```

## Hook awareness

`.claude/settings.json` enforces the non-negotiables mechanically. If a hook
blocks an action (exit 2 with a reason), do not try to route around it — the
block is policy. Read the reason and change approach (e.g. switch `npm` → `bun`,
`.yml` → `.yaml`, or open an IaC PR instead of a manual `gcloud` mutation).

## Never (Claude-specific reminders; the rest are in AGENTS.md)

- Never suggest untested code for production, or skip the failing-test step.
- Never mix structural and behavioral changes in one suggestion.
- Never create or update `docs/intent.md` with guessed intent — ask the human
  first.
- Never suggest editing the ruff/mypy/semgrep configuration to make a check pass.
