# Windows co-hosted Ollama: allow declared tailnet forwarding and omit bridge on mirrored WSL

**Date:** 2026-10-25
**Status:** done (→ [Ollama runbook](../runbook/ollama-windows-wsl.md), ADR-0062, 0063, 0064). All 3 Accepted via [decision in #504](https://github.com/hironow/dotfiles/pull/504#issuecomment-6400086305). Merged in [#504](https://github.com/hironow/dotfiles/pull/504) (main `6098696e`). Independent review: 6 findings from round 1 adopted; rounds 2 and 3 had no blocking findings
**Scope:** `scripts/ollama_host.py`, `tests/unit/test_ollama_host.py`, `docs/runbook/ollama-windows-wsl.md`, 1 ADR and 1 row in `docs/decision-queue.md`. Leave Tailscale config, `.wslconfig`, and Ollama's launcher unchanged.

## Owner request and current state

On a machine hosting both Windows and WSL (hereafter "co-hosted machine"), the owner decided the following on 2026-10-25:

- Port 11434 is exposed to the tailnet via Tailscale TCP forwarding, inside the tailnet only (Funnel is not used).
- This forwarding is still needed. dotfiles checks must not treat it as a violation.

Facts verified on that co-hosted machine (2026-10-25, non-elevated user):

- Windows has 3 listeners on 11434: `ollama.exe` from Scoop's `ollama-full` on `127.0.0.1`, and a `tailscaled` child process on this machine's tailnet IPv4 (inside `100.64.0.0/10`) and IPv6 (inside `fd7a:115c:a1e0::/48`). Nothing listens on `[::1]:11434`.
- The `tailscaled` child process's executable path is unreadable, but `ParentProcessId` and `CreationDate` are readable. Its parent is the Tailscale service process (`Win32_Service` `Name='Tailscale'`, `State=Running`), created 1 second before the child. The service's `PathName` is `%ProgramFiles%\Tailscale\tailscaled.exe`, with Authenticode `Valid` and signer `O=Tailscale Inc.`.
- `tailscale serve status --json` has only `TCP` and `Web` top-level keys (no `AllowFunnel` or `Foreground`). `TCP."11434"` is `{"TCPForward":"localhost:11434"}`. `tailscale ip -4` and `-6` are readable without elevation.
- `just doctor` emits ERR for `ollama-owner` and `ollama-exposure`. Re-evaluating the same snapshot without the `tailscaled` listeners turns both OK—these listeners are the sole cause.
- The PowerShell probe (`WINDOWS_PROBE`) also sets `$owned` false on these listeners and skips querying the version, causing `ollama-health` WARN.
- Because `backend_owned()` is false, WSL `--setup` stops without creating a bridge, and WSL's CLI wrapper (`client_command`) also stops.
- WSL `wslinfo --networking-mode` is `mirrored`. Running `curl http://127.0.0.1:11434/api/version` from WSL reaches Windows Ollama directly without a bridge (`0.40.5`). `[::1]:11434` does not answer. WSL has neither a 11434 listener nor a bridge unit.
- In mirrored mode, listening on the same port in both Windows and WSL causes a conflict (already happened on this machine). Current WSL design places a bridge on `127.0.0.1:11434` and `[::1]:11434` inside WSL, and the runbook says "keep NAT". dotfiles does not manage `.wslconfig`.

## Approach

### A. Allow Tailscale tailnet-only forwarding only on declared machines (owner decision)

- **Declaration**: place a per-machine declaration file outside the repo: `%USERPROFILE%\.config\dotfiles\ollama-tailnet-forward` (single line containing `11434`). Machines without it or with different contents keep today's judgment. The declaration is a per-user configuration choice, not an authorization boundary against the user themselves; deleting it restores the original check. Document both in the runbook.
- **Conditions to recognize as valid forwarding** (all must hold; reject if any item is unreadable or uncheckable):
  1. Listener port is 11434.
  2. **Process lineage**: Tailscale service is `State=Running` with `ProcessId != 0`. The listening process is either that service process itself, or a child named `tailscaled` whose `ParentProcessId` matches the service PID and whose `CreationDate` is at or after the parent's `CreationDate` (preventing PID reuse from misidentifying an unrelated parent). Re-read the service PID after inspection and confirm it did not change.
  3. **Binary identity**: service `PathName` (unquoted) equals `%ProgramFiles%\Tailscale\tailscaled.exe`, neither the file nor its parent directory is a reparse point, and Authenticode is `Valid` with signer containing `O=Tailscale Inc.` (same verification as the wslrelay exception).
  4. **Address**: listener address matches one of this machine's tailnet addresses from `tailscale ip -4` / `tailscale ip -6` and falls inside `100.64.0.0/10` or `fd7a:115c:a1e0::/48`. Verify `%ProgramFiles%\Tailscale\tailscale.exe` with the same check as step 3 before invoking it.
  5. **Never allow Funnel**: no `AllowFunnel` anywhere in `tailscale serve status --json` (including per-session configs under `Foreground`) may be true.
  6. **Forward target must be the legitimate backend only**: accept `TCP."11434".TCPForward` = `127.0.0.1:11434`. Accept `localhost:11434` only when nothing listens on `[::1]:11434` (`localhost` can also resolve to IPv6; if wslrelay or another process is there, forwarding could go elsewhere than the verified backend). Reject any other target. Reject if any other TCP forward besides 11434 or any `Web` proxy target points to 11434 (undeclared exposure path).
- **Handling recognized listeners**: exclude them from PowerShell `$backendListeners` and Python `_backend_listeners()` (do not count as a second backend) and from `ollama-exposure`. Instead emit `OK ollama-tailnet-forward` so active forwarding stays visible every run. Only when recognized forwarding leaves the single backend intact does PowerShell query the version (`ollama-health`).
- Unrecognized listeners (failing any condition or lacking the declaration) remain ERR as today. Keep the wslrelay exception and other checks unchanged.
- **Structure**: make the judgment a PowerShell function `Test-DotfilesTailnetForward` accepting inputs as arguments (listener rows, service/process info, signatures, `tailscale ip` output, serve JSON, declaration content, `[::1]:11434` listeners). Split collection (`Get-CimInstance`, `Get-NetTCPConnection`, `Get-Item`, `Get-AuthenticodeSignature`, CLI calls, version query) into small mockable functions for testing.

### B. On mirrored WSL, omit the bridge and verify Windows reachability over shared loopback (approved by owner, 2026-10-25)

- **Network mode detection**: read `wslinfo --networking-mode` inside WSL. `nat` behaves as today; `mirrored` follows the rules below; anything else or unreadable is "unknown", causing `--setup` to stop without creating a bridge and doctor to emit WARN.
- **Verification order before connecting** (identical across mirrored doctor, setup, and `--inspect-local`):
  1. Network mode is confirmed `mirrored`.
  2. WSL listener check (`ss`) succeeds and shows no 11434 listener in WSL. If `ss` fails, do not assume "no listener"; stop there.
  3. Windows-side ownership check (`backend_owned()`) succeeds. Because `--inspect-local` (run inside WSL by Windows doctor) does not know Windows-side judgment, it sends no HTTP request; WSL loopback verification runs only in WSL doctor.
  4. Only after passing steps 1-3, send one HTTP request from WSL to `http://127.0.0.1:11434/api/version`; OK if its version matches Windows' response.
  If any earlier step fails, make zero HTTP calls and stop.
- **mirrored `--setup`**: install the CLI wrapper (`~/.local/bin/ollama`) as today, without writing or enabling any bridge unit. Before changing anything, check whether dotfiles' bridge unit is enabled, active/activating, has a running `--serve` process, or whether WSL has a 11434 listener; if any exists (or state is unreadable), change nothing, fail with an exception, and tell the user how to stop it (`systemctl --user disable --now ollama-windows-bridge.service`).
- **`--serve` itself**: bind only when network mode is confirmed `nat`. Under `mirrored` or unknown, exit without binding (preventing conflicts even if an old unit is started manually).
- **mirrored doctor**: emit `ollama-loopback` instead of `ollama-bridge`: ERR if WSL has a 11434 listener, WARN if Windows' legitimate backend is stopped, ERR if versions differ, OK if all checks above pass with matching version. `OLLAMA_HOST` check (`conflicting_config`) stays unchanged.
- WSL CLI wrapper still verifies Windows ownership before invoking Windows CLI; unchanged in mirrored mode.
- **Coupling between A and B**: once A lands, `backend_owned()` becomes true on the co-hosted machine, allowing current WSL `--setup` to create a bridge even under mirrored mode. Therefore, even if B as a whole were deferred, land the guard "under mirrored or unknown, `--setup` creates no bridge and `--serve` does not listen" in the same PR as A. Do not run WSL `just deploy` on mirrored machines until B merges.

### Documentation and decision records

- Add 3 ADRs. A cross-DR check flagged a conflict between ADR-0058 Decisions 3-4 (co-hosted Ollama runs 1 instance on WSL) and PR #502's implementation (1 instance on Windows), and the owner ruled to "replace it with another ADR" (translated) (2026-10-25). 0062 records #502's design and supersedes those parts of 0058; 0063 covers A; 0064 covers B. Add 3 rows to the decided log in `docs/decision-queue.md`, and update only the Status line of 0058. Record the rulings by proxy on the public PR.
- Update the runbook with how to declare and remove the file, that the declaration is not an authorization boundary, what gets verified (never Funnel, forwarding target rules), and mirrored handling. Change "keep NAT" to "bridge for NAT, shared loopback for mirrored".
- In a separate commit, add a warning to the runbook that "the standalone installer's uninstaller deletes models in the default path" (which actually deleted models on the co-hosted machine on 2026-10-25).

## TDD order (Red → Green → Verify per small behavior)

1. **Python core (Linux and Windows CI)**: pass pre-classified `tailnet_forward: true` listeners into `windows_findings()`, `_backend_listeners()`, and `backend_owned()`, and verify `ollama-owner`, `ollama-exposure`, and `ollama-tailnet-forward` are OK. Missing or false `tailnet_forward` stays ERR as today.
2. **PowerShell judgment function (Windows CI)**: same pattern as wslrelay exception tests (function stubs + `-EncodedCommand`). True only when all conditions hold; false on any of: missing/mismatched declaration, wrong port, stopped service or PID 0, parent not service, wrong name, parent newer than child, service PID changed mid-probe, wrong path, reparse point (file or parent), unsigned/wrong signer/signature check failure, address not belonging to this machine's tailnet (`0.0.0.0`, LAN, another `100.x`, out of range), `AllowFunnel` present (including via 443 or under `Foreground`), `TCPForward` pointing elsewhere (`localhost:8080`, `0.0.0.0:11434`), `localhost:11434` with wslrelay on `[::1]:11434`, `Web` proxy pointing to 11434, CLI failure, corrupt JSON.
3. **Full PowerShell probe (Windows CI)**: stub all collector functions, run `WINDOWS_PROBE` end-to-end, and verify in output JSON that recognized listeners get `tailnet_forward: true` and are excluded from backend, unrecognized ones stay as today, and the version query runs once only when solely legitimate backend + recognized forward remain and 0 times otherwise.
4. **WSL ordering (Linux CI)**: stub network mode, `ss`, Windows ownership, and HTTP; verify HTTP runs 0 times on unknown, `ss` failure, WSL listener present, or Windows ownership failure, and once only when all pass. Verify `wsl_findings()` OK / WARN / ERR lines, `--inspect-local` makes 0 HTTP calls in mirrored mode, and existing `nat` tests still pass.
5. **setup and `--serve` (Linux CI)**: in mirrored mode, place the CLI wrapper without calling mutating `systemctl` commands (`daemon-reload`, `enable`, `restart`); raise without modifying anything if unit is enabled/active/activating, `--serve` is running, listener exists, or state is unreadable; `--serve` binds only when confirmed `nat`.
6. **Physical machine (co-hosted machine; pin verified commit)**:
   - Before declaration: `just doctor` emits same ERRs as today.
   - After declaration while Windows backend is up: `ollama-owner`, `ollama-exposure`, `ollama-tailnet-forward`, and `ollama-health` are OK; connecting from this machine to tailnet address port 11434 returns version (forwarding reaches backend); LAN address port 11434 does not connect; stopping backend also breaks tailnet connection.
   - WSL: pull main and run `just deploy` → only CLI wrapper placed, no bridge unit → WSL doctor `ollama-loopback` OK, `ollama list` (CLI wrapper) works → Pi web search (hardcoded `http://localhost:11434`) reaches from WSL (`localhost` tries `::1`, gets refused, falls back to `127.0.0.1`) → stopping and restarting Windows backend causes no conflict.
   - Migration from an existing bridge is covered by unit test (5) since this machine has no prior bridge. Funnel is covered by realistic config fixtures (2) without exposing Funnel live. Reachability from another tailnet device is optional owner verification.

## Out of scope

- Changing Tailscale configuration, `.wslconfig`, or Windows Ollama launch method (tray app or machine-specific launcher).
- Python issues found during CA diagnostics.

## Definition of done

Unit tests for A (and B if approved) pass on Linux and Windows CI, `just ci` passes, all physical checks above pass, PR is merged, and results are reported to the owner.
Committing in dotfiles requires the machine's forbidden-token list (`~/.config/dotfiles/forbidden-tokens`). Wait to commit until the list is placed on the co-hosted machine.

## Physical verification (2026-10-25-26, co-hosted machine)

| Step 6 item | Result |
| --- | --- |
| Before declaration | `--check` gave `ollama-owner` and `ollama-exposure` ERR as today |
| After declaration, backend up | `ollama-install`, `ollama-owner`, `ollama-tailnet-forward`, and `ollama-exposure` OK; version retrieved (no `ollama-health` WARN) |
| Tailnet addresses | Both IPv4 and IPv6 port 11434 returned version (forwarding reaches backend) |
| LAN address | Connection refused; this machine's DHCP LAN IP happened to fall inside `100.64.0.0/10`, yet was not counted as forwarding because it is not a `tailscale ip` address |
| WSL (read-only, nothing placed) | `mirrored`, no WSL listener, no bridge; after confirming Windows ownership, shared loopback returned the matching version |
| After stopping backend | Tailnet connections also stopped; `ollama-owner` warned backend absent, `ollama-tailnet-forward` stayed OK; WSL skipped HTTP because ownership could not be confirmed |
| Windows probe script length | Passed via stdin so physical `--check` succeeded (`-EncodedCommand` reached 47,256 chars, exceeding the limit) |

WSL `just deploy` (pull main, place CLI wrapper, and turn doctor `ollama-loopback` OK) runs after merge.
Also verify then that Pi web search reaches Windows Ollama from WSL.
