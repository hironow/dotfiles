# Plan: agent-hook — one Go engine, harness definitions as data, a log line at every firing

**Date:** 2026-11-03
**Status:** Approved (owner, 2026-11-03, chat; Codex review 6: APPROVE). PR 0 merged as [#534](https://github.com/hironow/dotfiles/pull/534) (main `504987fd`); PR 1 in progress on `feat/agent-hooks-engine`.
**Related:** [hook contracts per harness](agent-hooks-go-contracts.md) (2026-11-03 snapshot, with the agy probe records), [agent sync](../agent-sync.md), [#533](https://github.com/hironow/dotfiles/pull/533) (Codex hooks rendered from the one source, from main `8d55d1b7`)
**Blocking decisions:** none (D1–D3 decided by the owner on 2026-11-03; no ADR, by the owner's decision)

## Owner decisions (2026-11-03, chat)

| Time | Decision |
| --- | --- |
| 14:52 | Unify the hooks dotfiles provides across harnesses first; review, add, or remove hooks afterwards |
| 15:34 | No ADR for the hooks work |
| 17:06 | Rewrite in Go, one source for Claude, Codex, agy, Pi, a log line at every firing |
| 17:08 | go-json v0.12.0 (v2 package) without the Class 2 cooldown, for this work |
| 17:28 | Design so harnesses such as dsh and OpenCode v2 can be added later |
| 17:35–17:36 | Dependencies: go-json, plus at most a JSON Schema library, so harness definitions (data) drive the code |
| 17:37 | No OTel from the start (no destination today); a pluggable sink is enough |
| 17:38 | Confirm each harness's contract in its OSS implementation |

Behavior stays as it is today (parity). Reviews 1–6 (Codex) are recorded at the end.

## Facts the design rests on (versions as of 2026-11-03; sources in [the contracts file](agent-hooks-go-contracts.md))

| Harness (installed / latest) | Transport | Pre input | Block | Rewrite | Failure handling by the harness |
| --- | --- | --- | --- | --- | --- |
| Claude Code (2.1.316 / 2.1.317; closed, docs) | command (exec form allowed) | `tool_name`, `tool_input`, `cwd`, ids; Bash `{command,...}`, Write `{file_path,content}`, Edit `{file_path,old_string,new_string,replace_all?}`, NotebookEdit `{notebook_path,new_source,...}` | exit 2 + stderr, or `permissionDecision:"deny"` | `updatedInput` replaces the whole input | non-0/2 exit, no start, timeout, bad JSON → continue, unless `"onFailure":"block"` (≥ 2.1.295) → block. Default timeout 600 s. Matching hooks run in parallel |
| Codex (0.166.0 stable; OSS `codex-rs/hooks`) | command (shell: sh; Windows PowerShell `-NoProfile -Command` or cmd) | `tool_name`, `tool_input`, `cwd`, ids; shell → `Bash {command}`; patch → `apply_patch {command: patch}` (matched by `Edit\|Write`) | exit 2 **with non-empty stderr**, or deny JSON (reason required) | `allow` + `updatedInput {command}` | everything else fails open (other exits, no start, timeout, bad JSON). Official generated JSON Schemas exist (`codex-rs/hooks/schema/generated/`). Trust per hook hash |
| agy (1.4.12; closed, docs + probes) | command (`sh -c`; Windows `cmd /c`) | `toolCall {name, args}`, `workspacePaths`, ids. Probed: `run_command {CommandLine}`, `write_file {Path,Content}`, `edit_file {Path,Target,Replacement}`. Public docs also name `write_to_file`, `replace_file_content`, `multi_replace_file_content` | `{"decision":"deny","reason"}` | `overwrite` (rtk excluded) | probed: any non-zero exit or timeout blocks; `{}` denies; `{"decision":"ask"}` = no-hook behavior; `allow` did not bypass permissions. Default timeout 30 s |
| Pi (1.4.0 / 1.5.0; OSS) | shim (in-process TypeScript) | `{toolName, input}`: bash/powershell `{command}`, write `{path,content}`, edit `{path, edits[{oldText,newText}]}` | `{block:true, reason}` or throw | mutate `event.input` | a pre throw blocks; no dispatch timeout (a hang stalls); handlers in load order |
| OpenCode v2 (2.0.29 / 2.2.5; OSS anomalyco/opencode) — later | shim (`Plugin.define`, `ctx.tool.hook("execute.before")`) | `{tool, input, agent, ...}`: shell `{command, workdir?, timeout(ms)?}`, write `{path,content}`, edit `{path,oldString,newString,replaceAll?}`, patch `{patchText}` | throw | mutate `input` (validated) | sequential, no timeout |
| dsh = DeepSeek Harness (not installed; dsh-v0.2.2-alpha.3) — later | shim (native `tools/pre-execute`) or a lossy Claude/Codex-compatible command bridge | bash/pwsh `{command, description, ...}`, write/edit `{file_path,...}`, apply_patch `{input}` | native deny | none natively (frozen input) | native throw → tool error |

## Design

### Shape: decode → IR → engine → encode

```text
native payload --decode(definition)--> Call{harness, event, tool, kind, input, cwd, project, native}
Call --engine (pure, IR only)--> Outcome{pass|block|rewrite, rule id, display reason, patch}
Outcome --encode(definition)--> native answer (stdout + exit code)
manifest + definitions --render--> each harness's registration (+ loss report)
```

- Module `tools/agent-hooks` (Go 1.27.3, `CGO_ENABLED=0`), binary `agent-hook`. Packages live under `internal/` and are named by role (the naming guide rules out `engine` as a name; "the engine" here means the pure hook packages): `ir` (the call and the outcome), one package per hook (`commandguard`, later `fileguard`, `secretguard`, `formatter`, `rtkpolicy`), `pyshlex` (Python's shlex, the command guard's tokenizer), `definition` (loads harness definitions, validates payloads, maps fields), `launch` (process I/O, deadlines), `logsink` (port + `FileSink`), and `cmd/agent-hook`.
- Dependencies: `github.com/goccy/go-json` v0.12.0 (v2 package, owner waiver) and `github.com/google/jsonschema-go` v0.4.3 (MIT; Google; used by the MCP Go SDK; only `go-cmp`, for its tests, in its module graph). Everything else is the standard library. No OTel SDK (owner decision; the observability guide's TracerProvider rule is overridden for this binary and recorded in the PR).
- The hook packages never see a native payload; definitions never see each other.

### Harness definitions are data

```text
tools/agent-hooks/harnesses/<name>/
  harness.json       transport, install strategy, registration templates per event/OS, launcher per OS,
                     payload tool name -> kind, per-hook tool scope, answer templates per outcome
                     (stdout template + exit code), support level per hook, versions covered
  pre.schema.json    JSON Schema 2020-12 of the native pre payload; "x-ir" annotations map fields to IR
  post.schema.json   same for post (with the success signal: Claude PostToolUse, agy error == "",
                     Pi !isError, OpenCode status == "completed"; Codex has none: post fires on completion)
  fixtures/          real payloads captured from the harness, labelled with its version
tools/agent-hooks/manifest.json   hooks: id, event, kinds, order, failure mode
tools/agent-hooks/shim/v1/        request.schema.json, response.schema.json (the shim protocol)
```

- A field moves or is renamed upstream → edit the schema, mapping, templates, and fixtures; the Go code does not change. New Go code is needed only for a new transport or new answer semantics.
- The manifest, every harness definition, and the shim protocol schemas are compiled into the binary with `go:embed`; nothing is read from the checkout at run time, so the rebuild-digest check covers them. Sync gets registrations, launchers, shims, and loss reports from the release binary itself (`agent-hook render --harness <name>`), so registrations and code cannot diverge. Tests: the binary works from a temporary directory with no checkout; a release built from changed definitions fails the digest check.
- Codex's definition is derived from Codex's generated schemas (pinned to the tag) with the envelope opened to unknown fields; the others are written from docs, source, and captured payloads.
- Validation has three layers with separate outcomes:
    - envelope (ids, event, tool name): unknown fields are ignored; a missing or wrong-typed field we use is `envelope_mismatch`;
    - tool input (per tool name, chosen with `if`/`then` on the tool name): a missing or wrong-typed field a hook needs is `input_mismatch`;
    - IR (after mapping): every field the hook needs is present and typed.
  Validation never skips a guard. Each hook declares the IR fields it needs with ordered candidate pointers, selected with jq's `//` rule (as the scripts do with `jq '.a // .b // .c'`): a candidate that is absent, `null`, or `false` is skipped, and any other value, including `""` and `0`, is selected. The command guard reads `tool_input.command` whatever `tool_name` is. Each hook runs on whatever it can extract. Validation results are only logged (`envelope_mismatch` / `input_mismatch` / `mapping_failed`, counted by doctor). The old scripts' results on malformed payloads (no `tool_name`, no `tool_input`, wrong types, unknown fields, and an earlier candidate that is `false` or `null` with a synthetic key in a later one, e.g. `{"content":false,"new_string":"AKIA..."}`) are pinned first and must stay the same. Whether a mismatch should block is a review item.
- `x-ir` minimum spec: a JSON Pointer from the payload root to the IR field, or an ordered list of pointers chosen by jq's `//` rule (skip absent, `null`, `false`); `*` selects every array element and yields a list (Pi `/input/edits/*/newText` → `contents[]`; agy `/workspacePaths/*` → `workspaces[]`); null or absent → the IR field is absent; per-tool mappings live under the tool's `if`/`then` branch. The project directory is not a mapping: a `ProjectLocator` port in the shell collects candidates as values (each workspace path, the file's git root, the file's directory, the call's cwd; a failed lookup is a value too), and the engine picks one (longest workspace containing the file, else the git root, else the directory; the call's cwd for commands). The choice is tested as pure logic, including failed lookups and several workspaces.
- Static tests: every `x-ir` pointer exists in its schema; every IR field a supported hook needs is mapped; every fixture validates; every fixture's IR equals a hand-written expected IR. Before wiring, Pi multi-edit and agy multi-workspace fixtures pass with no Go change.

### Kinds and per-harness scope

Kinds: `shell`, `write`, `edit` (one or more replacements), `patch` (patch text, multi-file), `notebook`. Each definition maps payload tool names to kinds. Support is kept per harness version, tool, and hook: a mapping is registered only after a captured fixture, its expected IR, and a live block confirm it. agy 1.4.12 registers the observed `run_command`, `write_file`, `edit_file`; the public-doc names (`write_to_file`, `replace_file_content`, `multi_replace_file_content`) are listed as `pending` and appear in the loss report as not covered. Per-hook scope lives in the definition, for example Pi's rtk applies to `bash` only.

### Support levels, capability matrix, loss report

Each hook has a level per harness version and tool: `supported`, `degraded` (reason), `pending` (documented, not observed), or `unsupported` (reason). The matrix below is generated from the definitions (the scope actually registered) and drives the tests and the loss report printed when a registration is rendered (and doctor INFO lines):

| Hook | Claude | Codex | agy | Pi | OpenCode v2 (later) | dsh native (later) |
| --- | --- | --- | --- | --- | --- | --- |
| files guard | supported | supported (patch) | supported | supported | supported | supported |
| secrets guard | supported | supported (patch `+` lines) | supported | supported (each `newText`) | supported | supported |
| command guard | supported | degraded on Windows (PowerShell text, bash grammar) | supported | degraded for `powershell` | supported | degraded for `pwsh` |
| rtk | supported (strip) | supported (forward) | unsupported (sandbox exec, permission rules) | supported (`bash`) | supported (`shell`) | unsupported (frozen input) |
| formatter | supported | supported | supported | supported | supported | supported |

### Launchers and the failure matrix

The binary validates its own answer against the harness's answer template before writing it, and an in-process watchdog writes the stage's failure answer and exits when the stage deadline passes (guards 10 s, rtk 10 s, formatter 20 s; registration timeout 30 s). Launchers add what the harness itself does not do.

| Harness / shell | Guard stage | rtk, formatter |
| --- | --- | --- |
| Claude (exec form, no shell) | `"onFailure":"block"`, `timeout` 30: no start, non-0/2 exit, timeout, and invalid JSON all block (Claude ≥ 2.1.295) | no `onFailure` (default continue) |
| Codex, sh (macOS, Linux, WSL) | `'<release>/agent-hook' codex pre --hook <id> \|\| { printf '%s\n' 'agent-hook failed' >&2; exit 2; }` | the bare command |
| Codex, Windows PowerShell | `& '<release>\agent-hook.exe' codex pre --hook <id>; if ($LASTEXITCODE -ne 0) { '<deny JSON>' }` | the bare command |
| Codex, Windows cmd (fallback shell) | `"<release>\agent-hook.exe" codex pre --hook <id> \|\| echo <deny JSON>` | the bare command |
| agy, sh | `'<release>/agent-hook' agy pre --hook <id> \|\| printf '%s' '<deny JSON>'` | pre: `\|\| printf '%s' '{"decision":"ask"}'`; post: `\|\| printf '{}'` |
| Pi / shims | the shim spawns the binary with a deadline; no answer, a bad answer, or a spawn error blocks | pass |

Sync renders the Codex Windows line for the shell Codex is configured to use (PowerShell or cmd) and doctor checks it. The program path is absolute and quoted by its shell's rules: sh single quotes with `'` written as `'\''`, PowerShell `& '...'` with `'` written as `''`, cmd double quotes. Claude's exec form needs no quoting: `command` is the path and `args` the arguments. These forms are the contract with sync's ownership rule (`_runs_agent_hook_release`, PR 0), which recognizes exactly them. A path holding something its harness still expands does not name itself: cmd expands `%VAR%` and, with delayed expansion, `!VAR!` inside double quotes, and Claude substitutes `${...}` placeholders in exec form. The renderer refuses such a path with a diagnostic (tested in PR 3), and the ownership rule never counts one. A Windows path is compared with `\` and `/` as the same separator; a POSIX path is compared as written, since `\` is a filename character there. If PR 3's live tests need a different launcher form, the ownership change lands in its own PR before PR 3, so that reverting PR 3 keeps it.

What is not guaranteed, and the mitigation:

- A binary that starts and exits 0 with malformed output: Codex (and agy) then fail open. Mitigation: the binary only reaches a home after the rebuild-digest check and `selftest`; doctor re-checks the digest.
- The binary hanging past the harness's own timeout despite the watchdog (for example a stuck runtime): Codex and agy fail open (agy: block). Mitigation: watchdog well under the timeout; a live test of the deadline.

Tests per OS: binary missing, non-zero exit, exit 0 with malformed JSON, a hang past the stage deadline, and a hang past the registration timeout; a normal exit 2 stays a block. Today's in-guard rules stay as they are (bad JSON input passes; a guard's internal exception passes on Claude; a missing command-guard companion blocks); changing them is a review item. A broken shim exchange (unknown protocol version, missing fields) is a separate rule: pre blocks, post does nothing.

### Releases, references, trust

- One build recipe (`just agent-hooks-build`) is used by sync, trust, and doctor: `CGO_ENABLED=0 GOTOOLCHAIN=local go build -trimpath -buildvcs=false -ldflags=-buildid=` with fixed `GOOS`/`GOARCH`/`GOAMD64`/`GOARM64`, the module cache verified against `go.sum`, and the Go version checked. The release ID hashes the sources and these build conditions. A test builds from two different directories and Git states and gets the same bytes.
- Sync builds `~/.local/share/dotfiles/agent-hooks/releases/<release-id>/agent-hook[.exe]`, runs `agent-hook selftest`, renders the registrations and shims for that release, then switches registrations. Any failure leaves the previous release, registrations, and trust in place.
- Releases are never deleted automatically: a session that loaded an older shim keeps its absolute path until it reloads, and session lifetimes have no bound. `just agent-hooks-gc` lists releases no registration, plugin, or shim references, and deletes them only when run, after reminding to reload open Pi and OpenCode sessions. Uninstall works per harness and per home. Test: a session holding an old shim keeps working after newer releases are installed.
- Trust and doctor do not trust a receipt: they rebuild with the same recipe into a temp directory and compare the installed binary's SHA-256 with it. Codex trust is renewed for the new command strings (they name the release path).
- Shims are generated per release (absolute binary path, release ID, protocol version) and switched only after the binary is in place.

### Shim protocol v1 (JSON Schema, validated on both sides)

- Request: `{v:1, harness, event, tool, input, cwd, ok (post only: the tool succeeded), context (open object, for example OpenCode's agent)}`.
- Response: `{v:1, action: pass|block|rewrite, reason?, set?}`; `set` maps an allowed IR field to a string (only `command` today). No deletion, no other types.
- Rewrites everywhere work the same way: the engine returns `set` on IR fields; the codec writes each value at that field's `x-ir` pointer into a copy of the original native input, validates the whole result against the tool's input schema, and answers with the harness's form: Claude gets the full merged input as `updatedInput` (other options such as `timeout` or `run_in_background` stay), Codex gets `updatedInput {command}` with `allow`, a shim sets the field in place. Conformance covers `command: null`, a wrong type, an unknown key, and keeping existing options.

### Logging (every firing, no OTel)

- Port `LogSink`; adapters `FileSink` (JSONL) and an in-memory fake for tests. Another sink later (for example OTLP) is a new adapter.
- One line per invocation to `$XDG_STATE_HOME/dotfiles/agent-hooks/logs/<date>.jsonl` (default `~/.local/state/...`; Windows `%LOCALAPPDATA%\dotfiles\agent-hooks\logs\`), files 0600 in a 0700 directory, kept 14 days, at most 10 MB a day.
- Only fixed-enum values: time, release, harness, event, tool (known names, else `other`), kind, hook id, outcome, rule id, duration ms, program and subcommand class (fixed lists, else `other`), file extension (fixed list, else `other`), a salted hash of the project directory, error code, W3C `trace_id`/`span_id` for correlating lines. No paths, command text, contents, reasons, or error messages.
- Logging failures never change an outcome. `just agent-hooks-log` prints recent lines readably.
- Latency budget, measured before wiring: p95 end to end within today's scripts + 15 ms on this Mac.

### Ports (parity)

- Command guard: the algorithm ported, not a shell parser: a Go tokenizer reproducing Python `shlex(posix=True, punctuation_chars=True, whitespace_split=True)` with comments; heredoc split with its quirks; regexes moved to RE2 with Python's Unicode `\s`/`\w` spelled out; rtk run verbs; the legacy scan; bash `case` globs as written.
- Files guard, secrets guard (9 patterns, line by line), formatter (same commands, project directory, only after success), rtk (Claude: worktree veto, mise launcher, strip; Codex: real binary, pwsh-safe path, allow + updatedInput; Pi: `rtk rewrite`, bash only).
- Parity tests: the old scripts stay as references until the last PR; differential tests at token, heredoc, and verdict level over all fixtures and a generated corpus (empty quotes, trailing escapes, comments, newlines, Unicode, unbalanced quotes); the existing subprocess tests run against both; the Claude `file_path` route of the files guard gets the test it lacks. The corpus and expected values stay as engine tests afterwards.
- How PR 1 does it for the command guard: `just command-guard-corpus` writes `internal/guardcorpus/command-guard.jsonl` from the Python guard: every command the guard's own tests use (read from their AST), edge cases for each quirk, each Python space and word-boundary character where it matters, pairs of fragments, and seeded random inputs, each with Python's tokens or tokenizer error, heredoc split, and verdict. `tests/unit/test_command_guard_corpus.py` fails when the file is stale; the Go tests check the port against it. The subprocess tests run against both once the binary decodes payloads (PR 2).
- Python's `\w` is not Go's. Go 1.27's tables are Unicode 17.0 and Python 3.14's are 16.0, and every letter Go adds would hide a name from the guard (a Unicode 17.0 letter after `bash` turns a block into a pass). So the port reads Python's own `\w`, written as a Go table (`internal/commandguard/pyword_table.go`) by the same recipe. The corpus and the table follow Python 3.14 (Unicode 16.0, pinned in the script): the script refuses to write them from another version, a test on every Python checks the table's version, and the checks that need Python 3.14 run in their own CI step on 3.14, where a skip fails instead (CI's other unit tests run on Python 3.12).
- Known differences: inputs Python can hold but UTF-8 cannot (lone surrogates), and Python's recursion limit, have no Go counterpart.

## PRs (each: Red tests first, `just ci`, full `just test` when recipes change, PR CI green, squash merge)

0. Ownership and compatibility: sync recognizes release-path registrations as managed (alongside script paths); the Pi installer removes the extension files it placed whose source is gone (a symlink to that source, or a copy whose first line is `// dotfiles-managed: <its own name>`). No behavior change. Uninstall moves into the binary and ships with each wiring PR (PR 3: Claude, Codex; PR 4: agy, Pi), because it removes what that PR registers; for Claude and Codex a revert plus a re-sync is already clean after PR 0.
1. Engine core and the command guard port with the token/heredoc/verdict differential harness.
2. Files and secrets guards, formatter, rtk policies, the definition loader with JSON Schema validation, definitions and fixtures for Claude, Codex, agy, Pi, the shim protocol, the conformance suite and capability matrix, `LogSink`/`FileSink`, the latency measurement, and the existing subprocess tests run against both the scripts and the binary. Not wired.
3. Releases, launchers, Claude and Codex wired; doctor (per harness: registered as rendered, enabled, release fresh by rebuild, runtime deps, loss report); Codex trust. Live: old tests against the installed binary; Claude and Codex sessions block `npm --version` and a `.yml` write, rewrite `git status`, log one line per firing; launcher failure cases per OS. A round-trip test renders every launcher form (each harness, OS, and shell) and checks that sync's `_runs_agent_hook_release` accepts each one, including paths with an apostrophe, `$`, or a space, while the negative corpus in `tests/unit/test_codex_hooks.py` is still rejected, so the renderer and the ownership rule cannot drift apart.
4. agy plugin (guards + formatter) and the Pi shim (guards + formatter + rtk; the vendored `rtk.ts` retired in the same PR). Live in scratch: blocks for `npm --version`, `x.yml`, a synthetic AWS-style key in a write and in a later edit element; an allowed write is formatted; agy compared with no plugin in auto and accept-edits modes and an owner-run interactive check; Pi rewrites `git status`; a live check that blocks and rewrites take effect. The installer places the Pi shim and counts it as a current extension: since PR 0 it removes any `// dotfiles-managed: <name>` extension it has no source for.
5. Remove the old scripts and their name-based handling, and move what still reads the Python guard: doctor's rtk-guard check (`scripts/ai_tools_check.py` reads its `RTK_RUN_SUBCOMMANDS` and `RTK_FILTER_SUBCOMMANDS`) and `just command-guard-corpus` with its test (the corpus stays as the Go tests' data, and the word table as the port's); final docs (`docs/agent-sync.md`, enforcement and rtk guides, repo `CLAUDE.md`).

Later, each its own PR through the same definition + conformance path: OpenCode v2 (shim), dsh (shim on its native events), rtk on agy (needs agy permission settings).

## Not in this plan

- Changing what any hook decides. Review items, kept as they are now: `NotebookEdit`'s `notebook_path` unchecked; relative `docs/agents/x.yml` not exempt; `bash -c` not unwrapped; bad JSON passes; guard exceptions pass on Claude; PowerShell commands checked with the bash grammar.
- Third-party hooks and plugin version drift. Upgrading Pi (1.5.0) or OpenCode (2.2.5): fixtures record the versions; upgrades are separate.

## Owner decisions on the plan (2026-11-03)

- D1 Logged fields: only the fixed-enum values listed above.
- D2 Releases under `~/.local/share/dotfiles/agent-hooks/` with reference-based cleanup: go ahead.
- D3 Pi's vendored `rtk.ts` is replaced by the engine's rtk in the Pi PR.

## Rollback

Each PR is one squash merge. Before reverting a wiring PR, run the per-harness uninstall (new code); then revert and re-sync; check that no old/new duplicates remain.

## Review record

- PR 1 reviews (Codex, of the code and of this plan's changes for PR 1). The package names by role, moving the subprocess tests to PR 2, and the PR 5 moves had no findings. The code findings were confirmed with Red tests and adopted:
    - Round 1 (REVISE): `\w` from Go's Unicode 17.0 tables turned a block into a pass (a Unicode 17.0 letter after `bash`). The port now reads Python's own `\w` table, and this plan no longer accepts that difference. The same round showed that the dev container's `just check` runs the Go tests in CI.
    - Round 2 (REVISE): the table followed whatever Python ran the script, so a run on 3.12 would have downgraded it unnoticed. The script now pins Unicode 16.0 and refuses others; the version-bound checks run strictly on Python 3.14 in CI.
    - Round 3 (APPROVE): no further findings.

- PR 0 reviews (Codex, of the code and of this plan's PR 0 and PR 4 changes). The plan changes were accepted in round 1. The code findings were all confirmed and adopted:
    - Round 1 (REVISE): release ownership matched a mere mention of the path; an unreadable user `.ts` aborted the Pi install.
    - Round 2 (REVISE): a bare-path prefix still allowed an assignment or a redirection; `normpath` let a user's link spell our path through another link and `..`.
    - Round 3 (REVISE): valid Windows quoting (PowerShell `''`, a literal `$` in cmd) was not recognized, so a revert would leave duplicates; the matcher must already accept everything PR 3 renders, since a fix in PR 3 is reverted with it. The rule now extracts the program per launcher form by that shell's quoting.
    - Round 4 (REVISE): `\` was turned into `/` in POSIX paths too, where it is a filename character; cmd still expands `%VAR%` and `!VAR!` inside double quotes, so the contract's "content literal" was wrong. Now only Windows paths treat `\` as a separator, and a path holding what its harness expands (cmd `%` `!`, Claude `${`) never counts; the renderer refuses one.
    - Round 5 (APPROVE): no further findings.
    - The class of problem is an ownership rule that accepts more than the renderer writes. The round-trip test in PR 3 guards against it.
- Review 6 (Codex, APPROVE): no further findings.
- Review 5 (Codex, REVISE, 1 P2): candidate selection follows jq's `//` (skip absent, null, false), pinned by a differential test — adopted.
- Review 4 (Codex, REVISE, 3): validation never skips a guard (per-hook candidate pointers; malformed-payload results pinned); definitions embedded in the binary and rendered by it; project-directory lookups behind a port — all adopted.
- Review 3 (Codex, REVISE, 6): launchers per actual shell with stated non-guarantees; three-layer validation and an `x-ir` spec; field-level rewrites validated after merge; no automatic release deletion; a fixed reproducible build recipe; agy registers observed tools only — all adopted.

- Review 1 (Codex, REVISE, 10): launch failure, receipt trust, tokenizer granularity, guard/rtk independence, matcher vs payload names, log scrubbing, release/registration skew, rollback leftovers, agy interactive acceptance, latency budget — all adopted.
- Review 2 (Codex, REVISE, 7): launcher failure matrix, reference-based release cleanup, rebuild-based trust, release-bound shims, shim protocol schema, enum-only log values, capability matrix and captured fixtures — all adopted.
- Research corrections applied: Claude `onFailure:"block"` and exec form (no shell launcher needed for Claude); Codex exit 2 needs non-empty stderr and everything else fails open (so Codex guards need the fallback); Codex's official generated schemas; agy public tool names in addition to the probed ones; OpenCode v2 and dsh contracts for later.
