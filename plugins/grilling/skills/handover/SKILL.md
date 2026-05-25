---
name: handover
description: Compact the current work session into docs/handover.md so the next actor (a fresh agent, a teammate, or future you) can pick up fast. Draft it from the conversation, show it, and write only after confirmation. Unlike an ephemeral temp-dir handoff, this persists the handover into the project repo (docs/handover.md), committed alongside the code. Use at the end of a work session, when the user says "handover", "write the handover", "引き継ぎを書いて", "ハンドオーバー", or wants the session state captured in docs/handover.md.
argument-hint: "What will the next session focus on?"
---

Compact the current work session into a handover document recorded at `docs/handover.md`,
so the next actor — a fresh agent, a teammate, or your future self — can continue with
minimal ramp-up. Optimize it to be read in under two minutes.

## Where it goes

- Target: `docs/handover.md` at the root of the current project repository. Confirm the
  repository / path first, and create `docs/` if it does not exist. If the session is not
  inside a project repo, ask the user where to write it (fallback: the OS temp directory).

## Rules

- Draft the full document, show it to the user, and write the file only after they confirm.
  If `docs/handover.md` already exists, this is a session-level update: summarise what
  changes before overwriting. Prior versions live in git history, not in the file.
- Do NOT duplicate content already captured elsewhere (intent.md, PRDs, plans, ADRs, issues,
  commits, diffs). Reference it by path or URL instead. Do not restate the intent — if
  `docs/intent.md` exists, reference it rather than repeating the goal.
- Redact sensitive information (API keys, passwords, PII) before writing.
- If the user passed arguments, treat them as a description of what the next session will
  focus on, and tailor "Next Actions" accordingly.
- For **Updated by**, use the human's name only if you reliably know it; otherwise use the
  agent / session id. Never fabricate a name.

## Structure

Write for both humans and AI agents, using this format:

```markdown
# Handover

**Last updated:** YYYY-MM-DD HH:MM (timezone)
**Updated by:** {human name or AI session id}

## Current State
{What is done. One paragraph.}

## In Progress
{What is actively being worked on. Include branch name, PR link, issue id.}

## Next Actions
1. {Concrete next step — include any skills the next actor should invoke}
2. {...}

## Known Risks / Blockers
- {Item and mitigation}

## Context the Next Actor Needs
- {Non-obvious gotchas, environment quirks, external dependencies}

## Relevant Files and Commands
- `path/to/file` - {why it matters}
- `just {command}` - {what it does}
```
