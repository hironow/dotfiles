<!--
  CLAUDE.md: the Claude Code overlay. The shared base for all tools is AGENTS.md,
  imported below. Put ONLY Claude-specific behavior here, so the two files never
  drift apart. Codex reads AGENTS.md and ignores this file; Claude Code reads
  both. Keep this file short for the same reason AGENTS.md is short.
-->

@AGENTS.md

# CLAUDE.md (Claude-specific overlay)

Everything in AGENTS.md applies. The rules below apply only to Claude Code.

## How to format answers

- Label each suggestion with its TDD phase: **[Red] / [Green] / [Refactor]**.
- When you propose code, **show the failing test first**, then the
  implementation.
- Give every Python suggestion type annotations.
- Write proposed commit messages as Conventional Commits. The type prefix
  already says whether a change is structural or behavioral, so never add
  `[STRUCTURAL]`/`[BEHAVIORAL]` tags (see docs/agents/commit-discipline.md).

## Plan review (before you show a plan to the human)

Every non-trivial implementation plan gets an independent review **before** you
show it. Never skip it, and never review it yourself in the context that wrote
it. Codex is the preferred reviewer. If Codex is unavailable, start an
independent subagent instead. Full steps, the three lenses, and commands:
docs/agents/plan-review.md.

## ASCII diagrams in answers

Use only single-byte ASCII inside a diagram; multi-byte characters break
monospace alignment. Always add a legend directly below it with Japanese
glosses (`English term: 日本語`), unless told otherwise. Full rules and a worked
example: docs/agents/ascii-diagrams.md.
