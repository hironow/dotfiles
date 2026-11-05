# Plan: agent-hook — one Go engine, harness definitions as data, a log line at every firing

**Date:** 2026-11-03
**Status:** Approved (owner, 2026-11-03, chat; Codex review 6: APPROVE). PR 0 merged as [#534](https://github.com/hironow/dotfiles/pull/534), PR 1 as [#535](https://github.com/hironow/dotfiles/pull/535), PR 2a as [#537](https://github.com/hironow/dotfiles/pull/537) after the fix [#536](https://github.com/hironow/dotfiles/pull/536); PR 2b as [#540](https://github.com/hironow/dotfiles/pull/540) (main `0c225828`), PR 2c as [#544](https://github.com/hironow/dotfiles/pull/544) (main `66b75132`), PR 2d as [#545](https://github.com/hironow/dotfiles/pull/545) (main `f93b7735`), PR 2e as [#546](https://github.com/hironow/dotfiles/pull/546) (main `7a6f70fd`), PR 2e.2 as [#548](https://github.com/hironow/dotfiles/pull/548) (main `c7baaa6c`). PR 2e.3 is on hold (owner, 2026-11-05); its work in progress is commit `cc5619c5`, which [#549](https://github.com/hironow/dotfiles/pull/549) took off main. PR 2f goes ahead of it; its first part, the port of Pi's path resolution, is [#551](https://github.com/hironow/dotfiles/pull/551).
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

- Module `tools/agent-hooks` (Go 1.27.3, `CGO_ENABLED=0`), binary `agent-hook`. Packages live under `internal/` and are named by role (the naming guide rules out `engine` as a name; "the engine" here means the pure hook packages): `ir` (the call and the outcome), one package per hook (`commandguard`, later `fileguard`, `secretguard`, `formatter`, `rtkpolicy`), `pyshlex` (Python's shlex, the command guard's tokenizer), `definition` (loads harness definitions, validates payloads, maps fields), `launch` (process I/O, deadlines), `logline` (the log line, pure), `logsink` (port + `FileSink`), and `cmd/agent-hook`.
- Dependencies: `github.com/goccy/go-json` v0.12.0 (v2 package, owner waiver) and `github.com/google/jsonschema-go` v0.4.3 (MIT; Google; used by the MCP Go SDK; only `go-cmp`, for its tests, in its module graph). Everything else is the standard library. No OTel SDK (owner decision; the observability guide's TracerProvider rule is overridden for this binary and recorded in the PR).
- The hook packages never see a native payload; definitions never see each other.

### Harness definitions are data

```text
tools/agent-hooks/harnesses/<name>/
  harness.json       transport, install strategy, registration templates per event/OS, launcher per OS,
                     payload tool name -> kind, per-hook tool scope, answer templates per outcome
                     (stdout template + exit code), support level per hook, versions covered
  pre.schema.json    JSON Schema of the native pre payload (2020-12; Codex's keeps its generated draft-07);
                     "x-ir" annotations map fields to IR
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

Tests per OS: binary missing, non-zero exit, exit 0 with malformed JSON, a hang past the stage deadline, and a hang past the registration timeout; a normal exit 2 stays a block. A guard that panics blocks since PR 2e.2 (`fixed-guard-failure`); rtk and the formatter let the call go on; a missing command-guard companion blocks. Bad JSON input was one: since PR 2b, input that is not one JSON value blocks, a change its review decided (see how PR 2b does it). A broken shim exchange (unknown protocol version, missing fields) is a separate rule: pre blocks, post does nothing.

### Releases, references, trust

- One build recipe (`just agent-hooks-build`) is used by sync, trust, and doctor: `CGO_ENABLED=0 GOTOOLCHAIN=local go build -trimpath -buildvcs=false -ldflags=-buildid=` with fixed `GOOS`/`GOARCH`/`GOAMD64`/`GOARM64`, the module cache verified against `go.sum`, and the Go version checked. The release ID hashes the sources and these build conditions. A test builds from two different directories and Git states and gets the same bytes.
- Sync builds `~/.local/share/dotfiles/agent-hooks/releases/<release-id>/agent-hook[.exe]`, runs `agent-hook selftest`, renders the registrations and shims for that release, then switches. Any failure leaves the previous release, registrations, and trust in place.
- **Registrations name a stable path per home** (owner, 2026-11-05 18:45, chat), `~/.local/share/dotfiles/agent-hooks/current/<home>/agent-hook`: a symlink to that home's release. Switching a release moves the link only, so `settings.json`, `hooks.json`, and Codex's trust do not change, and a running session's next hook call runs the new release. With a release path in every command, every new release would have rewritten Codex's commands and their trust, and a Codex session started in between would have run with no dotfiles hook for its whole life: Codex keys trust by a hook's position, hashes its command, and reads hooks once per session. Trust is renewed only when a registration itself changes (the first switch, or a changed template), in a locked, restorable switch with Codex stopped (PR 3d). Pi's and OpenCode's shims still name a release.
- Releases are never deleted automatically: a session that loaded an older shim keeps its absolute path until it reloads, and session lifetimes have no bound. `just agent-hooks-gc` lists releases no registration, plugin, or shim references, and deletes them only when run, after reminding to reload open Pi and OpenCode sessions. Uninstall works per harness and per home. Test: a session holding an old shim keeps working after newer releases are installed.
- Trust and doctor do not trust a receipt: they rebuild with the same recipe into a temp directory and compare the installed binary's SHA-256 with it.
- Shims are generated per release (absolute binary path, release ID, protocol version) and switched only after the binary is in place.

### Shim protocol v1 (JSON Schema, validated on both sides)

- Request: `{v:1, harness, event, tool, input, cwd, ok (post only: the tool succeeded), context (open object, for example OpenCode's agent)}`.
- Response: `{v:1, action: pass|block|rewrite, reason?, set?}`; `set` maps an allowed IR field to a string (only `command` today). No deletion, no other types.
- rtk on Claude and Codex is a delegate, not a rewrite the binary makes: rtk's own adapter (`rtk hook claude`, `rtk hook codex`) reads the native payload and writes the native answer, and the binary edits that answer exactly as the scripts do (PR 2c). A deny from rtk stays a deny.
- Rewrites the binary makes itself (from PR 2d: Pi's `rtk rewrite`) work the same way everywhere: the engine returns `set` on IR fields; the codec writes each value at that field's `x-ir` pointer into a copy of the original native input, validates the whole result against the tool's input schema, and answers with the harness's form: Claude gets the full merged input as `updatedInput` (other options such as `timeout` or `run_in_background` stay), Codex gets `updatedInput {command}` with `allow`, a shim sets the field in place. Conformance covers `command: null`, a wrong type, an unknown key, and keeping existing options.

### Logging (every firing, no OTel)

- Port `LogSink`; adapters `FileSink` (JSONL) and an in-memory fake for tests. Another sink later (for example OTLP) is a new adapter.
- One line per invocation to `$XDG_STATE_HOME/dotfiles/agent-hooks/logs/<date>.jsonl` (default `~/.local/state/...`), files 0600 in a 0700 directory, kept 14 days.
    - A day's file takes no line past 10 MB. Runs do not lock each other, so runs that write at the same moment can each add one line (under 4 KiB) past it: a day's file stays under 10 MB plus 4 KiB per run writing at once.
    - Windows (`%LOCALAPPDATA%\dotfiles\agent-hooks\logs\`) is not logged yet. The standard library can neither read nor set a file's owner and DACL, and the Go tests run only on Linux. A Windows adapter that checks both through handles, tested on a Windows runner, is its own PR.
- Only fixed-enum values: time, release, harness, event, tool (known names, else `other`), kind, hook id, outcome, rule id, duration ms, program and subcommand class (fixed lists, else `other`), file extension (fixed list, else `other`), a salted hash of the project directory, error code, W3C `trace_id`/`span_id` for correlating lines. No paths, command text, contents, reasons, or error messages.
- Logging failures never change an outcome. `just agent-hooks-log` prints recent lines readably.
- Latency budget, measured before wiring: p95 end to end within today's scripts + 15 ms on this Mac. PR 2h.2 measured it on 2026-11-05: every hook is within it, and faster than its script ("How PR 2h.2 does it" below).

### Ports (parity)

- Command guard: the algorithm ported, not a shell parser: a Go tokenizer reproducing Python `shlex(posix=True, punctuation_chars=True, whitespace_split=True)` with comments; heredoc split with its quirks; regexes moved to RE2 with Python's Unicode `\s`/`\w` spelled out; rtk run verbs; the legacy scan; bash `case` globs as written.
- Files guard, secrets guard (9 patterns, line by line), formatter (same commands, project directory, only after success), rtk (Claude: worktree veto, mise launcher, strip; Codex: real binary, pwsh-safe path, rtk's answer forwarded with only the command changed; Pi: `rtk rewrite`, bash only).
- Parity tests: the old scripts stay as references until the last PR; differential tests at token, heredoc, and verdict level over all fixtures and a generated corpus (empty quotes, trailing escapes, comments, newlines, Unicode, unbalanced quotes); the existing subprocess tests run against both; the Claude `file_path` route of the files guard gets the test it lacks. The corpus and expected values stay as engine tests afterwards.
- How PR 1 does it for the command guard: `just command-guard-corpus` writes `internal/guardcorpus/command-guard.jsonl` from the Python guard: every command the guard's own tests use (read from their AST), edge cases for each quirk, each Python space and word-boundary character where it matters, pairs of fragments, and seeded random inputs, each with Python's tokens or tokenizer error, heredoc split, and verdict. `tests/unit/test_command_guard_corpus.py` fails when the file is stale; the Go tests check the port against it. The subprocess tests run against both once the binary decodes payloads (PR 2).
- Python's `\w` is not Go's. Go 1.27's tables are Unicode 17.0 and Python 3.14's are 16.0, and every letter Go adds would hide a name from the guard (a Unicode 17.0 letter after `bash` turns a block into a pass). So the port reads Python's own `\w`, written as a Go table (`internal/commandguard/pyword_table.go`) by the same recipe. The corpus and the table follow Python 3.14 (Unicode 16.0, pinned in the script): the script refuses to write them from another version, a test on every Python checks the table's version, and the checks that need Python 3.14 run in their own CI step on 3.14, where a skip fails instead (CI's other unit tests run on Python 3.12).
- Known differences: inputs Python can hold but UTF-8 cannot (lone surrogates), and Python's recursion limit, have no Go counterpart.
- How PR 2a does it for the files and secrets guards: `just file-guards-corpus` runs the shell guards (bash and jq) on each input as Claude Code (file_path, content) or Codex (an apply_patch patch) hands it over, and records the exit code and the reason: the inputs of the guards' own tests (read from their parametrize marks), edge cases for each quirk, and seeded random inputs. The secrets corpus writes every character as a JSON `\u` escape, so it holds no token shapes for a secret scanner to flag. `tests/unit/test_file_guards_corpus.py` reruns the guards and fails when a corpus is stale. The shell guards' quirks are kept: bash drops NUL bytes. Two quirks were bugs: a relative path under `docs/agents/` was not exempt, which the binary fixes since PR 2e.2 (`fixed-docs-agents-relative`), and one the binary fixes since PR 2e (`fixed-dash-line`): a path that starts with `-` (except `-` itself) makes `basename` fail, so the guard exits 1 and reads no further paths, except that GNU's `basename` (Linux, Git Bash) takes `--help` and `--version` and their prefixes as options that succeed, and the guard reads on. The files corpus records the old guard under both flavors, so the script needs both (on macOS, `gbasename` from coreutils); CI on Linux checks GNU's. The port takes base names itself and needs neither.
- How PR 2b does it: the binary `agent-hook <harness> pre --hook <id>` (ids `command-guard`, `files-guard`, `secrets-guard`) runs the three guards for Claude and Codex, not yet registered.
    - **Definitions:** `harnesses/{claude,codex}/` hold `harness.json` (versions, tool name to kind, the answers as templates), `pre.schema.json`, and fixtures with their expected IR. Claude's schema is written from the docs and payloads captured from Claude Code 2.1.316. Codex's is its generated schema at `rust-v0.166.0` with the envelope opened and `tool_input` typed per tool; its fixtures are constructed from that schema until PR 3 captures live ones. Both map the same candidates, because the old scripts read the same fields for every harness: `command`, `filePath`, and `content` (`content`, `new_string`, `new_source`). Codex never sends the last two, so its schema lists them as `x-ir-undeclared`. Tests: every pointer is declared or listed, every fixture validates, and each fixture decodes to its expected IR.
    - **Unreadable input blocks (the review item above):** stdin must be exactly one JSON value (RFC 8259, UTF-8, unique names, no escaped unpaired surrogate, at most 10,000 levels; numbers stay text). Anything else blocks with `BLOCKED: agent-hook could not read the hook input as one JSON value, so no guard ran.` The scripts did not reject bad JSON. Each read its own extensions and blocked on them: Python and jq read `NaN` and duplicate names, jq reads a BOM, several documents, and invalid UTF-8, and Python reads an escaped unpaired surrogate. Passing what the binary cannot read would turn some of today's blocks into passes, and jq's extensions change with its version. The condition is deliberately strict: Claude Code's `JSON.stringify` escapes an unpaired surrogate in a tool input, and such a call now blocks.
    - **Reading a readable payload, as each script does:** the command guard analyzes `command` only when it is a string that Python's `str.strip()` leaves non-empty. The files and secrets guards read a selected string as bash's `$(...)` leaves it (NUL bytes, then trailing newlines, dropped). An empty result falls back to `command` as an apply_patch patch. A non-string value prints as JSON text: the files guard finds no path in it, and the secrets guard checks that text, where a NUL stays `\u0000`. The files guard takes base names itself, so it asks the machine nothing (`fixed-dash-line`).
    - **Answers:** a pass exits 0 and writes nothing, where a script may have exited 1 or 5 with a diagnostic; PR 3's launchers block on any other exit. A Claude block exits 2 with the guard's `BLOCKED:` line. A Codex block exits 0 with `guard-codex.sh`'s deny JSON, its reason made one line as that script does. A guard that panics blocks (`fixed-guard-failure`, PR 2e.2); rtk and the formatter let the call go on, as their scripts did.
    - **Parity:** `just hook-payload-corpus` runs every payload through every script, as Claude Code (the script) and Codex (`guard-codex.sh`) run them. It uses a fixed environment that inherits nothing but `PATH`: `LC_ALL=C.UTF-8`, Python's stdin strict UTF-8 and its default 4,300-digit integer limit, Python 3.14 picked by the wrapper, and each `basename` flavor. It writes `internal/guardcorpus/payloads.jsonl`. Each run keeps the legacy result, its difference IDs (none, `unreadable`, `reference-limit`, `pass-diagnostic`, `nul-warning`, and the `fixed-*` of PR 2e), and the answer the binary must give, worked out by the script, not by Go. The payloads are the guard tests' inputs as those tests wrap them, the fixtures, unreadable input paired with blocking and harmless payloads, odd shapes and types of every field, candidate orders, tool names no definition maps, NULs, `-` paths, block reasons `guard-codex.sh` rewrites, an unused 4,300- and 4,301-digit integer, and 255 levels of nesting. `tests/unit/test_hook_payload_corpus.py` fails when the corpus is stale or a run's ID does not follow from its legacy result. The Go tests check the binary against every run in-process and as a real process, built once and run from an empty directory, each run a subtest named by its frame (`parity`, or its difference IDs). This is how the existing subprocess tests run against both.
    - **Left to PR 3's launcher tests:** what checks the scripts' own wiring (choosing a real `python3`, the wrapper's companion lookup, pwsh's exit codes, bash's pipes, and bash 3.2).
    - **Known differences:** unreadable input blocks. Past a reference's limit the binary reads on: jq 1.7.1 stops at 255 levels and jq 1.8.2 at 9,999, and the command guard's Python raises past 4,300 digits; each such script passes. The command guard's script reads stdin in the locale's encoding (cp932 on Japanese Windows), and the binary reads UTF-8. A pass is silent.
- How PR 2c does it: the binary also runs `agent-hook <harness> pre --hook rtk` and `agent-hook <harness> post --hook formatter` for Claude and Codex, not yet registered.
    - **Manifest:** `tools/agent-hooks/manifest.json` (embedded) gives each hook its event and failure mode. The guards are `closed`: unreadable input blocks. `rtk` and `formatter` are `open`: unreadable input passes silently and runs nothing, as the scripts failed open. A hook named for another event exits 64.
    - **rtk keeps each harness's entry point:** `rtk hook claude` and `rtk hook codex` disagree where rtk consults Claude Code's permission rules (measured with rtk 1.1.0: `pnpm install` is rewritten for Codex only). `internal/rtkpolicy` edits rtk's answer as each script does, at the JSON-value level, so untouched values keep their text:
        - Claude: the worktree git veto (Python shlex without comments), then mise's launcher (`shlex.quote` of `Path(...).as_posix()`, whose rules are `PurePosixPath`'s on Unix and `PureWindowsPath`'s on Windows), then the strip to `hookEventName` and `updatedInput`;
        - Codex: only the command changes, to rtk's real binary (mise's answer first, never a shim, an unquoted path). rtk's decision, reason, and other members stay.
    - **Programs are found as the scripts found them:** `process.Search` walks PATH as Python's `shutil.which` and bash do, joining without cleaning, so the kernel resolves `link/..` through the link (Go's `exec.LookPath` cleans first and can pick another program). A program found through a relative or empty entry is never run: the hook passes instead.
    - **The formatter:** each `file_path` line, or every Add/Update/Move-to path of the patch, that is a regular file: `.py` through the three `uv run --frozen --only-group lint ruff` commands (the last on one pipe for stdout and stderr, as `2>&1`), `.go` through `gofmt -w`. It reports what ruff still finds on stderr and exits 0. Commands inherit the process's environment, and its cwd on Claude and Codex (2d lets agy's formatter name the project directory).
    - **Definitions:** `post.schema.json` for both harnesses (Claude's from captured PostToolUse Write and Edit payloads of 2.1.316; Codex's derived from its generated `post-tool-use.command.input` at `rust-v0.166.0`), a `cwd` IR field, the pre `forward` answer (rtk's edited answer, as it is) and the post `pass` answer (the notice on stderr).
    - **Parity:** `just tool-hooks-corpus` runs each scenario through each script in a root built from scratch (PATH of fake programs then `sys-bin` with bash 5, jq, and Python 3.14; nothing inherited). The fakes log the path given to execve, the arguments, stdin (rtk only reads it), the physical cwd, and `PATH`, `HOME`, and a probe variable. It writes `internal/toolhookcorpus/{rtk,formatter}.jsonl`, with difference IDs (`unreadable`, `reference-limit`, `path-relative`, `rtk-answer-unreadable`, `nul-warning`, `pass-diagnostic`) derived from the legacy runs. The formatter's notices are built from the recorded ruff output, so a body is never cut where bash's NUL warning is taken off. The Go tests check every run in-process (a fake machine that answers from the generator's world and replays the invocations) and as a real process (`faketool` behind a shebang in each fake's place). A forwarded answer compares as JSON, integers exactly. `tests/unit/test_tool_hooks_corpus.py` keeps the corpora fresh, every ID earned, and every test of the old scripts mirrored by a scenario or a Go test.
    - **Not ported:** the `RTK_HOOK_PERMISSION_DECISION=keep` seam (the strip is the policy) and the wrappers' interpreter lookup (PR 3's launcher tests).
    - **Known differences:** the IDs above; Windows uses Go's `exec.LookPath` (PATHEXT), with a relative result not found; PATH unset finds nothing (Python falls back to `/bin:/usr/bin`); a formatter that cannot start reports nothing (bash printed its error into the notice).
- How PR 2d does it: the binary also answers agy (Antigravity CLI 1.5.0) for the three guards (`pre`) and the formatter (`post`), not yet registered (PR 4 ships the plugin).
    - **Facts:** payloads captured on 2026-11-04 from agy 1.5.0 in a scratch workspace (`.agents/hooks.json`, `agy -p --mode accept-edits`) have the shape of the 1.4.12 probe records and no `cwd`; `error` is `""` after a success. Pi 1.4.0's events were captured too, for 2e.
    - **Definition:** `harnesses/agy/` maps `run_command` to shell, `write_file` to write, and `edit_file` to edit; the public-doc names stay `pending`, not mapped. `x-ir`: `command` from `CommandLine`, `filePath` from `Path`, `content` from `Content` then `Replacement`, and `workspaces` from `/workspacePaths/*`. A pass is `{"decision":"ask"}`, a block `{"decision":"deny","reason":"BLOCKED: ..."}` with the reason escaped but not made one line, and a post answer `{}` with the notice on stderr.
    - **Data, not Go:** each schema names where its tool's name is (`x-ir-tool`: `/tool_name` for Claude and Codex, `/toolCall/name` for agy), so `Decode` no longer reads `tool_name` in Go. A pointer with one `*` makes a list field (`ir.Call.Lists`), each element read as a single field is.
    - **Success signal:** agy's post schema holds `x-success`: the member (`/error`), the values that mean success (`""`), and that an omitted member means success too. The member is read as written, so a number anywhere in the payload changes nothing. After a failed call no post hook runs, and the answer is `{}`. Claude and Codex have none, as before.
    - **Support:** `harness.json` gives each hook a level per tool (`supported`, `degraded`, `unsupported`); the tools a hook is registered for are today's matchers. One cell is a known gap:
        - rtk on agy is `unsupported`.
        - (Claude's files guard on NotebookEdit was the other, `degraded`, until PR 2e fixed it: `fixed-notebook-path`.)
        - Levels cover macOS and Linux; Windows levels come with PR 3's Windows launchers.
    - **Where commands run:** `hookCwd` says where a harness runs its hooks: Claude and Codex in the session's directory, agy in the directory that holds `hooks.json`.
        - On agy the formatter places each file (`locate`) on the machine: the file's real path, each workspace's real path, and the git root (the nearest `.git` entry; a failed lookup is a value).
        - `internal/project` picks the longest workspace that holds the file, else the git root, else the file's directory. The commands run there (`process.Command.Dir`), with the real path.
        - A relative path (agy sends no cwd), a path that does not resolve, and any path on Windows are not formatted.
        - Claude and Codex run as before: the fake machine now compares `Dir`, so 2c's corpora pin it empty for every invocation.
    - **Conformance:** `internal/conformance` (tests only) runs each hook's scenarios through every harness, on every tool the hook is registered for, in-process.
        - A scenario writes its value at the tool's real input member, listed in the suite from the contracts file rather than taken from `x-ir`, and never adds a member.
        - Per-harness readers, written from the contracts file and Codex's source (`parse_pre_tool_use` at `rust-v0.166.0`), read each answer as the harness does: a block with its reason, a pass, a rewrite, or invalid. Each reader has negative tests.
        - Degraded cells pin their gap; rtk is left to the tool-hooks corpus.
    - **Real process:** a test builds a workspace, a symlink out of it, and another project with `.git` on the real file system, and checks where the fake `uv` and `gofmt` ran and on which path.
    - **Not yet:** a captured payload with several workspaces (no capture had one); decoded test payloads cover that case.

- How PR 2f does it: the binary also answers Pi (1.4.0) through the shim protocol, for the three guards (`pre`) and the formatter (`post`), not yet registered (PR 4 ships the shim).
    - **The shim protocol v1** (`tools/agent-hooks/shim/`, embedded): `request.schema.json` and `response.schema.json`.
        - A harness whose `harness.json` says `"transport": "shim"` gets each request checked against the request schema, and the request's `harness` and `event` must be the binary's arguments.
        - A broken exchange is its own rule: input that is not one JSON value, an unknown `v`, a missing, wrong-typed, or unknown member, a relative `cwd`, or another harness or event. Before the tool, every hook blocks (`shim.broken`), rtk included; after it, nothing runs.
        - The loader checks a shim harness's answers against the response schema, and that they exit 0.
    - **Pi's definition** (`harnesses/pi/`):
        - tools `bash`, `write`, and `edit` (`powershell` pending), `hookCwd` session, and rtk `unsupported` until 2g;
        - the answers `{"v":1,"action":"pass"}` and `{"v":1,"action":"block","reason":"BLOCKED: ..."}`;
        - `x-ir`: `command`, `filePath`, `content`, `contents` (every `newText`, a new list field), and `cwd`; `x-success` is `/ok`.
        - The fixtures are the events captured on 2026-11-04, wrapped as requests. Pi hands its extensions the arguments after the tool's `prepareArguments`, its coercion, and its schema check, so an old-style edit arrives in `edits[]` (Pi 1.4.0 `agent-loop.js` `prepareToolCall`, `agent-session.js` `_beforeToolCall`).
    - **Pi's paths** (`"pathResolution": "pi"`):
        - Before any hook reads the call, the shell replaces `filePath` with the file Pi touches (`internal/pipath`, [#551](https://github.com/hironow/dotfiles/pull/551), checked against Pi itself). The home is Node's `os.homedir()` (`Machine.HomeDir`).
        - A path the port cannot resolve exactly as Pi does blocks in the files guard (`file.unresolved`), and the formatter leaves it.
        - The approved design named a three-way `paths` field (`lines`, `one`, `pi`). PR 2e (`fixed-one-path`, `fixed-dash-line`) and #550 made `one` read as `lines` does, so only the resolution is new.
        - The files guard reads the resolved path by lines, as on every harness. Since #550 that is never laxer than reading one name; it is stricter for a name that holds a newline.
    - **The secrets guard** reads every element of `contents` as it reads `content`. Claude, Codex, and agy map no `contents`, so their corpora are unchanged.
    - **The formatter on Pi** runs only when the binary's working directory is the request's `cwd`, compared physically: that is the shim's contract, and otherwise ruff could run with another project's settings. After a failed call (`ok` false), no post hook runs.
    - **Conformance** covers Pi:
        - its members;
        - a strict reader of the shim response, with negative tests;
        - relative paths, judged as resolved;
        - a key in an edit's second replacement.
    - **Not yet:**
        - the rewrite codec and Pi's rtk (2g);
        - the shim and its wiring (PR 4);
        - Windows (`powershell`, and Windows paths: a Windows cwd is not absolute in the protocol, so every pre hook blocks).

- How PR 2g does it: the binary also answers Pi's rtk (`agent-hook pi pre --hook rtk`, bash only) as the vendored `config/pi/extensions/rtk.ts` behaves, with its first rewrite answer. It is not yet registered: PR 4 ships the shim and retires `rtk.ts`.
    - **Pi's rtk** (`rtkpolicy.PiCommand`, `PiRewrite`):
        - On a shell tool, a command goes to `rtk rewrite <command>` (2 s) when it is a string that JavaScript's `trim` does not leave empty, it does not start with `rtk` and a space, it holds no NUL (Node's spawn refuses one, and `rtk.ts` passes), and `RTK_DISABLED` is not `1`.
        - On exit 0 or 3, stdout trimmed as JavaScript trims it is the new command, unless it is empty or the same.
    - **Differences from `rtk.ts`**, each recorded in the corpus:
        - `rtk-version-probe`: no per-session `rtk --version`;
        - `path-relative`: rtk found through a relative PATH entry is not run;
        - `rtk-signal`: a signal death passes, which `rtk.ts` reads as code 0;
        - `rtk-answer-invalid-utf8`: stdout that is not UTF-8 passes;
        - `rtk-split-utf8`: stdout read whole keeps a character that a pipe chunk splits;
        - `rtk-late-output`: output a descendant writes after rtk exits is kept while the pipe is open (2 s).
    - **The rewrite codec** (`definition.Event.Rewrite`) writes the new value at the field's first `x-ir` pointer, into a copy of the native payload, and validates the result against the event's schema.
        - What it cannot write or validate is no rewrite: the pass, with why on stderr.
        - `ir.Outcome` gains `Rewrite` and `Set`, one field: the command.
    - **The answer:** Pi's `rewrite` answer is `{"v":1,"action":"rewrite","set":{"command":...}}`; templates read `.Set`. Claude and Codex get no rewrite answer, since rtk stays a delegate there.
    - **Parity:**
        - `internal/toolhookcorpus/pi-rtk.jsonl` ([#553](https://github.com/hironow/dotfiles/pull/553), `just pi-rtk-corpus`) holds 70 scenarios, each run through `rtk.ts` under node with Pi 1.4.0's `execCommand` and a fake rtk. The Go test replays every scenario through the binary, each subtest named `parity` or by its difference IDs.
        - A real-process test runs `ExecMachine` on real scripts for what the replay cannot show: a signal, a timeout, a split character, and late output.
    - **Conformance** covers Pi's rtk: the strict shim reader reads a fake rtk's rewrite as the rewrite of the command.
    - **Not yet:**
        - the shim and its hook order (PR 4): it should run the guards on the command before rtk rewrites it, as all of Claude's hooks see the original command;
        - Claude's and Codex's rewrite answers;
        - Windows.
- How PR 2h.1 does it: every run of the binary logs one line of fixed values, after its answer. Nothing is registered yet (PR 3).
    - **The line** (`internal/logline`, pure): `Build` takes one run's raw facts and keeps only fixed values.
        - The harness, tool, hook, rule, program, subcommand, and extension each come from a fixed list (the embedded definitions and manifest, the guards' `Rules`, written lists), else `other`.
        - The project directory (the call's `cwd`, else agy's first workspace, else the binary's working directory) and the session and call ids reach the line only as HMAC-SHA256 with the machine's salt, over a message of labeled, length-prefixed fields. A call's pre and post lines share the trace id; without a salt there is no project, and the trace id is random.
        - The error codes: `input.unreadable`, `shim.broken`, `hook.failed`, `rewrite.dropped`, `tool.failed` (a post call after a failed tool), `answer.failed`, and `usage` (a line of six keys).
        - A test fills every raw field with marker paths, commands, and a credential-shaped text, and finds none in the line.
    - **The validation results**, only logged, as `mismatch`: the first that applies of `envelope` (the payload fails its schema without the top-level `allOf`, where every definition keeps its per-tool branches), `input` (it fails the whole schema), `mapping` (`ir.Call.MappingMismatch`: a field of a type the hooks do not read, or a kind without what it holds), and `unchecked` (the validator cannot read the payload, such as a number past float64's range, which the decoder takes). Every fixture has none.
    - **The ids:** Claude and Codex map `session_id` and `tool_use_id`, agy `conversationId` and `stepIdx`, as the IR fields `sessionId` and `callId`. No hook reads them. Pi's shim sends none yet (PR 4).
    - **The file log** (`internal/logsink`, `FileSink`, POSIX):
        - Every level is opened as an `os.Root` inside the one above and checked through the open handle: `agent-hooks` and `logs` must be the user's directories, and lose group and other permission.
        - On macOS, every directory and file it checks also loses any ACL, through the handle, and the sink reads that none is left (`fstat64_extended` and `fchmod_extended`; the standard library has no ACL call). macOS checks an ACL before the mode bits, and a directory's inheritable entries pass to everything made in it. The mode narrows in the same call, since a deny entry may be all that guards a loose mode. A CI job on macOS runs these tests (`go-macos` in `unit-test.yaml`). On Linux, a POSIX ACL's named entries are bounded by the mask, which is the mode's group bits, so 0600 and 0700 leave them nothing.
        - None of its names may be a link, even one that stays inside its directory, and a file must be the user's regular file with one link. Files are created only with `O_EXCL` and opened with `O_NONBLOCK`.
        - The salt (32 bytes) is made under a non-blocking `flock` of `salt.lock`, written to `salt.new`, synced, and linked to `salt`. The lock's holder removes what a maker that died left; a salt that is not 32 bytes is never replaced.
        - Each line goes in one write, and every write removes the day files more than 14 days old. A short write (a full disk) leaves a partial line, which the next line in that day's file joins; the reader skips and counts it. The sink does not truncate, since another run may have appended in between.
    - **The run** (`launch`): logging starts after the answer is written and waits at most 250 ms. A sink that fails, panics, or never returns changes no answer, exit code, or stderr. The binary opens the file log on first use, inside that time.
        - The random ids and the salt come from `internal/osrand`, which reads `/dev/urandom` and returns an error; on an error the line (or the salt) is dropped. `crypto/rand` is not used on this path: since Go 1.24 it ends the process when the OS source fails, and after the answer that would turn a pass into exit 2, which Claude reads as a block. A test fails if `launch`, `logline`, or `logsink` imports it.
    - **Reading it:** `agent-hook log [--days N]` (and `just agent-hooks-log`) prints the last N UTC days (N from 1 to 15, what retention keeps) as a table, sorted by time, and counts the lines it cannot read. It reads each day's file as its own, so a partial last line does not take the next day's first. A cell that is not printable ASCII is printed quoted, so a line that anything else wrote cannot send escape sequences to the terminal. Reading makes no directory. No harness can be named `log`.
    - **Tests:** the binary's own tests set `XDG_STATE_HOME` to a temporary directory, so no test writes to the user's file log.
    - **Not yet:** the latency measurement (2h.2); Windows; doctor reading the log (PR 3); Pi's ids (PR 4).

- How PR 2h.2 does it: `just agent-hooks-latency` (`cmd/hooklatency`, cases and statistics in `internal/latency`) times today's hook scripts against the binary, hook by hook. Nothing is registered yet.
    - **Both sides run as a harness runs a hook command:** `/bin/sh -c` with the command string, the payload on stdin, the same working directory, and the same environment.
        - `XDG_STATE_HOME`, `UV_PROJECT_ENVIRONMENT`, and `RUFF_CACHE_DIR` point at temporary directories the two sides share. So the binary's file log never reaches the user's, and the project's `.venv` and `.ruff_cache` stay as they are.
        - uv's own cache is the user's, which uv only adds to: a temporary one would need the network to install ruff again.
        - Today's side is the command this Mac's Claude and Codex homes register: `bash "~/.claude/hooks/<script>.sh"`, and for Codex `guard-codex.sh <guard>.sh`, `rtk-hook-codex.sh`, and `format-after-edit.sh`.
        - The binary's side is `"<binary>" <harness> <event> --hook <id>`, built once with the release flags (`CGO_ENABLED=0 -trimpath -ldflags=-s -w`), with logging on.
    - **The cases** (20): on Claude and on Codex, each guard on a pass and a block, rtk on `git status`, and the formatter on `.md` (no program), `.py` (uv and ruff), and `.go` (gofmt).
    - **The working directory is the repository's uv project**, which the formatter's `uv run --frozen --only-group lint ruff` needs. Only the formatter's file lives in a temporary directory, and it is written back to its first content before every run, outside the timed span. The design had a fresh copy of a small project per run, but each would make a new virtual environment, which takes seconds and would bury both sides.
    - **Each answer is checked:** a warm-up run of today's script gives the expected answer, and every run of either side must give it.
        - The warm-up answer must show what the case is named for: a pass, Claude's or Codex's block, rtk's rewrite of `git status`, or ruff's report for `.py`. A missing rtk or gofmt would pass on both sides, fast and alike, and time nothing.
        - For `.py` and `.go`, today's formatter must change the file, and every run of either side must leave the same content in it.
        - The exit code and stderr must match byte for byte. Stdout must too, or be the same JSON value (`toolhookcorpus.SameJSON`, as the parity corpora compare): Python's `json.dumps` spaces its separators, and the binary does not.
        - Each binary run must add exactly one line to its file log.
    - **Timing:** wall time from start to exit, N rounds (default 200), today's side first in even rounds and the binary first in odd ones. Times are nearest-rank p50 and p95. The tool exits 1 when a binary p95 passes the script's by more than the budget (15 ms).
    - **Measured 2026-11-05** on this Mac (Apple M1 Max, 10 cores, 64 GB, macOS 27.2; Go 1.27.3, rtk 1.1.0, uv 0.13.6, ruff 0.17.2, Python 3.14.5, GNU bash 5.3.20), N = 200, in ms:

        | Case | Script p50 | Script p95 | Binary p50 | Binary p95 | Δp95 |
        | --- | ---: | ---: | ---: | ---: | ---: |
        | `claude/pre/command-guard/pass` | 35.7 | 38.7 | 11.1 | 12.3 | -26.4 |
        | `claude/pre/command-guard/block` | 35.4 | 38.4 | 11.2 | 12.3 | -26.1 |
        | `claude/pre/files-guard/pass` | 23.7 | 26.0 | 11.1 | 12.2 | -13.8 |
        | `claude/pre/files-guard/block` | 23.6 | 25.8 | 10.8 | 11.8 | -13.9 |
        | `claude/pre/secrets-guard/pass` | 23.9 | 26.3 | 10.9 | 12.0 | -14.4 |
        | `claude/pre/secrets-guard/block` | 24.0 | 26.6 | 10.9 | 12.3 | -14.4 |
        | `claude/pre/rtk/git-status` | 58.9 | 64.7 | 26.7 | 30.1 | -34.6 |
        | `claude/post/formatter/md` | 23.0 | 24.3 | 11.9 | 12.6 | -11.7 |
        | `claude/post/formatter/py` | 100.4 | 106.6 | 85.8 | 90.4 | -16.1 |
        | `claude/post/formatter/go` | 26.5 | 29.1 | 16.0 | 17.6 | -11.5 |
        | `codex/pre/command-guard/pass` | 44.1 | 47.6 | 10.8 | 12.0 | -35.6 |
        | `codex/pre/command-guard/block` | 48.6 | 52.8 | 10.8 | 11.8 | -41.0 |
        | `codex/pre/files-guard/pass` | 41.2 | 44.8 | 10.6 | 12.0 | -32.8 |
        | `codex/pre/files-guard/block` | 45.0 | 50.2 | 10.5 | 11.7 | -38.5 |
        | `codex/pre/secrets-guard/pass` | 41.3 | 44.8 | 10.6 | 12.5 | -32.3 |
        | `codex/pre/secrets-guard/block` | 45.5 | 50.2 | 10.6 | 11.7 | -38.5 |
        | `codex/pre/rtk/git-status` | 75.6 | 82.0 | 46.9 | 50.1 | -31.9 |
        | `codex/post/formatter/md` | 30.7 | 34.3 | 10.8 | 11.8 | -22.5 |
        | `codex/post/formatter/py` | 104.6 | 114.6 | 80.8 | 87.9 | -26.7 |
        | `codex/post/formatter/go` | 35.4 | 39.4 | 15.6 | 17.2 | -22.2 |

    - The binary is faster in every case. Its guards take about 11 ms end to end with logging on, where the Python command guard took 35 to 49 ms. The formatter's `.py` case is mostly uv and ruff on both sides.
    - CI does not run the measurement, since timing is noisy there. Its tests run with fake scripts and three rounds, so the tool cannot rot.

- How PR 3a does it: the binary becomes a release, but nothing is registered yet (PR 3d).
    - **`just agent-hooks-build`** (`cmd/hookrelease build`) builds a release into `releases/<id>/agent-hook`:
        - Every `go` command runs in one environment built for it: `PATH`, `HOME`, and the caches; `GOENV` and `GOWORK` off, no experiment, `-mod=readonly`, the local toolchain, cgo off, the target and its level, and no proxy except for `go mod download`. A `replace` directive, or a C, cgo, or Swig input in a main-module package, is refused.
        - The release ID is 16 hex characters of SHA-256 over the Go version, the target, the fixed flags, and every file the target's build reads (`go list`'s `GoFiles`, `SFiles`, `HFiles`, `SysoFiles`, `EmbedFiles`, plus `go.mod` and `go.sum`). The checkout's place and Git state do not enter it.
        - The binary (`-trimpath -buildvcs=false -pgo=off`, no build ID, the ID in `logline.Release`) must show the expected build information, print its ID from `agent-hook version`, and pass `agent-hook selftest` before it is moved into place. An existing release with other bytes is refused and kept.
        - `check PATH` rebuilds and compares SHA-256. `switch --home KEY PATH` points `current/<KEY>/agent-hook` at one of the root's releases by renaming a new symlink over the old one.
    - **`agent-hook version`** prints the release ID and the Go version. **`agent-hook selftest`** answers 16 cases on the in-memory machine: on Claude and Codex, each guard on a pass and a block, rtk's forward, and the formatter's notice, byte for byte, with no program run and nothing logged. `version` and `selftest` cannot be harness names.
    - **The stage watchdog:** each hook has a deadline in `manifest.json` (the guards and rtk 10 s, the formatter 20 s).
        - A worker reads stdin, decodes, decides, and renders. The supervisor alone writes, once: the worker's answer, or at the deadline a guard's block with the rule `hook.timeout` (rtk and the formatter pass). The line logs `hook.timeout`.
        - Every child gets the stage's deadline. On POSIX each child leads its own process group, and its pipes are read from the start (one pipe for `Combined`). A watcher observes the exit with `waitid(WNOWAIT)` without reaping; one owner alone kills the group, at the deadline and after the pipes close (or 2 s after the exit), and only then reaps, so no signal can reach a reused group ID. The recorded `rtk-late-output` still holds. Windows kills the direct child.
    - **Tests:** two copies of the module build the same bytes; a polluted environment builds them too; the ID follows every input of the target; `check` finds a changed byte; `switch` keeps homes apart and points only at a release. The watchdog answers with no stdin EOF, drops a late worker, signals only before the reap, and leaves no descendant alive, with 1 MiB on each stream and `Combined`'s order kept.
    - **Not yet:** rendering (3b), doctor (3c), the wiring (3d), and Windows.

### Bugs of the old scripts that the binary fixes

The owner decided (2026-11-04 19:30, chat) that where an old script has a bug, the binary fixes it, and the tests keep each fix apart from the faithful port.

- **Each fix is a named edit to the old script** (`scripts/old_script_fixes.py`). The corpus generators apply it to copies of the scripts, so the fixed behavior is defined by a script, as the legacy one is, and never by Go.
- **The generators run the old scripts and the fixed ones** on every input. Answers are compared after the corpora's noise normalization.
    - Where they differ, the binary gives the fixed answer.
    - The run names the fixes it needs, as `fixed-<name>`: those whose absence from the full set changes the answer.
    - A run's difference is a set of IDs joined by `+`, so a fix and noise can stand together.
- **The frame shows in the tests.**
    - `tests/unit/test_corpus_differences.py` gives every ID a kind (`fixed`, `policy`, `limit`, `noise`) and a reason, and fails on an unregistered ID or a fix that no corpus input needs.
    - A fix that no old script can show (a Go panic has no input that makes an old script fail) is binary-only: it is registered with the Go test that holds it, and no corpus may name it.
    - The Go corpus tests name each subtest by its frame (`parity`, or its IDs), so `go test -run '/fixed-'` lists every place where the binary differs from the old scripts on purpose.
    - Each fix's own Go tests live in a `fixes_test.go`.
- **The fixes** (PR 2e), each reproduced on the old script and on main's binary:
    - `fixed-dash-line` (files guard): a line that starts with `-` made `basename` fail; the guard exited 1, which no harness blocks on, and checked no later line, nor that one. Base names are now taken without `basename(1)`, so every line is checked, and the binary needs no `basename` flavor.
    - `fixed-notebook-path` (files guard): NotebookEdit's `notebook_path` was never read. It is now checked on its own, after what the guard read before, so neither an empty nor a safe `file_path` hides it.
    - `fixed-one-path` (formatter): each line of `file_path` was formatted, with NULs and trailing newlines dropped, so a file the tool never wrote could be formatted. A string `file_path` now names one file, exactly as given; agy's formatter from 2d had the same flaw.
- **The four review items the plan held** (owner, 2026-11-04 22:00, chat: fix them all as bugs), in PRs 2e.2 to 2e.4:
    - `fixed-docs-agents-relative` (files guard, PR 2e.2): the exemption `*/docs/agents/*` needs a `/` before `docs`, so a relative path under `docs/agents/`, as Codex's patch names files, was blocked, though a bare `AGENTS.md` is exempt. It is exempt now, on a line where a path starts: the first line of a `file_path`, each file of a patch, and the first line of a `notebook_path`. A later line is part of the path above it: `/w/x`, a newline, and `docs/agents/y.yml` names a file under no `docs/agents/` directory, and it stays blocked, as the old guard blocked it.
    - `fixed-guard-failure` (launcher, binary-only, PR 2e.2): a hook that panicked let the call go on, guards included, as the old Python guard's own exceptions did (exit 1, which Claude and Codex let through). A guard that panics now blocks, with rule `hook.failed`; rtk and the formatter still let the call go on.
    - The command guard's reading of bash (PR 2e.3) and of PowerShell (PR 2e.4) follow.
- **Fixed earlier, under their own IDs** (PR 2c): `path-relative` (a program found through a relative PATH entry is not run) and `rtk-answer-unreadable` (an rtk answer that is not one JSON value is not forwarded).
- **The generator's own bug,** fixed as such: the 2a generator read a reason from the last `BLOCKED:`, which cut a reason that names a file holding `BLOCKED:`.

## PRs (each: Red tests first, `just ci`, full `just test` when recipes change, PR CI green, squash merge)

0. Ownership and compatibility: sync recognizes release-path registrations as managed (alongside script paths); the Pi installer removes the extension files it placed whose source is gone (a symlink to that source, or a copy whose first line is `// dotfiles-managed: <its own name>`). No behavior change. Uninstall moves into the binary and ships with each wiring PR (PR 3: Claude, Codex; PR 4: agy, Pi), because it removes what that PR registers; for Claude and Codex a revert plus a re-sync is already clean after PR 0.
1. Engine core and the command guard port with the token/heredoc/verdict differential harness.
2. Not wired, in eleven PRs so that each stays reviewable:
    - 2a. The files and secrets guards and Codex's apply_patch reading, ported with their parity corpora. Its review found two fail-opens in the shell guards, fixed first in [#536](https://github.com/hironow/dotfiles/pull/536) as an exception to keeping every decision: the secrets guard passed a large write holding a key (`grep -q` under pipefail), and the files guard passed `a.yml` where no file could be written (a here-string on bash 3.2). A reference that passes or blocks the same input depending on its size or its environment cannot be matched.
    - 2b. The definition loader with JSON Schema validation, definitions and fixtures for Claude and Codex, decode and encode, the binary, and the existing subprocess tests run against both the scripts and the binary.
    - 2c. The rtk and formatter hooks for Claude and Codex, so that the binary runs every hook they run today. The original 2c was split here, so that each part stays reviewable; only the order changes.
    - 2d. agy: its definition and fixtures, `*` pointers (list fields), the post success signal, the `ProjectLocator`, support levels per tool, and the conformance suite (the capability matrix is rendered from the levels in PR 3). The original 2d was split here, since agy and Pi share only the list fields; only the order changes.
    - 2e. The old scripts' bugs, fixed in the binary (owner's decision, 2026-11-04; "Bugs of the old scripts that the binary fixes" below). It comes before Pi because it changes Claude's and Codex's answers and the 2a, 2b, and 2c corpora.
    - 2e.2 to 2e.4. The four review items the plan held, fixed as bugs (owner, 2026-11-04): 2e.2 the files guard's relative `docs/agents/` and a guard that panics; 2e.3 the command guard finds every command bash runs from the text (newlines, joined operators, `#` inside a word, reserved words, substitutions, `bash -c`, `eval`); 2e.4 PowerShell commands are read with PowerShell's grammar.
    - 2f. Pi: its definition and fixtures, the shim protocol, Pi's paths, and its guards and formatter. The port of Pi's path resolution (`internal/pipath`, checked against Pi 1.4.0 itself, `just pi-paths-corpus`) lands first, in its own PR, with nothing calling it yet; only the order changes.
    - 2g. The rewrite codec and Pi's rtk (`rtk rewrite`, bash only), with parity against the vendored `rtk.ts`, run under node with Pi's own `execCommand`. The record of what `rtk.ts` does (`just pi-rtk-corpus`) lands first, in its own PR, with nothing using it yet; only the order changes.
    - 2h. `LogSink`/`FileSink` and the latency measurement, in two PRs: 2h.1 logs every run, and 2h.2 then measures the binary with logging on. Only the order changes.
3. Releases, launchers, Claude and Codex wired, in four PRs so that each stays reviewable (only the order changes): 3a releases (the build recipe and release ID, `version`, `selftest`, the stage watchdog), 3b rendering (registration templates as data, `agent-hook render`, the stable paths in the ownership rule, the round-trip test), 3c doctor, and 3d the wiring, with Codex trust, per-home uninstall (in sync, owner 2026-11-05: the ownership rule is sync's), and gc. Native Windows keeps the scripts until its own PR, which comes before PR 5. The plan's text for PR 3 as a whole: doctor (per harness: registered as rendered, enabled, release fresh by rebuild, runtime deps, loss report); Codex trust. Live: old tests against the installed binary; Claude and Codex sessions block `npm --version` and a `.yml` write, rewrite `git status`, log one line per firing; launcher failure cases per OS. A round-trip test renders every launcher form (each harness, OS, and shell) and checks that sync's `_runs_agent_hook_release` accepts each one, including paths with an apostrophe, `$`, or a space, while the negative corpus in `tests/unit/test_codex_hooks.py` is still rejected, so the renderer and the ownership rule cannot drift apart.
4. agy plugin (guards + formatter) and the Pi shim (guards + formatter + rtk; the vendored `rtk.ts` retired in the same PR). The installer and doctor compare the installed Pi version with `harnesses/pi/harness.json`'s `versions`: the path port and its corpus are Pi 1.4.0's, so on a version the definition does not cover the installer does not place the shim, and doctor says why. Pi follows `latest` in mise, so a `mise upgrade` can change Pi under a placed shim: the shim also compares Pi's own package version with the definition's when it loads, and on a mismatch blocks every call (fails closed). Live in scratch: blocks for `npm --version`, `x.yml`, a synthetic AWS-style key in a write and in a later edit element; an allowed write is formatted; agy compared with no plugin in auto and accept-edits modes and an owner-run interactive check; Pi rewrites `git status`; a live check that blocks and rewrites take effect. The installer places the Pi shim and counts it as a current extension: since PR 0 it removes any `// dotfiles-managed: <name>` extension it has no source for.
5. Remove the old scripts and their name-based handling, and move what still reads the Python guard: doctor's rtk-guard check (`scripts/ai_tools_check.py` reads its `RTK_RUN_SUBCOMMANDS` and `RTK_FILTER_SUBCOMMANDS`) and `just command-guard-corpus` with its test (the corpus stays as the Go tests' data, and the word table as the port's); final docs (`docs/agent-sync.md`, enforcement and rtk guides, repo `CLAUDE.md`).

Later, each its own PR through the same definition + conformance path: OpenCode v2 (shim), dsh (shim on its native events), rtk on agy (needs agy permission settings).

After this plan is complete, two new harnesses, one at a time, as the check that the design is complete, since a harness should be added as data (owner, 2026-11-04): grok CLI (`docs.x.ai/build/cli/reference`), then muse CLI (`dev.meta.ai/docs/overview#muse-code`).

The dev container CI job, paused in #547, stays paused until PR 5 is merged (owner, 2026-11-04). The Go tests run in their own CI job meanwhile.

## Not in this plan

- Changing what any hook decides, except the old scripts' bugs, which the binary fixes (owner, 2026-11-04; see "Bugs of the old scripts that the binary fixes"). The four review items the plan held are such bugs (PRs 2e.2 to 2e.4). (Bad JSON passing was one too; PR 2b's review changed it to a block.)
- Third-party hooks and plugin version drift. Upgrading Pi (1.5.0) or OpenCode (2.2.5): fixtures record the versions; upgrades are separate.

## Owner decisions on the plan (2026-11-03)

- D1 Logged fields: only the fixed-enum values listed above.
- D2 Releases under `~/.local/share/dotfiles/agent-hooks/` with reference-based cleanup: go ahead.
- D3 Pi's vendored `rtk.ts` is replaced by the engine's rtk in the Pi PR.
- 2026-11-05 18:45 (chat): registrations name a stable path per home, not a release (see "Releases, references, trust"); Claude's and Codex's uninstall lives in sync.

## Rollback

Each PR is one squash merge. Before reverting a wiring PR, run the per-harness uninstall (new code); then revert and re-sync; check that no old/new duplicates remain.

## Review record

- PR 3's design (Codex, seven rounds; APPROVE). Each finding was adopted:
    - Round 1 (REVISE, 7): restoring `hooks.json` alone does not restore Codex's trust; a switch writing new commands opens a trust window; the watchdog must supervise the whole run and kill descendants; build conditions outside the ID (`GOEXPERIMENT`, a parent `go.work`, Go settings); inputs of other targets; the selftest's scope; the plan's uninstall.
    - Round 2 (REVISE, 7): one shared link breaks naming homes in a sync, so the link is per home; the link must be in the restorable unit; a lock and bounded app-server calls; Go does not record `-ldflags` under `-trimpath`; a descendant can outlive its parent; `-pgo=auto` and other implicit inputs; gc's references.
    - Round 3 (REVISE, 3): a group kill after the reap can reach a reused group ID; the journal needs the new state and the stage; the merge must keep Codex's positions for others' hooks.
    - Rounds 4 and 5 (REVISE, 1 each): waiting for the exit before reading the pipes deadlocks; `Combined`'s one pipe must stay.
    - Rounds 6 and 7: APPROVE.

- PR 2g (Pi's rtk) code reviews (Codex):
    - Round 1 (APPROVE): no findings.
    - Round 2, after the NUL gate (REVISE, 1): the corpus replay gave the fake's stderr no place, so `rewrite-stderr` could not catch stderr mixed into the rewrite. It now replays stderr apart, and a mutation that mixes them fails.
    - Round 3 (APPROVE).
    - Its own checks: 20 mutations of its decisions; the one that survived showed a parameter that changed nothing (`RTK_DISABLED` unset reads as `""`), which is removed.
- PR 2g (Pi's rtk) design reviews (Codex), each claim checked against Pi 1.4.0's source:
    - Round 1 (REVISE, 2): Pi decodes each stdout chunk on its own, so a valid UTF-8 rewrite that a chunk boundary splits becomes U+FFFD; and Pi stops reading 100 ms after rtk exits, where Go reads until the pipe closes. Both keep Go's reading, recorded as `rtk-split-utf8` and `rtk-late-output`, with corpus scenarios and a real-process test.
    - Round 2 (APPROVE).
- The record of what `rtk.ts` does (`internal/toolhookcorpus/pi-rtk.jsonl`, part of PR 2g) was written by Codex from a brief, and reviewed by Claude and by an independent reviewer (a separate Claude session):
    - Round 1 (REVISE, 6):
        - The signal scenario's fallback exit was 0, so its check could not fail; it is now 1, and a late write inside Pi's 100 ms grace shows that the late child does write.
        - Where node or Pi is missing (CI), nothing tied the corpus to the scenarios; a test now renders the scenarios with the recorded answers and compares bytes.
        - It added scenarios for a NUL, a leading space before `rtk`, a padded command, and a bare `rtk`.
        - The local-path check missed a path that is not ASCII once the corpus escaped it, and the scenario PATH held node's directory, where a host rtk could answer. Both are fixed.
        - What the binary must do is now derived from each scenario's bytes, not written as literals.
    - Round 2 (APPROVE): each fix was shown to fail where it should, also under load and without node.
- PR 2f (Pi through the shim protocol) code reviews (Codex):
    - Round 1 (REVISE, 1): the conformance reader of the shim response took `"reason": null` as no reason, though the protocol makes a present reason a string. It now tells null from none, with negative tests on pass, post, and rewrite. The same round confirmed that Claude's, Codex's, and agy's corpora did not change.
    - Round 2 (APPROVE): no further findings.
- PR 2f's revised design (for today's main, against the approved design of 2026-11-04): Codex, APPROVE, no findings. It drops the three-way `paths` field for `pathResolution` and fixes the relative `docs/agents/` exemption first (#550).
- PR 2f's own checks: 24 mutations of its decisions. Two survived: one was a check that could never fail (a cwd that resolves to `""`), removed; the other, an unresolved path's formatting, got a test that pins it.
- The port of Pi's path resolution (`internal/pipath`, part of PR 2f) was written by Codex from a brief, and reviewed by Claude and by an independent reviewer (a separate Claude session), each claim checked against Pi 1.4.0's own `resolveToCwd`:
    - Round 1 (REVISE, 3), found by a differential fuzz of the port against Pi:
        - A `file:` URL with an empty segment before a dot segment resolved to another file than Pi writes: the URL parser keeps an empty segment, so a later `..` removes it (`file:///w/docker-compose.yaml//..` is `/w/docker-compose.yaml`), where `path.Clean` dropped it first (`/w`), which the files guard passed. A plain URL now has no empty segment; the URL is refused otherwise.
        - The corpus had no such case: it now holds them, their plain-path forms, and every path of one to three segments among a name, an empty segment, and the dot segments, plain and percent-encoded (1,425 cases).
        - The freshness test skipped where `pi` is a mise shim; it now follows the shim. It still skips where Pi 1.4.0 is not installed: a different Pi version is checked where Pi runs, by PR 4's installer and doctor, since the sandbox image pins another Pi.
    - Round 2 (APPROVE): the fixed port matched Pi on 3.8 million fuzzed cases, and the new corpus fails the round 1 code on 10 cases, 3 of them from the segment grid alone. Its one suggestion went to PR 4: the shim checks Pi's version when it loads.
- The relative `docs/agents/` exemption, narrowed after PR 2e.2. Found while revising PR 2f's design for today's main, and reproduced on the old guard and on main's binary: the exemption held on every line, so `/w/x`, a newline, and `docs/agents/y.yml` passed, which the old guard blocked. It now holds only where a path starts, inside the same fix ID. The revised PR 2f design, this change included, was reviewed by Codex: APPROVE, no findings.
- PR 2e.2 (the files guard's relative `docs/agents/`, a guard that panics) code reviews (Codex). Each finding was reproduced by a mutation and adopted:
    - Round 1 (REVISE):
        - The registry passed a binary-only fix whose Go test was renamed so that Go no longer ran it, since it only looked for the ID in the file. It now finds the test function as Go runs it (`func TestXxx(t *testing.T)`) and the ID in its body.
        - The answers do not show a block's rule, so the panic test let a changed `hook.failed` through. `failedOutcome` is now pinned directly.
    - Round 2 (APPROVE): no further findings.
- Plan reviews of PRs 2e.2 to 2e.4 (Codex), rounds 1 to 3 (REVISE): no finding on 2e.2's part; the findings on 2e.3 and 2e.4 are recorded with those PRs.
- PR 2e (old scripts' bugs) code reviews (Codex). Each finding was reproduced and adopted:
    - Round 1 (REVISE):
        - Where the fixed script's answer was the old one's but its noise was not, the run kept the old noise ID (`field-file-path-negative`: `pass-diagnostic`, though the fixed guard passes silently). The fixed script is now the reference for every run it applies to: its noise always, and fixes exactly when its answer differs.
        - The tests that run the old scripts failed on native Windows (a file name with a newline, a POSIX PATH). They are now POSIX-only; the pure ones run everywhere.
    - Round 2 (REVISE):
        - A derived input was refused whenever its base held a fixed record, even one that changed only the noise. A base is now refused only when its difference names a fix.
        - The formatter's reference test looked for jq on the parent's PATH, but ran the script on a PATH without it. jq is now linked into the test's own bin.
    - Round 3 (APPROVE): no further findings.
- PR 2e (old scripts' bugs) plan reviews (Codex). Each finding was adopted:
    - Round 1 (REVISE):
        - `notebook_path` as a later `//` candidate could still go unchecked (`file_path:""`), and swapping the order would let a blocked `file_path` pass. It is now checked on its own, with tests both ways.
        - Earning a fix alone missed fixes that act together (`notebook_path:"--x.yml"` needs both). Fixes are found by leaving each out of the full set, after noise normalization; a run holds a set of IDs.
        - The 2a generator cut a reason at the last `BLOCKED:`. It now reads from the first one after the known diagnostics, with no fix ID.
    - Round 2 (APPROVE): no further findings.
- PR 2f (Pi; designed as 2e) design reviews (Codex), approved in round 3 and held for PR 2e:
    - Round 1 (REVISE): the formatter split Pi's one path on newlines, and could format another file; a broken shim exchange followed the hook's failure mode, where the plan blocks every pre hook.
    - Round 2 (REVISE): "reading lines is never laxer" failed on a `-` line, which stopped the old guard. That bug is now fixed for every harness (PR 2e), so reading lines is never laxer again.
    - Round 3 (APPROVE).
- PR 2d code reviews (Codex). Each finding was reproduced and adopted:
    - Round 1 (REVISE):
        - The Codex reader took `"decision":""` beside a valid deny as a block; Codex cannot deserialize it and fails open. The reader now rejects any present `decision` other than `approve` or `block`.
        - agy's success check decoded the whole payload into float64s, so an unused `1e400` failed it and the formatter did nothing. `x-success` is now a member and its values, read as written; the JSON acceptance test now runs on every harness and event.
    - Round 2 (APPROVE): no further findings.
- PR 2d design reviews (Codex). Each finding was adopted:
    - Round 1 (REVISE):
        - The `ProjectLocator` read paths as text: a symlink could lead a file out of its workspace, and a relative path could follow a changed directory. Files and workspaces are now resolved physically, the directory and the real path go together, and a relative or unresolvable path is not formatted.
        - A failed agy edit was still formatted. `x-success` now reads the post payload, and no post hook runs after a failed call.
        - The conformance suite wrote the first `x-ir` candidate, which added a member instead of changing the tool's own. It now writes each tool's real member, from its own list, and checks that none is added.
        - The Codex reader took any `deny` as a block. Each reader now follows its harness's rules, the reason included, with negative tests.
    - Round 2 (REVISE):
        - The Codex reader still took `deny` with `updatedInput` as a block; it now ports every rule of `parse_pre_tool_use`.
        - NotebookEdit was in the scope but not in the member list, and its files-guard cell would have expected a block the old guard never made. Support is now per tool; that cell is `degraded` and pinned.
    - Round 3 (APPROVE): no further findings.
- PR 2c code reviews (Codex). Each finding was reproduced and adopted:
    - Round 1 (REVISE):
        - On Windows, Claude's rtk through mise was refused; the separator test and the launcher's name (`PureWindowsPath.as_posix()`) now follow the OS.
        - `base` alone could carry another scenario's answer; a derived scenario must now be its base plus one unused integer member, in the same environment.
        - An integer and a double compared as two doubles; they now compare exactly.
        - Recording jq's errors as one marker could rewrite a notice body; only the jq lines outside the protected notices are.
    - Round 2 (APPROVE): no further findings.
- PR 2c design reviews (Codex). Each finding was reproduced on the scripts and adopted:
    - Round 1 (REVISE):
        - Go's `exec.LookPath` cleans `link/..` before the kernel resolves it, so it can run another program than the scripts did. The binary now searches PATH as `shutil.which` and bash do, and never runs a program found through a relative entry.
        - Reading rtk's command and answering `allow` turned an rtk `deny` into an allow on Codex. rtk on Claude and Codex is now a delegate whose answer is edited as the scripts edit it, and the rewrite codec moves to 2d.
        - Replay could not see a command run in another cwd or environment, so each program's cwd and environment are recorded, and the port cannot change them.
        - The formatter's bash and jq diagnostics needed their own IDs, with bash 5 pinned.
    - Round 2 (partial): a NUL warning can follow a notice or stand with none after it. Warnings are now taken off wherever they stand.
    - Round 3 (REVISE):
        - Warning text that bash rebuilt by dropping NULs inside a notice would have been cut, so the notices are now built from the recorded output and protected.
        - A fake that reads its stdin would eat the formatter loop's remaining paths, so only rtk's fake reads it.
        - Canonical JSON rounds big integers, so integers now compare exactly.
    - Round 4 (APPROVE): no further findings.
- PR 2b code reviews (Codex). Each finding was reproduced on the scripts and adopted:
    - Round 1 (REVISE): the corpus normalizer refused two real blocks, a reason over two lines and `guard-codex.sh`'s own NUL warning; now only leading warnings are taken off. A caller's `PYTHONINTMAXSTRDIGITS` changed what the command guard did with 4,301 digits; the scripts now inherit nothing but `PATH`. No test caught a guard that skipped a tool no definition maps; the corpus and the unit tests now run the guards under such tools.
    - Round 2 (REVISE): a reason that quotes bash's NUL warning could still lose its first `BLOCKED:` line to the strip; a warning is now only a line that names one of the scripts.
    - Round 3 (APPROVE): no further findings.
- PR 2b design reviews (Codex). Each finding was checked against the scripts first and adopted:
    - Round 1 (REVISE): Codex mapped only `command`, which turns some blocks into passes; Python's `json` reads `NaN`; the order of bash's NUL dropping, newline trimming, and the empty test; the legacy run apart from the outcome; real-process runs, exit 64 for an unknown argument, and the tests not ported.
    - Round 2 (REVISE): replacing invalid UTF-8 does not always side with the block (cp932 reads `81 40` as a space); tolerances contradicted an exact match, so each run records a difference ID and the binary's expected answer; a Codex block is compared on stdout, since `guard-codex.sh` moves stderr there.
    - Round 3 (REVISE): unreadable input blocking adopted as the review item's decision, stated as a deliberately strict condition. A NUL inside a non-string content stays escaped, as jq prints it. The reference Python is pinned to 3.14 and checked to be the one the wrapper picks. The strict reader keeps numbers as text and checks depth itself. The payload corpus runs each `basename` flavor.
    - Round 4 (APPROVE): no further findings.
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
