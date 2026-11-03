# Hook contracts per harness (snapshot)

**Date:** 2026-11-03
**Status:** snapshot for [the agent-hook plan](agent-hooks-go.md). Sections 1–6 and the rtk table come from a Codex research run with pinned sources. The agy section ends with this repo's own probe records.

Audit cutoff: **2026-11-03**. “Latest” includes published prereleases, identified below. `?` means optional; `J` means arbitrary JSON. Code links pin the repository, release/commit, file and line range.

## 1. Claude Code

**Version and sources.** Latest release: [v2.1.317, November 3](https://github.com/anthropics/claude-code/releases/tag/v2.1.317). Closed source; findings come from the current official [hooks reference](https://code.claude.com/docs/en/hooks), [guide](https://code.claude.com/docs/en/hooks-guide) and [SDK types](https://code.claude.com/docs/en/agent-sdk/typescript). Those pages are not release-pinned.

**Hook/plugin registration.** Settings locations: `~/.claude/settings.json`, `.claude/settings.json`, `.claude/settings.local.json`, managed settings; enabled plugins contribute `hooks/hooks.json`. Format: `hooks.<Event>[].{matcher?,hooks:[{type:"command",command,...}]}`. Managed policy can restrict enabled hooks. [Registration reference](https://code.claude.com/docs/en/hooks#hook-locations)

**Pre-tool input.** Required strings: `session_id,transcript_path,cwd,hook_event_name,tool_name,tool_use_id`; `tool_input:J`. Optional: `prompt_id,permission_mode,agent_id,agent_type,scratchpad_dir:string`, `effort:{level:string}`, `mcp_server:object`. The SDK types omit the documented `scratchpad_dir`. [Common fields](https://code.claude.com/docs/en/hooks#common-input-fields), [typed envelope](https://code.claude.com/docs/en/agent-sdk/typescript#basehookinput)

| Tool | `tool_input` |
|---|---|
| `Bash` | `{command:string,timeout?:number,description?:string,run_in_background?:boolean,dangerouslyDisableSandbox?:boolean}` |
| `Write` | `{file_path:string,content:string}` |
| `Edit` | `{file_path:string,old_string:string,new_string:string,replace_all?:boolean}` |
| `NotebookEdit` | `{notebook_path:string,new_source:string,cell_id?:string,cell_type?:"code"\|"markdown",edit_mode?:"replace"\|"insert"\|"delete"}` |

These are the official [tool input types](https://code.claude.com/docs/en/agent-sdk/typescript#tool-input-types). `Write/Edit` paths are normalized to absolute native paths before hooks. No current official `MultiEdit` input definition was found.

**Post-tool input.** Successful `PostToolUse`: common envelope plus tool identifiers/input, `tool_response:J`, `duration_ms?:number`. `PostToolUseFailure` exists: replaces the response with `error:string`, `is_interrupt?:boolean`, retaining optional duration. Responses are tool-specific. [Typed post events](https://code.claude.com/docs/en/agent-sdk/typescript#posttoolusehookinput)

**Answer contract.** Pre decisions belong in `hookSpecificOutput`, with matching `hookEventName`: `permissionDecision:"allow"|"deny"|"ask"|"defer"`, optional reason, `updatedInput:object`, `additionalContext:string`. `updatedInput` replaces the entire input; defer ignores it. Allow remains subject to permission restrictions. Post supports top-level `decision:"block",reason`, nested context and output replacement; failure supports additional context. Universal `continue:false` stops processing; `suppressOutput` is accepted but ineffective. [Decision contract](https://code.claude.com/docs/en/hooks#pretooluse-decision-control), [SDK return contract](https://code.claude.com/docs/en/agent-sdk/hooks#outputs)

**Failure behavior.** Exit 0 applies valid JSON; exit 2 blocks pre-execution regardless of an accompanying allow. Post exit 2 supplies feedback after execution. Other exits can still apply valid JSON; otherwise failures normally continue. `onFailure:"block"` changes missing-command, timeout and malformed-output handling. Windows without Git Bash has an additional default blocking exception. Command timeout defaults to **600 seconds**. Matching hooks run concurrently; restrictive decisions win, while competing rewrites have no guaranteed winner. [Exit/failure reference](https://code.claude.com/docs/en/hooks#exit-code-output), [concurrency and limits](https://code.claude.com/docs/en/hooks-guide#how-hooks-work)

**Official JSON Schema.** None found for wire input/output. [SchemaStore’s settings schema](https://json.schemastore.org/claude-code-settings.json) describes registration, not hook payloads.

**Differences/open questions.** Current contracts include defer, output replacement and configurable failure blocking. `MultiEdit` support could not be confirmed; absence from documentation is not proof of removal.

## 2. Codex

**Version and sources.** Latest published release: [rust-v0.167.0-alpha.4, November 3](https://github.com/openai/codex/releases/tag/rust-v0.167.0-alpha.4), SHA `fb036d4ebd89f263d34a1f888c279ce85bb383c6`. Latest stable is 0.166.0, October 29. The hooks crate is identical between them. Official [hooks documentation](https://learn.chatgpt.com/docs/hooks).

**Hook/plugin registration.** User `~/.codex/hooks.json`; trusted-project `.codex/hooks.json`, following enabled config layers. Inline TOML hooks also accumulate. Active plugins contribute manifest-defined hooks or default `hooks/hooks.json`. [`discovery.rs:145–231`](https://github.com/openai/codex/blob/rust-v0.167.0-alpha.4/codex-rs/hooks/src/engine/discovery.rs#L145-L231), [`loader.rs:1221–1277`](https://github.com/openai/codex/blob/rust-v0.167.0-alpha.4/codex-rs/core-plugins/src/loader.rs#L1221-L1277)

`hooks.state` is a **TOML table**, containing per-hook `enabled?`, `trusted_hash?`, `trusted_content_hash?`. Untrusted/changed non-managed hooks are skipped; plugin content is rechecked before execution. [`hook_config.rs:21–37`](https://github.com/openai/codex/blob/rust-v0.167.0-alpha.4/codex-rs/config/src/hook_config.rs#L21-L37), [`discovery.rs:836–940`](https://github.com/openai/codex/blob/rust-v0.167.0-alpha.4/codex-rs/hooks/src/engine/discovery.rs#L836-L940)

**Pre-tool input.** Required strings: `session_id,turn_id,cwd,hook_event_name,model,permission_mode,tool_name,tool_use_id`; `transcript_path:string|null`, `tool_input:J`; optional `agent_id,agent_type:string`. Verified at the [producer](https://github.com/openai/codex/blob/rust-v0.167.0-alpha.4/codex-rs/core/src/hook_runtime.rs#L196-L235) and [serializer, `pre_tool_use.rs:181–196`](https://github.com/openai/codex/blob/rust-v0.167.0-alpha.4/codex-rs/hooks/src/events/pre_tool_use.rs#L181-L196).

- Native `exec_command` projects to **`Bash {command:string}`**, using native `cmd`; other native arguments disappear. [`exec_command.rs:336–346`](https://github.com/openai/codex/blob/rust-v0.167.0-alpha.4/codex-rs/core/src/tools/handlers/unified_exec/exec_command.rs#L336-L346)
- `apply_patch` projects to **`apply_patch {command:string}`**, containing raw patch text. `Edit/Write` are matcher aliases. No notebook-specific contract was confirmed. [`apply_patch.rs:370–418`](https://github.com/openai/codex/blob/rust-v0.167.0-alpha.4/codex-rs/core/src/tools/handlers/apply_patch.rs#L370-L418), [`hook_names.rs:28–55`](https://github.com/openai/codex/blob/rust-v0.167.0-alpha.4/codex-rs/core/src/tools/hook_names.rs#L28-L55)

**Post-tool input.** Same envelope plus `tool_response:J`; no common success/error flag. Shell and patch currently produce strings. Completed shell commands can trigger post-hooks despite nonzero subprocess exit; handler failures do not. No `PostToolUseFailure` event was found. [`schema.rs:321–342`](https://github.com/openai/codex/blob/rust-v0.167.0-alpha.4/codex-rs/hooks/src/schema.rs#L321-L342), [`context.rs:441–490`](https://github.com/openai/codex/blob/rust-v0.167.0-alpha.4/codex-rs/core/src/tools/context.rs#L441-L490), [`registry.rs:938–971`](https://github.com/openai/codex/blob/rust-v0.167.0-alpha.4/codex-rs/core/src/tools/registry.rs#L938-L971)

**Answer contract.** Empty output/`{}` passes. Pre deny requires a nonempty reason. Rewrite requires **allow plus `updatedInput`**; bare allow does not approve execution. Shell/patch replacements require `command:string`. Pre ask, legacy approve and stop controls are unsupported. Post accepts block/reason, stop controls, context and system messages; output replacement is unsupported. [`output_parser.rs:121–238`](https://github.com/openai/codex/blob/rust-v0.167.0-alpha.4/codex-rs/hooks/src/engine/output_parser.rs#L121-L238), [`369–510`](https://github.com/openai/codex/blob/rust-v0.167.0-alpha.4/codex-rs/hooks/src/engine/output_parser.rs#L369-L510)

**Failure behavior.** Exit 2 blocks **only with nonempty stderr**. Other nonzero exits, missing commands, timeout, malformed/unknown JSON fields fail open. Invalid accepted rewrites instead fail at the tool adapter. Default pre/post timeout: **600 seconds**. Parallel hooks share input; block wins, otherwise last-completed rewrite wins. [`pre_tool_use.rs:119–298`](https://github.com/openai/codex/blob/rust-v0.167.0-alpha.4/codex-rs/hooks/src/events/pre_tool_use.rs#L119-L298), [`registry.rs:1086–1127`](https://github.com/openai/codex/blob/rust-v0.167.0-alpha.4/codex-rs/core/src/tools/registry.rs#L1086-L1127), [`discovery.rs:946–968`](https://github.com/openai/codex/blob/rust-v0.167.0-alpha.4/codex-rs/hooks/src/engine/discovery.rs#L946-L968)

Windows uses the selected shell: PowerShell gets `-NoProfile -Command`; fallback can be `%COMSPEC%`/`cmd.exe /C`. It is not universally `pwsh`. [`command_runner.rs:444–521`](https://github.com/openai/codex/blob/rust-v0.167.0-alpha.4/codex-rs/hooks/src/engine/command_runner.rs#L444-L521)

**Official JSON Schema.** Found: [pre input](https://github.com/openai/codex/blob/rust-v0.167.0-alpha.4/codex-rs/hooks/schema/generated/pre-tool-use.command.input.schema.json), [pre output](https://github.com/openai/codex/blob/rust-v0.167.0-alpha.4/codex-rs/hooks/schema/generated/pre-tool-use.command.output.schema.json), [post input](https://github.com/openai/codex/blob/rust-v0.167.0-alpha.4/codex-rs/hooks/schema/generated/post-tool-use.command.input.schema.json), [post output](https://github.com/openai/codex/blob/rust-v0.167.0-alpha.4/codex-rs/hooks/schema/generated/post-tool-use.command.output.schema.json).

**Differences/open questions.** Schema-valid values can be runtime-unsupported. Hook parsing failures and rewrite-validation failures have different execution consequences.

## 3. Antigravity CLI `agy`

**Version and sources.** Installed **1.4.12**, checked November 3. The public [CLI changelog](https://antigravity.google/docs/changelog/) labels 1.4.10, October 29, latest; latest available version therefore remains unconfirmed. Sources: official [hooks](https://antigravity.google/docs/hooks), [plugins](https://antigravity.google/docs/plugins), bundled hooks.md:137–250 (bundled `~/.gemini/antigravity-cli/builtin/skills/agy-customizations/docs/hooks.md`).

**Hook/plugin registration.** Project `.agents/hooks.json`, global `~/.gemini/config/hooks.json`, plugin-root `hooks.json`. Top-level keys are **named hook definitions**, containing enabled flags and event arrays. Pre/post use matcher groups. Bundled documentation says hooks run sequentially. Plugin configuration enablement overrides manifest disabling. Bundled registration:8–133 (bundled `~/.gemini/antigravity-cli/builtin/skills/agy-customizations/docs/hooks.md`), plugin enablement:86–112 (bundled `~/.gemini/antigravity-cli/builtin/skills/agy-customizations/docs/plugins.md`)

**Pre-tool input.** Documented camelCase fields: `conversationId,transcriptPath,artifactDirectoryPath,modelName:string`, `workspacePaths:string[]`; bundled examples also contain `lastUserInput:string`. Event fields: `toolCall:{name:string,args:object}`, `stepIdx:integer`. Examples do not establish every field’s requiredness.

Public tool vocabulary includes `run_command`, **`write_to_file`**, **`replace_file_content`**, **`multi_replace_file_content`**. Complete typed argument schemas were not found. The probed `write_file {Path,Content}`, `edit_file {Path,Target,Replacement}` and `toolSummary` remain probe evidence, not documentation-confirmed contracts. [Public tool reference](https://antigravity.google/docs/hooks#supported-tools)

**Post-tool input.** Common metadata, tool call and step index, plus `error?:string`; no documented response body. Expected hook output is `{}`. Bundled post contract:230–250 (bundled `~/.gemini/antigravity-cli/builtin/skills/agy-customizations/docs/hooks.md`)

**Answer contract.** Required `decision`: bundled `allow|deny|ask|force_ask`; public docs additionally list `deny_unless_prior_grant`. Optional `reason:string`, `permissionOverrides:string[]`, `overwrite:object`. Overwrite shallow-merges arguments. Bundled answer contract:189–226 (bundled `~/.gemini/antigravity-cli/builtin/skills/agy-customizations/docs/hooks.md`)

**Failure behavior.** Documented execution: Unix `sh -c`, Windows `cmd /c`, cwd containing `hooks.json`, default timeout **30 seconds**. Exact nonzero, timeout, malformed-output and missing-command consequences are undocumented. Handler configuration:123–133 (bundled `~/.gemini/antigravity-cli/builtin/skills/agy-customizations/docs/hooks.md`)

**Official JSON Schema.** None found; “Schema and file format” is prose.

**Differences/open questions.** Docs say allow auto-permits and ask prompts, conflicting with the probes below. `{}` violates the documented required decision, but default-deny behavior is unconfirmed. Nonzero/timeout blocking remains probe-only. Public multi-edit names cannot safely be substituted for installed CLI wire names.

### agy 1.4.12 probe records (2026-11-03, a scratch workspace with a project `.agents/hooks.json`, `agy -p`)

- Hook tool names and args (from the hook's own stdin): `run_command` {CommandLine, WaitMsBeforeAsync, toolSummary}; `write_file` {Path, Content}; `edit_file` {Path, Target, Replacement}. Plain string values. (Not `write_to_file` / `replace_file_content`; no multi-edit tool observed.)
- Neutral answer: `{"decision":"ask"}` gave the same outcome as no hook in every observed cell — auto mode: allow-listed `ls`, auto-safe `echo` and `touch`, file write, file edit all ran; accept-edits mode: allow-listed command ran, approval-required `echo` auto-denied in headless mode, as without a hook. Empty stdout behaved the same but is undocumented. `{}` is a deny (no reason).
- Failures: exit 1, exit 2, and a timeout each BLOCK the tool call (fail closed), with the error and stderr shown to the model. A `deny` reason reaches the model verbatim.
- rtk: `overwrite` applies with `ask`, but the rewrite changes behavior two ways: (1) agy's command sandbox cannot execute `rtk` (exit 127, "operation not permitted: rtk"), so `ls -la` fails as `rtk ls -la`; (2) in accept-edits mode the rewritten `rtk git status` no longer matches the allow rule `command(git status)`, so an allowed command is auto-denied. rtk therefore fails the shipping condition for agy.
- Side finding (not hooks): in agy, git fails outside the dotfiles workspace because the sandbox cannot read `~/dotfiles/config/git/shared.gitconfig`, which `~/.gitconfig` includes.
- Not observed: interactive prompts and "Always allow" in the TUI; a permissions deny rule (agy shows no such setting).

### rtk on agy (2026-11-03; rtk's official docs are rtk-ai/rtk `develop`; v1.1.0, the latest stable, installed)

- Official integration: `rtk init -g --agent antigravity` writes a plugin `~/.gemini/config/plugins/rtk/` (`plugin.json`, `hooks.json` = `rtk-rewrite` → PreToolUse `run_command` → `rtk hook antigravity`, timeout 10, plus `rules/AGENTS.md`). The hook answers `{"decision":"allow"}` for pass-through and for rewrites (`src/hooks/hook_cmd.rs:482-549`, develop 2026-11-02).
- Official permission note (`hooks/antigravity/README.md`): "Antigravity evaluates its tool permissions after lifecycle hooks rewrite commands. If you maintain strict command allowlists, ensure permitted commands account for rtk (e.g. `command(rtk git status)` or `command(rtk *)`)." Measured: hook `allow` does not bypass agy's evaluation (accept-edits, headless: `echo` stays auto-denied with rtk's raw `allow`); an allow-listed `git status` becomes auto-denied as `rtk git status`. `command(rtk *)` would approve rewritten commands whose original is not allowed (against ADR 0047); a per-rule twin `command(rtk X)` for each `command(X)` keeps parity.
- Sandbox (official docs gap): agy's auto mode turns the Seatbelt terminal sandbox on; rtk's install dir (`~/.local/share/mise/installs/rtk/...`) is not mounted, so `rtk ...` fails with exit 127. Measured: adding `read_file(~/.local/share/mise/installs/rtk)` (session-only `--settings`) makes `rtk ls -la` run. rtk's docs do not mention this.
- `permissionOverrides: ["command(rtk git status)"]` in the hook answer did not avoid the auto-deny.
- Not settled: in auto mode, whether agy's risk classifier treats `rtk git push` (rtk rewrites git push, git commit, curl) the same as `git push`; the headless probe ended earlier on a `read_file` request in both cases.
- rtk doc drift: `docs/guide/resources/agent-coverage.md` (2026-10-13) calls Antigravity "rules file only, installs no hook", while `src/hooks/init/antigravity.rs` (2026-10-23) installs the hook.

## 4. Pi

**Version and sources.** Latest [earendil-works/pi v1.5.0, November 2](https://github.com/earendil-works/pi/releases/tag/v1.5.0); installed 1.4.0 is older.

**Hook/plugin registration.** In-process extensions register `pi.on("tool_call"|"tool_result",handler)`. Sources include user `~/.pi/agent/extensions/`, trusted-project `.pi/extensions/`, settings/packages and CLI `-e`. Files, directory entrypoints and package declarations work; symlinks are followed. [`package-manager.ts:586–667`](https://github.com/earendil-works/pi/blob/v1.5.0/packages/coding-agent/src/core/package-manager.ts#L586-L667), [`resource-loader.ts:533–557`](https://github.com/earendil-works/pi/blob/v1.5.0/packages/coding-agent/src/core/resource-loader.ts#L533-L557)

**Pre-tool input.** JS event: `{type:"tool_call",toolName:string,toolCallId:string,parentToolCallId?:string,input:object}`. [Producer, `agent-session.ts:673–696`](https://github.com/earendil-works/pi/blob/v1.5.0/packages/coding-agent/src/core/agent-session.ts#L673-L696)

- [`bash`](https://github.com/earendil-works/pi/blob/v1.5.0/packages/coding-agent/src/core/tools/bash.ts#L39-L49)/[`powershell`](https://github.com/earendil-works/pi/blob/v1.5.0/packages/coding-agent/src/core/tools/powershell.ts#L23-L40): `{command:string,timeout?:number}`; seconds.
- [`write`](https://github.com/earendil-works/pi/blob/v1.5.0/packages/coding-agent/src/core/tools/write.ts#L10-L20): `{path:string,content:string}`.
- [`edit`](https://github.com/earendil-works/pi/blob/v1.5.0/packages/coding-agent/src/core/tools/edit.ts#L20-L50): `{path:string,edits:{oldText:string,newText:string}[]}`.

No core patch/notebook tool exists in the [builtin inventory:95–105](https://github.com/earendil-works/pi/blob/v1.5.0/packages/coding-agent/src/core/tools/index.ts#L95-L105).

**Post-tool input.** Same identifiers/input, type `tool_result`, plus text/image `content[]`, tool-specific `details`, `structuredContent?:J`, `isError:boolean`, `usage?:Usage`. [Producer:699–739](https://github.com/earendil-works/pi/blob/v1.5.0/packages/coding-agent/src/core/agent-session.ts#L699-L739)

**Answer contract.** Pre returns `{block?:boolean,reason?:string,terminate?:boolean}` or nothing. First block wins. Rewrite by mutating `event.input` in place; later handlers see it, without revalidation. Post returns partial result replacements. Termination requires a blocked call and batch-level agreement. [Return consumer, `runner.ts:1190–1267`](https://github.com/earendil-works/pi/blob/v1.5.0/packages/coding-agent/src/core/extensions/runner.ts#L1190-L1267), [`agent-loop.ts:735–785`](https://github.com/earendil-works/pi/blob/v1.5.0/packages/agent/src/agent-loop.ts#L735-L785)

**Failure behavior.** Pre throw prevents execution; post throw reports an extension error and continues. Handlers are awaited sequentially in extension/registration order; no dispatch timeout, so hangs stall. Broken extension loads are recorded/skipped. Exit/stdout protocols do not apply. [Dispatcher](https://github.com/earendil-works/pi/blob/v1.5.0/packages/coding-agent/src/core/extensions/runner.ts#L1190-L1267), [loader:638–706](https://github.com/earendil-works/pi/blob/v1.5.0/packages/coding-agent/src/core/extensions/loader.ts#L638-L706)

**Official JSON Schema.** None found for events/results; official TypeScript types and TypeBox tool schemas exist.

**Differences/open questions.** Latest edit uses `edits[]`; legacy flat fields are normalized before hook delivery. Native extensions need a separately defined subprocess bridge for a Go engine.

## 5. OpenCode v2

**Version and sources.** Current home **anomalyco/opencode**; latest v2 [v2.2.5, October 30](https://github.com/anomalyco/opencode/releases/tag/v2.2.5). Installed 2.0.29 is older. Official [v2 plugin docs](https://opencode.ai/v2/docs/build/plugins/).

**Hook/plugin registration.** `Plugin.define({id,setup(ctx)})`; `ctx.tool.hook("execute.before"|"execute.after",callback)`. Auto-loads `plugin/` and `plugins/` under global config and project `.opencode` roots, including symlink targets. Default global root is `~/.config/opencode`, with overrides. No hash-trust mechanism found in this path. [`source-directory.ts:7–32`](https://github.com/anomalyco/opencode/blob/v2.2.5/packages/core/src/plugin/source-directory.ts#L7-L32), [`discovery.ts:59–144`](https://github.com/anomalyco/opencode/blob/v2.2.5/packages/core/src/config/discovery.ts#L59-L144)

**Pre-tool input.** `{tool:string,sessionID:string,agent:string,messageID:string,id:string,input:unknown}`. [Producer, `tool.ts:121–129`](https://github.com/anomalyco/opencode/blob/v2.2.5/packages/core/src/tool.ts#L121-L129)

| Tool | Input |
|---|---|
| [`shell`](https://github.com/anomalyco/opencode/blob/v2.2.5/packages/core/src/tool/plugin/shell.ts#L21-L59) | `{command:string,workdir?:string,timeout?:nonnegative integer,background?:boolean}`; milliseconds |
| [`write`](https://github.com/anomalyco/opencode/blob/v2.2.5/packages/core/src/tool/plugin/write.ts#L20-L28) | `{path:string,content:string}` |
| [`edit`](https://github.com/anomalyco/opencode/blob/v2.2.5/packages/core/src/tool/plugin/edit.ts#L22-L34) | `{path:string,oldString:string,newString:string,replaceAll?:boolean}` |
| [`patch`](https://github.com/anomalyco/opencode/blob/v2.2.5/packages/core/src/tool/plugin/patch.ts#L19-L25) | `{patchText:string}` |

No builtin notebook editor was found.

**Post-tool input.** Same envelope plus either `status:"completed",result:{output?:unknown,content?:string|Content[],metadata?:Metadata}` or `status:"error",error:Tool.Error`. [Producer/consumer:131–173](https://github.com/anomalyco/opencode/blob/v2.2.5/packages/core/src/tool.ts#L131-L173), [error types:61–89](https://github.com/anomalyco/opencode/blob/v2.2.5/packages/schema/src/tool.ts#L61-L89)

**Answer contract.** Callback returns void. Mutate `event.tool/input` to rewrite; throw/reject to block. Rewritten input is validated against the selected tool. Successful post results can be replaced. No block/decision/stdout JSON protocol is consumed. [`tool.ts:316–336`](https://github.com/anomalyco/opencode/blob/v2.2.5/packages/core/src/tool.ts#L316-L336), [`runtime.ts:29–84`](https://github.com/anomalyco/opencode/blob/v2.2.5/packages/core/src/tool/runtime.ts#L29-L84)

**Failure behavior.** Sequential registration order; no hook-specific timeout. Before rejection prevents execution and produces no after event. After rejection propagates as an Effect defect; fail-open handling is not established. [`hooks.ts:69–95`](https://github.com/anomalyco/opencode/blob/v2.2.5/packages/core/src/plugin/hooks.ts#L69-L95), [`adapter.ts:680–690`](https://github.com/anomalyco/opencode/blob/v2.2.5/packages/plugin/src/promise/adapter.ts#L680-L690)

**Official JSON Schema.** None found for hook events. [Configuration schema](https://opencode.ai/config.json) is separate.

**Differences/open questions.** Confirmed v2 `execute.before`; v1 `tool.execute.before` is a different API. A Go subprocess bridge must define its own serialization.

## 6. dsh — DeepSeek Harness

**Version and sources.** Confidently identified as [deepseek-ai/deepseek-harness](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.2-alpha.3/README.md#L1-L9). Latest observed release: [dsh-v0.2.2-alpha.3, November 3](https://github.com/deepseek-ai/deepseek-harness/releases/tag/dsh-v0.2.2-alpha.3), SHA `05b1cae8db6e674c5685101494d4eec24652424a`.

**Hook/plugin registration.** Native Cordis events include `tools/pre-execute` and `tools/post-execute`. Profiles configure bundles under `$DSH_HOME/profiles/<name>`. Optional Claude/Codex command bridges require explicit `configPath`; they do not reproduce upstream discovery/trust. [`profile.ts:160–171`](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.2-alpha.3/packages/boot/app-boot/src/profile.ts#L160-L171), [bridge registration:49–120](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.2-alpha.3/packages/experimental/hooks-claude-code/src/index.ts#L49-L120)

**Pre-tool input.** Native execution includes readonly IDs, `name`, frozen JSON `arguments`, agent/toolset objects, opaque tokens and `AbortSignal`; it is not a JSON wire contract. [Native producer:120–158](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.2-alpha.3/packages/core/tools/src/pipeline.ts#L120-L158)

Claude bridge sends `session_id,cwd,hook_event_name,tool_name,tool_use_id:string`, `transcript_path:""`, full `tool_input`. Codex bridge adds `turn_id,model`, fixed `permission_mode:"default"`, null transcript; **reduces every input to `{command:string}`**, empty for non-shell tools. Native tool names remain unchanged. [Claude producer:327–347](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.2-alpha.3/packages/experimental/hooks-claude-code/src/index.ts#L327-L347), [Codex producer:291–327](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.2-alpha.3/packages/experimental/hooks-codex/src/index.ts#L291-L327)

Native tool schemas:

- [`bash`](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.2-alpha.3/packages/shell/tool-bash/src/index.ts#L367-L402)/[`pwsh`](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.2-alpha.3/packages/shell/tool-pwsh/src/index.ts#L384-L419): required `description,command:string`; optional `timeoutMs:number,workdir:string`.
- [`write`](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.2-alpha.3/packages/fs/tool-fs/src/write.ts#L73-L84): `{file_path:string,content:string}`.
- [`edit`](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.2-alpha.3/packages/fs/tool-fs/src/edit.ts#L85-L98): `{file_path,old_string,new_string:string,replace_all?:boolean}`.
- [`apply_patch`](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.2-alpha.3/packages/fs/tool-fs/src/apply-patch.ts#L26-L39): `{input:string}`.
- [`str_replace_editor`](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.2-alpha.3/packages/fs/tool-str-replace-editor/src/index.ts#L427-L467): command/path plus command-specific nullable text, line and range fields.

Composition can add background/sandbox fields. No notebook contract was identified.

**Post-tool input.** Native result discriminates `isError`, carrying JSON value/content or structured error. Both command bridges flatten content to `tool_response:string`, without an error flag. [Native result:270–346](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.2-alpha.3/packages/core/tools/src/contracts.ts#L270-L346)

**Answer contract.** Native pre supports allow/deny/ask/cancel, without rewriting frozen input; post supports accept/replacement or blocking feedback. [Types:348–370](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.2-alpha.3/packages/core/tools/src/contracts.ts#L348-L370), [consumers:190–232](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.2-alpha.3/packages/core/tools/src/pipeline.ts#L190-L232), [486–521](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.2-alpha.3/packages/core/tools/src/pipeline.ts#L486-L521)

Bridge parser recognizes upstream-like fields, but consumers differ: Claude applies deny/ask; Codex applies deny only. Both ignore rewrites and do not halt for `continue:false`. [Parser:59–132](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.2-alpha.3/packages/experimental/hook-protocol/src/codec.ts#L59-L132), [Claude consumer:180–269](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.2-alpha.3/packages/experimental/hooks-claude-code/src/index.ts#L180-L269), [Codex consumer:174–255](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.2-alpha.3/packages/experimental/hooks-codex/src/index.ts#L174-L255)

**Failure behavior.** Native throws become tool errors; hangs require cooperative cancellation. Bridges run serially, default **600 seconds**, through configured `ctx.shell`. Exit 2 blocks; other nonzero exits, malformed JSON and spawn failures supply no structured block. Timeout follows returned exit status. [Runner:67–103](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.2-alpha.3/packages/experimental/hook-protocol/src/runner.ts#L67-L103), [native cancellation:7–41](https://github.com/deepseek-ai/deepseek-harness/blob/dsh-v0.2.2-alpha.3/packages/core/tools/src/events.ts#L7-L41)

**Official JSON Schema.** None found for hook wire input/output.

**Differences/open questions.** dsh has three distinct contracts. Neither compatibility bridge faithfully implements upstream rewrite semantics.

## RTK reference adapters

Pinned `develop` SHA: **`63b8c3e26ec9487eb3953a142a8279366b5f5689`**, observed November 3.

| Harness | Integration confirmed in source |
|---|---|
| Claude | Preserves input, rewrites command through `updatedInput`. [`hook_cmd.rs:683–750`](https://github.com/rtk-ai/rtk/blob/63b8c3e26ec9487eb3953a142a8279366b5f5689/src/hooks/hook_cmd.rs#L683-L750) |
| Codex | Native PreToolUse; emits allow **with** updatedInput. [`hook_cmd.rs:959–1042`](https://github.com/rtk-ai/rtk/blob/63b8c3e26ec9487eb3953a142a8279366b5f5689/src/hooks/hook_cmd.rs#L959-L1042) |
| Antigravity | `run_command`, `CommandLine`, `overwrite.CommandLine`. [`hook_cmd.rs:482–548`](https://github.com/rtk-ai/rtk/blob/63b8c3e26ec9487eb3953a142a8279366b5f5689/src/hooks/hook_cmd.rs#L482-L548) |
| Pi | Bash `tool_call`; mutates input in place. [`rtk.ts:116–136`](https://github.com/rtk-ai/rtk/blob/63b8c3e26ec9487eb3953a142a8279366b5f5689/hooks/pi/rtk.ts#L116-L136) |
| OpenCode | Dual v2 `execute.before` and v1 `tool.execute.before` adapters. [`rtk.ts:203–226`](https://github.com/rtk-ai/rtk/blob/63b8c3e26ec9487eb3953a142a8279366b5f5689/hooks/opencode/rtk.ts#L203-L226) |
| dsh | No adapter found in inspected hooks/init inventory. [`mod.rs:25–38`](https://github.com/rtk-ai/rtk/blob/63b8c3e26ec9487eb3953a142a8279366b5f5689/src/hooks/init/mod.rs#L25-L38) |
