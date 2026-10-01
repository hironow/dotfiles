# 0049. headroom is mandatory base tooling: MCP in every home, the j-cc proxy as its canary, telemetry off

**Date:** 2026-10-01
**Status:** Accepted (operator directive, 2026-09-29; integration and egress
decided 2026-09-29, canary mechanism revised 2026-10-01).

## Context

`headroom` (PyPI `headroom-ai`) is a context-optimisation layer for LLM clients:
a local proxy that compresses what a client sends to the model, an MCP server
offering compression as on-demand tools, a memory store and a metrics dashboard.
The operator ruled that headroom, like [rtk](./0047-rtk-mandatory-base-tooling.md),
is a **base tool of this environment with no option not to use it**, installed
through mise, at the latest stable version — an explicit Class 1 override of the
dependency policy's cooldown.

That turns three questions from preferences into decisions.

**1. How a Claude Code session uses it.** headroom offers three integrations,
and they differ mainly in what breaks when headroom does:

| | the proxy (`ANTHROPIC_BASE_URL`) | the MCP server | `headroom wrap claude` |
|---|---|---|---|
| compresses | every request | what the agent asks it to | every request |
| headroom down | the session fails: a dead endpoint | the tools vanish, the session continues | the session fails, by design |
| Remote Control / managed settings | lost (gated on the direct API) | kept | lost |
| writes sync-owned files | no | no | **yes** — `settings.json`'s env |
| installs extras | no | no | Serena, by default |

**2. What it sends out.** By default headroom emits an anonymised usage beacon,
checks for updates, reports licence state and downloads ML models (huggingface.co,
and ONNX Runtime from cdn.pyke.io). The beacon is ON unless turned off, and
**fails open**: any value of `HEADROOM_BEACON` but the literal `off` uploads.
Measured on 0.38.0 with `headroom telemetry --json`:

| `HEADROOM_BEACON` | `DO_NOT_TRACK` | `beacon_enabled` |
|---|---|---|
| unset | unset | **true** |
| `on` | unset | true |
| `off` | `1` | false |
| `on` | `1` | **false** |
| unset | `1` | false |

So `DO_NOT_TRACK=1` is the stronger control: it overrides an explicit
`HEADROOM_BEACON=on`, while `HEADROOM_BEACON` alone is the one that fails open.
Neither stands in for the other.

**3. What it actually compresses here.** Measured through a real
`headroom_compress` call on 0.38.0 with the installed `proxy,code` extras:

| payload | ratio |
|---|---|
| 700 log lines | **0.009** |
| 700-object JSON array | **0.335** |
| 700-line `ls -la` listing | 1.000 — unchanged |
| repetitive prose | 1.000 — unchanged |

The unchanged rows are the ML route. The server logs `WARNING: Kompress model
not ready; requests will not be compressed`: that route wants `headroom-ai[ml]`
plus a first-run warmup that downloads from huggingface.co.

## Decision

**headroom is installed by mise** (`pypi:headroom-ai`, extras `proxy,code` — not
`all`, which pulls torch) and pinned, like every other tool in
`config/mise/config.toml`.

**The MCP server goes to every Claude home.** `just headroom-mcp-register` (and
`just deploy`) register `headroom mcp serve` through Claude Code's own
`claude mcp add --scope user`, with `CLAUDE_CONFIG_DIR` set per home. Reading the
registry is done by reading `<home>/.claude.json`; every write goes through the
CLI, because that file holds a home's live state and several homes run sessions
at once. The command is `mise x -- headroom mcp serve`: an absolute path breaks
at the next version bump, and a bare `headroom` depends on the PATH of whatever
started Claude Code, which is a snapshot that may predate the install.

**The proxy stays scoped to `j-cc`, and the j-cc proxy IS the canary.**
`scripts/jev_headroom.py` already starts a proxy on a free port per launch,
reuses a ready one, points only the Claude process it starts at it, and treats
every failure as "launch without headroom". The earlier plan was a launchd
KeepAlive proxy in one agent home as a canary; that is **rejected**, because it
would give one machine two mechanisms for one job and the existing one is
already the safer shape — per launch, fail-open, no daemon to go stale. The v2
§3 comparison (cache creation and read tokens, total usage, compression ratio,
latency p50/p95, failure rate, concurrency, a kill drill, a recovery drill) is
measured against THIS proxy. Promotion to "every session through the proxy" stays
an explicit operator decision taken on that data.

