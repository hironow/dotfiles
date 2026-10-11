@AGENTS.md

# CLAUDE.md (Claude-specific overlay)

Everything in AGENTS.md applies. The rules below apply only to Claude Code.

## How to format answers

- Label each suggestion with its TDD phase: **[Red] / [Green] / [Refactor]**.
- When you propose code, **show the failing test first**, then the
  implementation.

## Plan review (before you show a plan to the human)

Every plan that changes behavior (code, config, dependencies, infrastructure, or
the rules in these instructions) gets an independent review **before** you show
it. A plan that only fixes typos, comments, or formatting needs none. Never skip a required review, and
never review a plan yourself in the context that wrote it. Codex is the preferred reviewer. If Codex is unavailable, start an
independent subagent instead. Full steps, the three lenses, and commands:
docs/agents/plan-review.md.

## ASCII diagrams in answers

Use only single-byte ASCII inside a diagram; multi-byte characters break
monospace alignment. Always add a legend directly below it with Japanese
glosses (`English term: 日本語`), unless told otherwise.
