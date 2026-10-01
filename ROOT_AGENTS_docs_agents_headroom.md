# headroom — the context optimisation layer

Mandatory base tooling next to [rtk](./rtk.md), installed through mise
(`pypi:headroom-ai`, extras `proxy,code`). rtk compresses what a *command* puts
on your terminal; headroom compresses what reaches the *model*.

## Two routes, deliberately different in blast radius

**The MCP server — every Claude home.** `headroom mcp serve`, registered by
`just headroom-mcp-register` (and by `just deploy`) through Claude Code's own
`claude mcp add --scope user`, with `CLAUDE_CONFIG_DIR` set per home. It offers
three tools the agent calls on demand, shown as
`mcp__headroom__headroom_compress`, `…_retrieve` and `…_stats` (the doubling is
normal MCP namespacing). If the server is down the tools simply vanish and the
session carries on, so a broken headroom costs a tool, never a session.

**The proxy — `j-cc` only.** `scripts/jev_headroom.py` starts one on a free port
per launch, reuses a ready one, and points only the Claude process it starts at
it (`ANTHROPIC_BASE_URL`). Any problem means "launch without headroom", never
"j-cc does not start". A custom base URL turns off Remote Control, which is why
plain `claude` stays direct. This per-launch, fail-open proxy IS the proxy canary:
there is no launchd service, on purpose — one mechanism, not two.

Do not run `headroom wrap claude` or `headroom init`. `wrap` is fail-closed by
design and writes the `settings.json` env that sync owns; `just doctor`'s
`headroom-routing` line warns if either has run.

## What it actually compresses

Measured on 0.38.0 with the installed `proxy,code` extras, through a real
`headroom_compress` call:

| payload | ratio |
|---|---|
| 700 log lines | **0.009** |
| 700-object JSON array | **0.335** |
| 700-line `ls -la` listing | 1.000 — unchanged |
| repetitive prose | 1.000 — unchanged |

The two 1.000 rows are the ML route, which is OFF here: the server logs
`WARNING: Kompress model not ready; requests will not be compressed`, because
the model wants `headroom-ai[ml]` plus a first-run warmup that downloads from
huggingface.co. That download is egress we have not invited, so the gap is
deliberate: structured output (logs, JSON, search results) compresses with no
network at all, and prose does not compress. Read a flat canary result in that
light before blaming the proxy.

## Egress

`HEADROOM_BEACON=off` **and** `DO_NOT_TRACK=1`, on every headroom process:
mise's global `[env]`, the shared Claude settings env, the persisted Windows
User env, the MCP registration's own `env` block, and the proxy process
`jev_headroom` starts. Two switches because the beacon fails OPEN — any value
but the literal `off` uploads — and because `DO_NOT_TRACK=1` is the stronger of
the two: measured on 0.38.0, it turns the beacon off even against an explicit
`HEADROOM_BEACON=on`.

`just doctor` checks both in the shell, in every Claude home's settings and in
the Windows User env, and asks headroom itself
(`headroom telemetry --json` → `beacon_enabled`). Update checks, licence
reporting and model downloads remain allowed; the beacon does not.

In an outage, bypass is per process and needs no sync: `JEV_HEADROOM=off j-cc`
skips the proxy, and removing the MCP server (`claude mcp remove headroom
--scope user`) drops the tools. Both are restored by
`just headroom-mcp-register` and the next launch.

## After a headroom upgrade

mise pins the version, so upgrades are deliberate. `just doctor` compares what
dotfiles relies on with the installed tool and warns when they part: the
`headroom proxy` flags `jev_headroom.proxy_command` passes, the beacon state by
headroom's own account, and whether the MCP registration still matches what
`just headroom-mcp-register` would write.
