# Launching Claude Code and Pi with Jev

`j-cc` and `j-pi` query Jev with your initial prompt before launching Claude Code and Pi.
From Jev's response, they select the Sonnet 5.5 effort level for the session and workers, and the model and reasoning effort for Codex workers.
Normal `claude` and `pi` behavior is unchanged.

## Initial setup

Run `just deploy` and open a new shell.
If Pi reports missing extensions, run `just pi-extensions-install`.
`just deploy` does not update installed Pi extensions; update them with `just update-all` (which runs `pi update --extensions` internally).
Pi extensions and their dependencies are exempt from the 7-day npm quarantine (`just harden-env` writes `min-release-age=0` to `~/.pi/agent/npm/.npmrc`).
On machines where updates stop with `ETARGET`, run `just harden-env` and retry.
If extension versions drift across machines, the same configuration can fail on one machine and succeed on another.

Store the TypeSafe API key in `~/.config/jev/env` as `TYPESAFE_API_KEY=...`.
It is read on every launch, so edits take effect without reopening the shell.
If the environment variable `TYPESAFE_API_KEY` (or `TYPESAFE_AI_API_KEY`) is set, it takes precedence.
Worker hooks and `codex-jev` run in an environment with key variables stripped, so they can only read the key from this file.
On machines without `~/.config/jev/env`, Jev falls back to `~/.env` (if `~/.config/jev/env` exists but is unreadable, it does not fall back to `~/.env`).

It lives under `~/.config` because of the Codex Windows sandbox.
Every time you use Codex, the sandbox reapplies `CodexSandboxUsers` read permissions to almost every item directly under the home directory.
Exclusions are only a fixed list such as `.ssh`, `.aws`, and `.config`, which does not include `~/.env`.
Because model-chosen commands run inside the sandbox, Jev refuses to read a key file that has this permission.

```sh
mkdir -p ~/.config/jev
grep '^TYPESAFE_API_KEY=' ~/.env > ~/.config/jev/env   # When migrating from ~/.env
chmod 600 ~/.config/jev/env                              # macOS and Linux
```

