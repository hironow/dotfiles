# ADR 0087 — `just deploy` registers declared remote MCP servers with every agent

- **id**: ADR-0087
- **title**: `just deploy` registers declared remote MCP servers with every agent
- **status**: Proposed
- **date**: 2026-11-21
- **decided-date**: —
- **decision-maker**: Hiroto N.
- **decision-maker-contact**: @hironow
- **author**: Claude Code (owner session, Windows)
- **author-contact**: @hironow
- **supersedes**: part of [ADR-0026](0026-antigravity-cli-instruction-layer.md) Decision 3 (MCP only: dotfiles now asks Antigravity's own CLI to add the declared servers)
- **superseded-by**: none
- **related**: [0048](0048-required-claude-plugins.md), [0049](0049-headroom-mandatory-base-tooling.md), [0051](0051-adopt-decision-queue-for-new-records.md), [0056](0056-common-claude-plugin-set.md), [0057](0057-shared-plugins-need-no-per-home-settings.md)
- **consultation-trace**: the owner's choices in a Claude Code session on 2026-11-20 and 2026-11-21 (see "Consultation")

## Plain summary

The README listed MCP servers to add by hand, and only for Claude Code.
Now `dump/harness/mcp-servers.json` declares them, and `just deploy` adds them to Claude Code, Codex, Pi and Antigravity.
A server that needs an API key is never added: deploy prints how to set it up.
A server that needs a browser sign-in is added where the agent lets a sign-in wait for first use; Codex signs in the moment a server is added, so Codex gets the command instead.

## Context

- The README's `## MCP` section held `claude mcp add` lines for deepwiki, bun, cloudflare docs, vercel, livekit docs, openai docs, google-dev-knowledge, aws knowledge, k6 and jaeger. On 2026-11-20 each endpoint answered an MCP `initialize` POST:
    - deepwiki, bun, cloudflare docs, openai docs and aws knowledge answered 200 with no key;
    - livekit docs answered 200 only with a trailing slash (`/mcp/`; without it, 308);
    - vercel answered 401 (OAuth);
    - google-dev-knowledge needs an `X-Goog-Api-Key` header;
    - Jaeger v2 moved its MCP endpoint to `http://localhost:16686/api/ai/mcp/` (jaegertracing/jaeger#9657);
    - k6 runs as a local podman stdio command.
- On this host, the servers were spread unevenly: plain `claude` (`~/.claude.json`) had deepwiki and nexlev; each Claude home had only headroom (ADR 0049); Codex had deepwiki, nexlev, linear, playwright and node_repl; Pi and Antigravity had none.
- Claude Code plugins already carry some servers under their own names: context7, cloudflare (`mcp.cloudflare.com`, OAuth) and vercel (`mcp.vercel.com`, OAuth, in `vercel@claude-plugins-official`).
- Each agent CLI adds and removes servers itself: `claude mcp add --scope user`, `codex mcp add --url`, `pi mcp add --url`, `antigravity mcp add`. Only some can list as JSON, so the registry is read from the file the CLI owns.
- `codex mcp add` on an OAuth server starts the browser sign-in at once and waits (codex-rs `run_add`; no flag skips it). Pi and Antigravity only write the entry.
- The vercel plugin's hooks send usage telemetry to `telemetry.vercel.com` unless `VERCEL_PLUGIN_TELEMETRY=off` (vercel/vercel-plugin `hooks/src/telemetry.mts`).
- ADR 0026 Decision 3 says dotfiles does not sync Antigravity's settings or MCP, because writing them would clobber state that Antigravity owns.

## Decision

The owner's choices are adopted as these requirements (MUST):

- D1: `dump/harness/mcp-servers.json` MUST declare the remote MCP servers that need no secret: deepwiki, bun, cloudflare-docs, livekit-docs, openaiDeveloperDocs, aws-knowledge-mcp-server, context7, cloudflare and vercel, each with an `https` URL.
- D2: `just deploy` (`just agent-mcp-install`) MUST register each declared server with every Claude home and plain `claude`, Codex, Pi and Antigravity, through that agent's own `mcp add` / `mcp remove`. It MUST NOT edit an agent's file by hand. It MUST NOT touch or remove a server the declaration does not name. A server at another URL is removed, then added.
- D3: A server that a Claude plugin carries (`claude_plugin`) MUST be left to that plugin in Claude Code. A server that needs a sign-in (`sign_in`) MUST NOT be added to Codex by a run; the run prints the `codex mcp add` command instead.
- D4: A server that needs a secret (google-dev-knowledge) MUST NOT be registered and its key MUST NOT pass through dotfiles. A run prints its setup steps, once, and the `mcp add` command for each agent that lacks it.
- D5: `vercel@claude-plugins-official` MUST be in the shared plugin set, with `VERCEL_PLUGIN_TELEMETRY=off` in the shared Claude settings env.
- D6: A registry that cannot be read MUST stop that agent with a WARN, never count as empty. A CLI that is not on PATH MUST be skipped with an INFO line.

## Options Considered

| Option | What it does | Benefit | Cost | Result |
| --- | --- | --- | --- | --- |
| A: declare the servers; deploy adds them through each CLI | D1 to D6 | Every agent gets the same servers; nothing secret is stored | One more deploy step; a sign-in per agent for OAuth servers | Chosen |
| B: keep the README snippets | No code | — | Only Claude Code gets them, by hand, and the snippets went stale (livekit, jaeger) | Rejected |
| C: write each agent's file directly | No CLI calls | Fast | Races running sessions; clobbers state each CLI owns (the reason for ADR 0026 D3) | Rejected |
| D: also register stdio servers (playwright, chrome-devtools) and headroom for every agent | More tools everywhere | — | Needs pinned `bunx` commands and the LiteLLM decision for headroom first | Not now (owner) |

## Consequences

- **Positive**: Claude, Codex, Pi and Antigravity get the same documentation servers on every machine. The README no longer holds snippets that go stale.
- **Negative**: OAuth servers need a sign-in once in each agent, and in Codex by hand. A run prints INFO lines for google-dev-knowledge until the owner sets it up. The vercel plugin brings third-party hooks (with telemetry switched off).
- **Neutral**: linear, nexlev and the stdio servers stay where they are. `just deploy` on each machine is the owner's step.

## Reversal

none

## Consistency with other decision records

All ADRs 0001 to 0086 were searched for `MCP`; the matches were read for contradiction, duplication, misreading, false relation and mistaken relationship.

- 0026: Decision 3 forbids syncing Antigravity's settings and MCP, because a raw write would clobber them. This ADR still writes no Antigravity file; it asks `antigravity mcp add` for named servers and leaves every other entry alone. Recorded as a partial supersession of D3 (MCP only) so the boundary is explicit. On acceptance, 0026's status line says so.
- 0049: headroom's MCP server stays a separate step for Claude homes only. No conflict.
- 0048, 0056: vercel joins the shared plugin set from claude-plugins-official, which tracks latest. No conflict.
- 0057: the vercel plugin declares no `userConfig`, so it needs no per-home setting. No conflict.
- 0015, 0038, 0073, 0085 mention MCP in passing (inspector UIs, skill names, plugin contents, a check name). Not related.
- 0051: this ADR is registered in the decision queue.

## Consultation

- 2026-11-20 (AskUserQuestion): after the endpoint check, the owner chose to install deepwiki, bun, aws and livekit, openai docs and cloudflare docs automatically, vercel as a plugin, guidance only for google-dev-knowledge (and to drop it from the README), and claude, codex, pi and agy as the agents.
- 2026-11-21 (AskUserQuestion): asked which servers on this host but not in the declaration to add; the owner chose context7, and cloudflare and vercel; stdio servers not now; headroom waits for the LiteLLM decision.
- The plan passed an independent review (Antigravity, Gemini Pro), whose seven findings were applied.
