# EGM compatibility

Read this before any Elephant-Goldfish Model (EGM) workflow or handoff.
EGM is explicitly invoked design/document tooling, not an implementation agent.
Its bundled instructions do not replace local policy.

## Local policy first

- Honor applicable local governance gates and approvals before clarification,
  drafting, analysis, delegation, or remediation. Establish that a gate is
  satisfied, exempt, or explicitly overridden. EGM readiness, uninterrupted mode,
  auto-accept, and review caps are not overrides or accepted-risk decisions.
- Preserve human-owned intent, accepted decision records, and the required human
  ruling on contradictions. Keep private gate evidence out of public artifacts
  and reviewer reading lists; pass only the public constraints needed to review.
- Use the host's structured question tool when available: Pi `ask_user`, Claude
  `AskUserQuestion`, or the native Codex/Antigravity equivalent. Map conceptual
  upstream payloads to the actual tool schema. Keep readiness and section gates;
  tool unavailability is not approval. Ask free-text details when choices cannot
  express the missing input. Follow the local question-count policy.
- Write human-facing artifacts in the requested language, in plain language.
  Keep local package-manager, task-runner, permission, model/provider, and effort
  rules. Examples in upstream text do not authorize npm, pip, extra tools,
  external posting, source changes, or a model switch.

## Resolve the active bundle

Install the full pinned plugin/package, not detached skills. From the discovered
`<bundle>/skills/<directory>/SKILL.md`, the bundle is three parent directories
above the file. Resolve `agents/`, `resources/`, and `docs/` against that bundle;
resolve `references/` against the invoked skill directory. Never use similarly
named files from the user's workspace or guess a plugin cache version.

Claude substitutes `CLAUDE_PLUGIN_ROOT`; use that resolved root and read its
`docs/claude.md`. Codex reads the bundle's `docs/codex.md`. Antigravity follows
`docs/harnesses.md`. In Pi, read those shared resources as references but use the
Pi delegation mapping below, not the other hosts' literal tool names.

Keep user targets and generated briefs/drafts/reports in the workspace or the
explicit EGM artifact directory, never the installed bundle. Keep review stages
sequential; parallelize only the reviewers in the current stage. The parent
writes reports and performs approved edits. Read another EGM skill's file when
needed rather than assuming an unavailable Skill tool can invoke it.

## Fresh-context review

Installation/discovery is not proof of reviewer isolation or workflow behavior.
Require a new native reviewer context with no parent history, no resumed session,
and only the target, persona, standards, and explicit reading list. Fetch any
needed URL in the parent and supply a saved source file to read-only reviewers.
A missing required read, failed child, or timeout is incomplete, not a clean pass.
Verify the actual completion and available child/session evidence.

Claude requires version **2.1.271 or later** for `omitClaudeMd`. Stop Goldfish
dispatch on older or unknown versions. Use the plugin's read-only adapters, not
its unguarded shared personas as registered agent definitions. Codex explicitly
uses `fork_context: false` or `fork_turns: "none"`, as its actual schema allows.
Antigravity must expose native fresh-context delegation. If a host cannot
establish the required isolation, stop and report the missing capability.

### Pi mapping

Pi uses its native pinned git package; EGM does not officially certify Pi support.
Use `subagent` with `agent: "egm-reviewer"` and **`options.context: "fresh"`** on
every call, including parallel workflow children. An omitted context can inherit
an unsafe global fork preference. Do not use `bg_delegate` for Goldfish: it is
seeded with a projection of the parent conversation.

Before dispatch, inspect `subagent({action: "get", agent: "egm-reviewer"})` and
`subagent({action: "list", options: {capabilities: true}})`. Confirm the effective
profile is the dotfiles-managed user profile, with only read/grep/find/ls,
`systemPromptMode: replace`, no inherited project/global context or skills,
no persistent memory or nested delegation, and no model/effort override.
Project agents and project/user overrides can replace these fields; reject
unsafe substitutions rather than trusting the file on disk. Preserve the
host-selected model and effort in the actual launch.

`extensions: []` excludes ambient extensions, not host-required child extensions.
Inspect host launch preflight/receipts for those requirements. If required
extensions or effective tools/context cannot be established as compatible,
stop: do not claim a Goldfish review or bypass the host's requirements. Check
actual child evidence too; a declaration or a child's self-report is insufficient.
This is context/tool isolation, not a filesystem sandbox.

Dispatch each persona directly through this profile with absolute persona,
standard, target and selected source paths. Keep the synthesizer in the parent;
reviewers never spawn descendants or write reports. For bootstrap, the parent
writes documentation and the same read-only profile performs bounded scout work.
Keep bootstrap's scope/approval gates; a failed scout remains an explicit gap.