Jev does not read key files that others can read.
On macOS and Linux, set permissions to 0600 so only the owner can read and write it.
On Windows, both the owner and every access-control entry must be yourself, SYSTEM, or Administrators.
`OWNER RIGHTS` (`S-1-3-4`) permissions are evaluated as [permissions for the current owner](https://learn.microsoft.com/en-us/windows-server/identity/ad-ds/manage/understand-security-identifiers#well-known-sids).
If the owner is anyone else, Jev rejects the file even if `OWNER RIGHTS` is present.
Files created under `~/.config` usually satisfy this with default permissions.
If not, Jev prints `~/.config/jev/env must be owned by you` at launch; inspect permissions with `icacls`, remove inheritance, and grant access only to yourself.

```powershell
icacls "$HOME\.config\jev\env"                                             # List permissions
icacls "$HOME\.config\jev\env" /inheritance:r /grant:r "${env:USERNAME}:F"  # Remove inheritance and grant access only to yourself
```

Never commit the key to a repository.
Your prompt is sent to Jev, so do not include passwords or other secrets in it.

## Usage

Run these inside your working repository from zsh on macOS or Linux, or PowerShell on Windows.

```sh
j-cc 'fix the failing parser tests'
j-pi 'fix the failing parser tests'
```

A new session does not launch without a prompt.
Normal launch settings for model, permissions, approvals, and plan review rules are unchanged.
Even if Claude Code hits a usage limit, it never switches to another account or pay-as-you-go billing.

### Resuming a previous session

`-c` (`--continue`) and `-r` (`--resume`) have the same meaning and syntax as the same flags in Claude Code and Pi.

```sh
j-cc -c                                   # Continue the most recent session in this directory
j-cc -c 'now fix the error handling too'          # Continue and send a prompt
j-cc -r                                   # Pick from a list
j-cc -r <session ID or name> 'your request'
j-pi -c 'your request'
j-pi -r                                   # Pick from a list
```

Because Claude Code's `-r` reads the immediately following word as a session ID or name (the list filter), `j-cc -r` parses it the same way.
Pi's `-r` takes no value, so any word after `j-pi -r` is the prompt.
Resumed sessions receive the same model, system prompt rules, and headroom proxy as new sessions. `j-pi` also passes the worker key.
Resumed `j-cc` sessions do not attach worker definitions or hooks (see "Claude Code" below).
In resumed sessions, Claude Code ignores `--agents` definitions and reads only `--settings` hooks (verified on this machine on 2026-11-18).
If hooks alone remained, every worker launch would be rewritten to a nonexistent `worker-<effort>` and fail.
Therefore, subagents in resumed sessions use Claude Code's default definitions, and Jev does not select worker effort or `codex:codex-rescue` model and effort.
Resuming with plain `claude -c` or `pi -c` does not attach the model, rules, or proxy either.

If a prompt is provided, Jev selects the effort level just like a new session.
If no prompt is provided, Jev is not queried and the session resumes at `medium`.
The previous session's effort level is not carried over.
Other flags (such as `--fork-session`) are not accepted; invoke `claude` or `pi` directly when you need them.

## How effort levels are selected

Jev is queried once at launch (not when resuming without a prompt).
The two questions below are combined into a single call.

- **Difficulty** (Score, 3 levels): from simple changes to cross-service work with an unknown cause
- **Strict structure** (Noul): whether format errors (such as a JSON schema) would break consumers

The repository code maps the answer to an effort level.
Following [Anthropic's Sonnet 5.5 recommendations](https://platform.claude.com/docs/en/build-with-claude/effort#recommended-effort-levels-for-claude-sonnet-5-5), clear tasks use `medium`, while hard tasks and tasks needing strict structure use `high`.
`xhigh` and `max` are not selected until evaluations confirm an improvement.

| Condition | Effort level |
| --- | --- |
| Strict structure probability is 0.7 or higher | `high` |
| Difficulty confidence is below 0.5 (Jev cannot judge) | `medium` |
| Difficulty score is 1.5 or higher (near the top tier) | `high` |
| Otherwise | `medium` |

If Jev is unreachable or its response cannot be parsed, it also falls back to `medium`.
NaN, infinity, and values that overflow when converted to a number are rejected.
If strict structure probability is validly 0.7 or higher, `high` is selected even if the difficulty value is invalid.
Thresholds live in `scripts/jev_core.py`, and the Pi extension uses the same values (`tests/unit/jev_effort_cases.json` verifies parity).

## Per-worker selection

Each worker launch also sends its prompt to Jev to reselect the effort level.
The decision rules and the `medium` fallback when Jev is unreachable are the same as at launch.

### Pi

In Pi launched with `j-pi`, each time `subagent` launches a worker, it sends `task` to Jev.
It appends `:medium` or `:high` to the parent's Sonnet 5.5 model name to launch the worker.
For launches with an explicit model, the suffix is added only if it is a Sonnet 5.5 provider with no suffix.
Other models, launches with suffixes such as `:low`, children inside `workflowScript`, and management operations are left untouched.

The API key is passed to the extension once when Pi starts, and the extension deletes it from the environment right after loading.
The key is not passed to the bash tool or to worker child sessions.
If the extension is not installed, the key is not passed to Pi and worker selection is skipped.

### Claude Code

Claude Code's Agent tool has no effort parameter; a subagent's effort is fixed per definition.
So `j-cc` injects the following two items only for new sessions (via `--settings` and `--agents`, without changing global config; see "Resuming a previous session" above for why they are omitted on resume).

- `worker-medium` and `worker-high`: worker definitions differing only in effort
- `PreToolUse` hook (`scripts/jev_claude_hook.py`): rewrites default worker launches to whichever definition Jev selected

Only launches whose `subagent_type` is `general-purpose`, `worker`, or unset are rewritten.
`Explore`, custom agents, and launches with an explicit `model` are left untouched.
Because the hook returns no permission decision, approval prompts are not bypassed.
On failure, nothing is changed and the launch proceeds as Claude sent it.
Because Claude Code runs hooks via Git Bash even on Windows, the hook command uses `/` separators in its path.

## Codex worker model and effort

When Codex is invoked as a worker from `j-cc` or `j-pi`, Jev selects a `gpt-6` series model and reasoning effort for each launch.
Selection follows [OpenAI's model guide](https://learn.chatgpt.com/docs/models?surface=cli).

| Model | Best suited for | Base effort |
| --- | --- | --- |
| `gpt-6-astra` | The hardest, ambiguous tasks requiring deep analysis or large deliverables | `low` |
| `gpt-6.1-sol` | Complex tasks where time and cost also matter (near-Astra capability at a lower unit cost) | `medium` |
| `gpt-6-luna` | Clear, iterative tasks (extraction, classification, conversion, scoped edits) | `high` |

Sol uses 6.1 (`gpt-6.1-sol`).
6.0 (`gpt-6-sol`) is no longer recommended by OpenAI and is not used.

Jev is asked four questions in one call: the same two questions as for effort level, plus whether the task is "clear and iterative" and whether it "requires judgment across multiple steps to the end".

| Condition | Selection |
| --- | --- |
| Difficulty confidence is below 0.5, or no response | `gpt-6.1-sol` / `medium` |
| Difficulty is 1.5 or higher, multi-step is 0.7 or higher, and confidence is 0.8 or higher | `gpt-6-astra` / `low` |
| Difficulty is 1.5 or higher (does not match above) | `gpt-6.1-sol` / `high` |
| Clear and iterative is 0.7 or higher (not hard) | `gpt-6-luna` / `high` |
| Otherwise | `gpt-6.1-sol` / `medium` |

If strict structure is needed (0.7 or higher), Sol steps up to `high` and Astra steps up to `medium`.
Because Astra costs far more per unit than Sol, it is chosen only when confidence is high.
Thresholds live in `scripts/jev_core.py` and are pinned against real cases in `tests/unit/jev_codex_cases.json`.

### From Claude Code

`--model` and `--effort` are prepended to the `codex:codex-rescue` prompt, and the plugin wrapper passes them directly to Codex.
If the prompt already contains `--model` or `--effort`, those take precedence and nothing is changed.
`--effort` is capped at `xhigh`, which the plugin accepts.
This path requires the Codex plugin (`codex:codex-rescue`) to be installed in Claude Code.
`just deploy` installs the tag-pinned version into every existing Claude home (declared in `dump/harness/claude-plugins.json`, ADR 0048, ADR 0056).
`just doctor`'s `claude-plugins` check reports any home missing it; install with `just claude-plugins-install`.

### From Pi

Pi's built-in `codex-exec` and `codex-exec-writer` cannot override the model (arguments are hardcoded and `config.toml` is not read).
Instead, `just deploy` generates the following two definitions in `~/.pi/agent/agents/`.

- `codex-jev`: read-only (equivalent to `codex-exec`)
- `codex-jev-writer`: can write to the workspace (equivalent to `codex-exec-writer`)

Both query Jev right before execution and run `codex exec -m <model> -c model_reasoning_effort=<effort>` (sandbox and other flags match the built-ins).
Because absolute paths to Python and the script are embedded in the definitions, `sh` is not needed and the same definitions work on Windows.
Because selection runs at execution time, it also applies to children inside `workflowScript`.
In Pi launched with `j-pi`, calling `codex-exec` or `codex-exec-writer` directly from `subagent` automatically redirects to these two.
You can verify the chosen model from the first line of stderr (`Jev: codex gpt-6.1-sol / medium (read-only)`), saved in `external-*.stderr.log` for Pi runs.

## Pi providers and failover

Pi uses authenticated providers in order: GitHub Copilot, Anthropic (Claude Code subscription), and OpenRouter.
Cursor is never used even if logged in.
Because Pi does not pass tools to the Cursor provider (it replies `Tool not available`), it cannot launch workers, run commands, or edit files there.
The Claude Code subscription is reserved for Claude Code itself, so it ranks behind other subscriptions.
OpenRouter is pay-as-you-go, so it is last.

Failover to the next provider happens only on a 429 status or a known mechanical limit error.
Vague text like "quota exceeded" or statuses that conflict with auth or server errors do not trigger failover; the original error is shown instead.
If no authenticated fallback provider exists, the original error is shown.

## Pi compaction and memory (pi-blackhole)

The `pi-blackhole` extension handles Pi conversation compaction and memory creation.
It replaces Pi's `/compact`, and background workers (observer, reflector, dropper) build memories.
Because `pi-observational-memory` and `pi-vcc` conflict and prevent loading, the installer removes `pi-observational-memory`.

Worker models are configured per machine in `~/.pi/agent/pi-blackhole/pi-blackhole-config.json`.
Because authenticated providers differ per machine, dotfiles does not distribute this file.
If no worker model is set and `sessionFallback` stays at its default `false`, memory creation is silently skipped (compaction still runs).
To run with the session's model, set `"sessionFallback": true`.
That uses main-model tokens for memory creation and makes its prompt cache more likely to break.
To delegate to cheaper models, set provider and model in `observerModel`, `reflectorModel`, and `dropperModel` (see "Quick start config" in the upstream README).

To verify, restart Pi, converse for about 15000 tokens, and run `/blackhole-memory view` to check that memories are recorded.

## headroom (j-cc and Codex workers)

`j-cc` routes requests from the launched Claude session and its workers through the headroom proxy to compress content sent to the model.
`ANTHROPIC_BASE_URL` is passed only to that Claude process.
Because pointing `ANTHROPIC_BASE_URL` anywhere other than `api.anthropic.com` breaks Claude Code Remote Control, plain `claude` connects directly.
Codex workers (`codex-jev`) launched from `j-pi` also use this proxy (`codex exec` receives `-c openai_base_url=http://127.0.0.1:<port>/v1` and `OPENAI_BASE_URL` on the command line rather than via a config file because of `--ignore-user-config`).
`j-pi` itself does not route through the proxy.
`pi-background-tasks` rejects any Anthropic URL other than the official `https://api.anthropic.com`.
The GitHub Copilot path re-resolves its endpoint from the login token each time, so the extension cannot redirect it.
headroom is installed via mise (`pypi:headroom-ai`).

Each time `j-cc` or a Codex worker starts, it prepares the proxy in this order:

1. If `/health` on the port recorded in `~/.cache/jev/headroom.json` reports a ready headroom proxy, reuse it
2. Otherwise, start `headroom proxy --host 127.0.0.1` on a free port (with beacon off) and record the port once ready; append output to `~/.cache/jev/headroom-proxy.log`
3. If headroom is missing or fails to start, report it and launch without headroom

`j-pi` runs the same setup at launch so Codex workers have a ready proxy (without routing Pi's own traffic through it).
Every time `j-cc` or `j-pi` starts, it prints the dashboard URL (`http://127.0.0.1:<port>/dashboard`), and opens it in a browser only when that launch started a new proxy.
To suppress opening the browser, launch with `JEV_HEADROOM_DASHBOARD=off` (the URL is still printed).
To open it later, use `just headroom-dashboard` (plain `headroom dashboard` opens the default port 8787, which is not this proxy's dashboard).

The proxy stays running after `j-cc` exits and is reused on subsequent launches (the few-second startup happens only once).
To disable it, launch with `JEV_HEADROOM=off`.
If the proxy stops mid-session, that session loses model access, so restart `j-cc` (which starts a new proxy).
Starting two `j-cc` sessions nearly simultaneously may start two proxies (each uses its own).

The headroom version is pinned (`config/mise/config.toml`) and bumped manually.
After bumping, verify two invariants with `just doctor`.
`headroom-telemetry` checks that headroom itself reports beacon off (`headroom telemetry --json`).
`headroom-cli` checks that `headroom proxy --help` lists the flags passed by `jev_headroom.proxy_command`.
`/health`'s response shape is checked by `headroom-proxy` when a proxy is running (if the shape changes, `j-cc` waits for the proxy and then launches without headroom).
Verify the Codex worker path with `just jev-headroom-verify`.

`headroom init` and `headroom wrap` write the proxy route directly into Claude and Codex configs.
We do not use them because plain `claude` and `codex` would stop working without the proxy and Claude would lose Remote Control.
If they are written, `just doctor`'s `headroom-routing` check flags them; remove with `headroom unwrap claude` or `headroom unwrap codex` and run `just sync-agents`.

To stop the proxy, do not rely on the state file; find your headroom proxy process by command line and kill it.
Any `j-cc` session using a stopped proxy loses model access.

```sh
pgrep -u "$USER" -af 'headroom proxy --host 127\.0\.0\.1'   # macOS and Linux: list
kill <PID>
```

```powershell
# Windows: two python.exe processes run under headroom.exe, so kill the parent tree
Get-CimInstance Win32_Process | Where-Object CommandLine -match 'headroom.*proxy --host 127\.0\.0\.1' | Select-Object ProcessId, ParentProcessId, Name
taskkill /T /F /PID <ProcessId of headroom.exe>
```

### What headroom compresses (measured)

Measured by calling `headroom_compress` directly on headroom 0.40.0 with the `proxy,code` extras.
Re-run the same measurement with `just headroom-compress-measure`.

| payload | ratio |
|---|---|
| 700 log lines | **0.001** |
| 700-object JSON array | **0.334** |
| 700-line `ls -la` listing | **0.890** |
| repetitive prose | 1.000 — unchanged |

Structured output shrinks heavily, aligned listings shrink slightly, and prose returns unchanged.
Even if the canary result is flat, a 1.000 ratio for prose is the expected result, not a proxy failure.

The 4 inputs used for measurement are identical byte sequences every time (`tests/unit/test_headroom_compress_measure.py` pins each sha256).
So if the numbers move after a version bump, the compressor changed.
Re-measure after bumping, and update this table if the numbers change.

We do not speculate here on why prose does not shrink.
Because the pinned extras include the full ONNX stack (`onnxruntime`, `transformers`, `tokenizers`), "the ML path requires `headroom-ai[ml]`" is not the reason.
Nothing else was measured.

## Using rtk and headroom together

rtk compresses command output, and headroom compresses content sent to the model.
Both are baseline tools installed via mise (ADR 0047), and their scope depends on how you launch.

| Launch method | rtk | headroom proxy | headroom MCP server |
| --- | --- | --- | --- |
| `j-cc` (Claude Code) | Active (Bash hook) | Routed (session and workers) | Available |
| Plain `claude` | Active | Not routed (preserves Remote Control) | Available |
| `j-pi` (Pi itself) | Active (Pi bash extension) | Not routed (reasons above) | None |
| Codex worker launched from `j-pi` | Inactive | Routed | None |
| Plain `codex` | Active (Codex hook) | Not routed | None |

Because `j-pi`'s Codex workers launch with `--ignore-user-config`, Codex does not read the user's `hooks.json`.
Therefore neither rtk nor dotfiles guard hooks apply to these workers.

Enable both (`just deploy` also registers the headroom MCP server and installs the Codex plugin):

```sh
just deploy
just harden-env                              # Turn off telemetry for both (on Windows, also writes User env vars)
just sync-agents && just sync-agents a b c d x   # Distribute Claude and Codex hooks and mark Codex hooks trusted
just doctor                                  # Follow the printed instructions until the AI section is all OK
```

One proxy is enough.
`j-cc` and Codex workers share the same proxy through the state file (`~/.cache/jev/headroom.json`), starting it automatically at launch if none is running (see the "headroom" section above).
We do not install a login daemon (only `j-cc` and `j-pi`'s Codex workers use it, avoiding two startup mechanisms).

Verify both are active in one session with:

```sh
just jev-headroom-verify rtk   # A session in the same env as j-cc routes through the proxy, and its Bash goes through rtk
rtk gain                       # Number of commands compressed by rtk and tokens saved
headroom savings               # Tokens saved by headroom (across proxies for 30 days)
```

To use headroom, do two things:

- Launch sessions with `j-cc` when you want content sent to the model compressed (the proxy starts automatically)
- Use headroom's MCP tools (`mcp__headroom__headroom_compress`, `…_retrieve`, `…_stats`) in any Claude session

Check overall status in `just doctor`'s AI section.
`headroom doctor` assumes headroom's own wiring (where `headroom wrap` or `headroom init` writes the proxy into Claude and Codex configs).
So in this setup it reports claude and codex as "not routed" and suggests `headroom wrap claude`; do not follow it (plain `claude` would route through the proxy and lose Remote Control).
If you run `headroom doctor`, pass the recorded port (`port` in `~/.cache/jev/headroom.json`) with `-p` and inspect only the `proxy` and `version` lines (nothing listens on the default 8787, so `proxy` reports failure).

## Verification

Whether `updatedInput` and `effort` actually take effect in the Agent tool can only be verified with real requests.

```sh
just jev-claude-verify
```

It launches one unnamed worker, one named worker, and one `codex:codex-rescue`, judging by Claude Code's logs rather than the model's reply.
Those logs are the hook's own log, each subagent's `agent-*.meta.json` (actual `agentType` and `name`), and the effort recorded on each request.

| Result | Exit code | Meaning |
| --- | --- | --- |
| `PASS` | 0 | Verified the unnamed worker definition, selected effort, and Codex call arguments (only for the machine where it ran) |
| `FAIL` | 1 | Observed schema rejection, worker definition mismatch, or effort mismatch (takes precedence even if a usage limit occurs at the same time) |
| `BLOCKED` | 2 | Confirmed a usage limit from a provider error event, or the CLI exited unauthenticated (result event `Not logged in`). Retry after reset or login. Quotes in conversation text do not count. On machines without the Codex plugin, Claude Code returns `not found` for `codex:codex-rescue`, resulting in this status without verifying the Codex path (worker results are included in the reason) |
| `PARTIAL` | 3 | Insufficient evidence of worker effort, or `medium` matches the parent so the effect cannot be distinguished. Also check `/tasks` |

Each matched unnamed worker requires an effort record.
However, because hook invocations are not matched one-to-one with every worker, `PASS` does not prove every launch was rewritten.
For Codex, it verifies that the companion tool call arguments contain the chosen `--model` and `--effort`, not that every downstream API request received the same effort.
If a named worker (teammate) has a different effort, a separate warning is emitted.

### Pi workers

Verify Pi worker effort levels with:

```sh
just jev-pi-verify
```

It runs one non-interactive launch (`pi -p`) identical to `j-pi`, triggering one worker with a hard prompt (the session itself is `medium`).
It judges by the `model` (the model the worker actually ran with) and exit code in `subagent-artifacts/<run>_worker_meta.json` written per run by pi-subagents, not by the session log.
That is because the session log records the launch arguments before the extension rewrote them and cannot show the rewrite result.

| Result | Exit code | Meaning |
| --- | --- | --- |
| `PASS` | 0 | Worker completed with `:high` (Jev's selection, higher than the session's `medium`) |
| `FAIL` | 1 | subagent was called but no worker record exists, model lacks an effort suffix, or worker failed |
| `BLOCKED` | 2 | Missing key or extension, stopped by usage limit before worker, pi-background-tasks older than 2.6.9 rejected Anthropic Sonnet 5.5 (`no Claude Code model policy`), or model did not call subagent (auto-retries once only when no provider error occurred). Usage limits and rejections are detected from provider errors in the session log even when Pi exits with code 0 |
| `PARTIAL` | 3 | Worker ran at `medium`, indistinguishable from the session |

### headroom routing

Verify that `j-cc` sessions, `j-cc` workers, and Codex workers route through headroom with:

```sh
just jev-headroom-verify          # All three
just jev-headroom-verify codex    # Codex workers only (works without a Jev key)
just jev-headroom-verify rtk      # Both headroom and rtk in one session (works without a Jev key)
```

It starts a verification-only proxy on a free port, logs request messages to a temporary directory, and stops the proxy and deletes the logs afterward.
Pointing at that proxy, it runs one non-interactive (`claude -p`) session with the same environment and hooks as `j-cc` and launches one plain worker.
It judges from the proxy log (marker in the session's and worker's first messages) and the hook log, without relying on the model's reply.
For Codex verification, it runs the real `jev_codex_exec.py` and makes it reuse the verification proxy via the state file (`JEV_HEADROOM_STATE_DIR`).
Although headroom does not log Codex (Responses API) request messages, it logs the client as `codex`, which the check counts (only this runner uses the verification proxy).
For `rtk` verification, it runs a session with the same environment as `j-cc` in an empty temporary directory and has Bash run `ls -la` once.
It passes (`PASS`) if the proxy log has a request from that session and rtk's own count in that directory (`rtk gain -p`) is at least 1 (only Claude's rtk hook can increment the latter).

| Result | Exit code | Meaning |
| --- | --- | --- |
| `PASS` | 0 | Both the session request and the request from the worker rewritten to `worker-<effort>` routed through the proxy |
| `FAIL` | 1 | Proxy failed to start, session or worker request bypassed the proxy, hook did not log a rewrite, or Bash command bypassed rtk |
| `BLOCKED` | 2 | Missing key, headroom, or rtk; usage limit; not logged in or login expired (run `claude` and `/login`); or model did not launch a worker or run Bash |
