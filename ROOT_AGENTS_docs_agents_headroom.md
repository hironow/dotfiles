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
