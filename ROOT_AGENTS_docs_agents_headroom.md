# headroom — the context optimisation layer

headroom is mandatory base tooling, next to [rtk](./rtk.md). mise installs it
(`pypi:headroom-ai`, extras `proxy,code`). rtk compresses what a *command*
prints to your terminal; headroom compresses what reaches the *model*.

## Two routes, with different blast radius on purpose

**The MCP server: every Claude home.** `headroom mcp serve` is registered by
`just headroom-mcp-register` (and by `just deploy`) through Claude Code's own
`claude mcp add --scope user`, with `CLAUDE_CONFIG_DIR` set per home. It offers
three tools that the agent calls when it needs them:
`mcp__headroom__headroom_compress`, `…_retrieve`, and `…_stats` (the doubled
name is normal MCP namespacing). If the server is down, the tools disappear and
the session carries on. A broken headroom costs a tool, never a session.

**The proxy: `j-cc` only.** `scripts/jev_headroom.py` starts one proxy on a
free port per launch, or reuses one that is ready. It points only the Claude
process it starts at that proxy (`ANTHROPIC_BASE_URL`). Any problem means
"launch without headroom", never "j-cc does not start". A custom base URL turns
off Remote Control, which is why plain `claude` stays direct. This per-launch,
fail-open proxy IS the proxy canary. There is no launchd service, on purpose:
one mechanism, not two.

A j-cc session gets both layers: headroom's proxy for what reaches the model,
and rtk's hook for what its commands print. `just jev-headroom-verify rtk`
checks both together in one session (a proxied request plus rtk's own count).

Do not run `headroom wrap claude` or `headroom init`. `wrap` fails closed by
design and writes the `settings.json` env that sync owns. `just doctor`'s
`headroom-routing` line warns if either one has run.

## What it actually compresses

Measured on 0.39.1 with the installed `proxy,code` extras, through a real
`headroom_compress` call. `just headroom-compress-measure` reproduces this:

| payload | ratio |
|---|---|
| 700 log lines | **0.001** |
| 700-object JSON array | **0.334** |
| 700-line `ls -la` listing | **0.890** |
| repetitive prose | 1.000 — unchanged |

So structured output compresses hard, a columnar directory listing compresses
a little, and prose comes back byte for byte. Keep this in mind when you read a
flat canary result, before you blame the proxy: on prose, a ratio of 1.000 is
the expected answer, not a broken proxy.

The recipe's four payloads are byte-identical on every run
(`tests/unit/test_headroom_compress_measure.py` pins the sha256 of each). That
is the only reason the ratios above still mean something after a bump: re-run
the recipe, and a moved number means the compressor moved, not the input.
Re-run it whenever the pin moves, and correct this table when a number changes.

This doc makes no claim about *why* prose does not compress. The pinned extras
do install an ONNX stack (`onnxruntime`, `transformers`, `tokenizers`), so "the
ML route needs `headroom-ai[ml]`" is not the explanation. The rest is
unmeasured, and a guess in a doc is worse than an open question.

## Egress

Set `HEADROOM_BEACON=off` **and** `DO_NOT_TRACK=1` on every headroom process.
They are set in five places: mise's global `[env]`, the shared Claude settings
env, the persisted Windows User env, the MCP registration's own `env` block, and
the proxy process that `jev_headroom` starts.

There are two switches for two reasons:

- The beacon fails OPEN: any value other than the literal `off` uploads.
- `DO_NOT_TRACK=1` is the stronger of the two. Measured on 0.39.1, it turns the
  beacon off even against an explicit `HEADROOM_BEACON=on`.

`HEADROOM_BEACON=off` on its own is also enough, with no `DO_NOT_TRACK` behind
it. We set both so that neither one is load-bearing.

`just doctor` checks both switches in the shell, in every Claude home's
settings, and in the Windows User env. It also asks headroom itself
(`headroom telemetry --json` → `beacon_enabled`). Update checks, licence
reporting, and model downloads stay allowed; the beacon does not.

Re-measuring after a version bump is safe. `headroom telemetry` only prints the
payload the beacon *would* send, so reading it causes no egress, even in the
one combination that leaves the beacon enabled.

The switches apply to new processes only. A proxy started before a bump keeps
serving its old version until you restart it. So read the switches from the
running process (`ps -Ewww -p <pid>`), not from the config it was launched
with. To find those pids, match `headroom(\.cli)?\s+(proxy|mcp)` against
`ps -axo pid=,command=`. A looser `pgrep -f headroom` misses the real argv
(`python -m headroom.cli proxy`) and also matches the shell doing the search.

In an outage, bypass works per process and needs no sync:

- `JEV_HEADROOM=off j-cc` skips the proxy.
- `claude mcp remove headroom --scope user` drops the tools.

`just headroom-mcp-register` and the next launch restore both.

## After a headroom upgrade

mise pins the version, so upgrades are deliberate. `just doctor` compares what
dotfiles relies on with the installed tool and warns when they differ:

- the `headroom proxy` flags that `jev_headroom.proxy_command` passes;
- the beacon state, as headroom itself reports it;
- whether the MCP registration still matches what `just headroom-mcp-register`
  would write.
