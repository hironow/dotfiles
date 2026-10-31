# headroom — the context optimization layer

headroom is mandatory base tooling, next to [rtk](./rtk.md). mise installs it
(`pypi:headroom-ai`, extras `proxy,code`). rtk compresses what a *command*
prints to your terminal; headroom compresses what reaches the *model*.

## Two routes

- **MCP server (every Claude home)**: `just headroom-mcp-register` (and
  `just deploy`) registers `headroom mcp serve` via `claude mcp add --scope user`.
  It exposes `mcp__headroom__headroom_compress`, `…_retrieve`, and `…_stats`. If
  the server is down, only those tools disappear; the session continues.
- **Proxy (`j-cc` and `j-pi` Codex workers only)**: `scripts/jev_headroom.py`
  starts or reuses one local proxy and points only the launched process at it
  (fail-open: if proxy setup fails, the launcher starts without headroom). Plain
  `claude` stays direct so Remote Control keeps working. Verify both headroom
  and rtk together with `just jev-headroom-verify rtk`.

Do not run `headroom wrap claude` or `headroom init`. `wrap` fails closed and
overwrites the `settings.json` env that `just sync-agents` owns (`just doctor`'s
`headroom-routing` check warns if either has run).
