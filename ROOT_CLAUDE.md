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

## Plan review (before showing a plan to the human)

Every non-trivial implementation plan gets an independent second pair of eyes
**before** it is presented — never skipped, and never an inline self-review in
the authoring context. Codex is the preferred reviewer; if it is unavailable,
spawn an independent subagent instead. Full procedure, lenses, and commands:
docs/agents/plan-review.md.

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