**`headroom wrap` and `headroom init` are never run.** `wrap` is fail-closed by
design, writes the `settings.json` env that sync owns, and installs Serena;
`just doctor`'s `headroom-routing` line warns if either has run.

**Telemetry off, on every process, with both switches.** `HEADROOM_BEACON=off`
and `DO_NOT_TRACK=1` in mise's global `[env]`, the shared Claude settings env,
the persisted Windows User env, the MCP registration's own `env` block, and the
proxy process `jev_headroom` starts. The last two matter because Claude Code and
`j-cc` start those processes themselves, so no shell's mise env reaches them.
`just doctor` checks the literals in all three declared places and asks headroom
itself (`headroom telemetry --json` → `beacon_enabled`).

**The remaining allowed egress** is: update checks, licence reporting, and model
downloads (huggingface.co, cdn.pyke.io). The beacon is not allowed.
`HEADROOM_OFFLINE=1`, which would stop all of it, is **not** chosen: it would
also stop the model downloads, and the ML compressors would silently degrade
without a controlled pre-fetch step to replace them.

**The ML gap stays open on purpose.** `headroom-ai[ml]` and its warmup are not
installed, so prose does not compress and structured output does. Closing the gap
means inviting a model download; the structured-output compression that works
today costs no network at all. Any flat canary result on prose-heavy
conversations is to be read as this gap, not as the proxy failing.

### Superseding note on ADR 0047

ADR 0047 states that rtk "answers `permissionDecision: 'allow'` for everything it
rewrites", and calls the wrapper's policy a defence against "blanket
auto-approval". That was true of rtk 0.45.0. It is **not** true of 0.50.0, the
version mise now pins. Measured by feeding real PreToolUse payloads to
`rtk hook claude`:

| typed command | rewritten to | `permissionDecision` |
|---|---|---|
| `ls -la` | `rtk ls -la` | `allow` |
| `grep -rn foo .` | `rtk grep -rn foo .` | `allow` |
| `rg foo` | `rtk rg foo` | `allow` |
| `find . -name x` | `rtk find . -name x` | `allow` |
| `cat /etc/hosts` | `rtk read /etc/hosts` | `allow` |
| `git status --short` | `rtk git status --short` | **absent** |
| `git diff` | `rtk git diff` | **absent** |
| `docker ps` | `rtk docker ps` | **absent** |
| `curl https://example.com` | `rtk curl …` | **absent** |
| `ps aux` | `rtk ps aux` | **absent** |
| `echo hi` | (no answer at all) | n/a |
| `sudo ls` | (no answer at all) | n/a |

0.50.0 auto-approves only its read-only file and search family, and leaves the
decision to the harness for git, docker, curl and ps. **0047's decision stands
unchanged** — the wrapper still strips the field, and without it `ls`, `grep`,
`rg`, `find` and `cat` would still be auto-approved — but its description of the
scope is corrected here, and so is the reading of an empty answer: for `echo` and
`sudo` an empty stdout is rtk declining, the normal case, not a failure.

## Consequences

- Every Claude home gains three tools (`mcp__headroom__headroom_compress`,
  `…_retrieve`, `…_stats`) and the system-prompt cost of their schemas. They earn
  that on structured output and not on prose, which is why the measurements are
  recorded here rather than left to be rediscovered.
- A home created later has no server until `just headroom-mcp-register` runs;
  `just doctor` reports which home is missing it, and `just deploy` fixes all of
  them.
- The egress posture is asserted mechanically: `just ci` pins the literal values
  in every tracked source, and the doctor reads them back off the machine. A
  future headroom that renames either variable shows up as a doctor WARN, not as
  silent uploading.
- `HEADROOM_BEACON` failing open means a typo (`HEADROOM_BEACON=false`) uploads.
  `DO_NOT_TRACK=1` is what stops that, which is why both are set rather than one.
- The proxy's blast radius stays one launcher. Nothing in a plain `claude`
  session depends on headroom being up, so a broken headroom costs compression,
  never a session.
- Pinning the MCP command to `mise x --` means a machine whose live mise config
  does not declare headroom gets no server rather than a wrong one. That failure
  mode is itself detected — see the `mise-config` doctor check.
