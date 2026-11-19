# Plan: Retry ca-doctor control over IPv4 to stop `control=unknown` flakiness on Windows

**Date:** 2026-11-01
**Status:** done (→ "Network and execution limits" in [CA runbook](../runbook/ca-doctor.md)). Approved (2026-11-01 21:46, owner; also approved using worktrees on both Windows and WSL). Merged in [#529](https://github.com/hironow/dotfiles/pull/529) (main `a3dbd5c7`). Results in §12
**Branch:** `fix/ca-doctor-control-ipv4` (worktree is `dotfiles-ca-control-ipv4` under home)
**Related:** [Windows and WSL follow-up plan](doctor-windows-wsl-warn.md) (added control retries in §2.2 and left root-cause isolation open), [ADR-0066](../adr/0066-doctor-warns-only-what-needs-action.md) (Accepted, D3 = retry control), [CA runbook](../runbook/ca-doctor.md) lines 56-61
**Blocking decisions:** none (D1 decided as (b) per independent review finding, §10)

Request: operator (2026-11-01 20:54): "How about you make and open the PR that fixes it?" (translated).
When verifying #527 on trade machine Windows, `ca-live` WARNs still appeared and disappeared across runs even with control retries.

## 1. Problem (measured on trade machine, 2026-11-01, main `8ad86f8`)

Running `output/ca-doctor/ca-doctor.exe --summary` 8 times on Windows yielded `unknown` after 3 attempts for one client's control in 4 of the 8 runs, turning that `ca-live-*` line to WARN and exiting 1 (diagnostic-go, curl, node, curl — a different client each time). Zero failures on WSL.

Root-cause isolation (continuing investigation left open in `docs/plan/doctor-windows-wsl-warn.md` §2.2):

| Measurement (Windows, 30 runs each) | Failures |
| --- | --- |
| curl `-6` → control URL | 19/30 (`(35) Recv failure: Connection was reset`) |
| curl `-4` → control URL | 0/30 |
| node `tls.connect` default / `family: 4` | 13/30 / 0/30 |
| python `socket.create_connection` default / `AF_INET` socket | 15/30 / 0/30 |
| bun `fetch` default | 0/30 |
| curl default → example.com (baseline) | 0/40 |
| WSL curl default → control URL | 0/40 |

- Control URL `https://emudhra.we-have-a-problem.com/` is hosted on GitHub Pages with both A (`185.199.108-111.153`) and AAAA (`2606:50c0:8000-8003::153`) records. Windows connects over IPv6 by default (curl `remote_ip` is `2606:50c0:8001::153`).
- The 14 test hosts have only A records (`204.168.130.246`, `54.39.60.141`, no AAAA). Test chains still connect over IPv4 today.
- WSL (NAT) exits only over IPv4, so the issue does not occur there. Windows Defender Network Protection is off (`EnableNetworkProtection=0`). Where connections reset (router, ISP, or GitHub) has not been traced.
- Current retries (`controlAttempts = 3` in `tools/ca-doctor/probe.go`) try the same path 3 times with no delay. With ~50% failure per attempt, 3 consecutive failures occur ~1/8 of the time per client, or ~50% across 5 clients—matching observations.

Thus, control currently probes a path (IPv6) that test chains never take.
This machine's broken IPv6 path pollutes the control question ("can this client establish TLS to a valid certificate?").

## 2. What we preserve

- Never mark unverified checks as OK or INFO: if control is `unknown` even over IPv4, keep WARN (ADR-0066 Decision 6, runbook line 87).
- Keep ERR rules and exit code contracts unchanged: accepting even 1 test host emits ERR.
- Probe test chains once over their current path (do not increase timeouts for unreachable hosts).
- Keep baseline (`ca-https-*`, example.com) unchanged (not failing).
- Keep attempt count (max 3 for control), total deadline (30 s), and concurrency limit (12) unchanged.

## 3. Changes

### 3.1 Retry the 2nd control attempt over IPv4

In `ProbeClient`, when a client can restrict itself to IPv4 using the same connection method, order control attempts as follows (max 3 unchanged):

1. Attempt 1: unchanged (client's default address selection). Stop immediately if `Accepted` or `CertRejected`.
2. Attempt 2: only if `unknown`, restrict to IPv4.
3. Attempt 3: if still `unknown`, retry once more with default selection.

Clients that cannot restrict to IPv4 (bun) keep trying up to 3 times with default selection.

Reason: because test hosts have only IPv4 addresses, a passing IPv4 control answers "can this client establish TLS to a valid certificate" along the same path as test chains.
Keeping attempts 1 and 3 on default selection preserves current results where control already works (Mac, WSL, Linux) and keeps a recovery path on IPv6-only networks (NAT64) if attempt 1 has a transient failure. Three `unknown`s still emit WARN.

### 3.2 How each client tries IPv4

Keep the `TLSProber` interface unchanged.
Make IPv4 restriction a property on the prober value (`GoProbe.IPv4`, `ExternalProbe.IPv4`), and pass `ProbeClient` two probers: default and IPv4 (`nil` when unsupported).
Extract live client assembly in `main.go` into one function so IPv4 support is decided in one place.

| Client | Default (unchanged) | IPv4 |
| --- | --- | --- |
| diagnostic-go | `http.Transport` default dial | Same Transport with `DialContext` using `net.Dialer` `"tcp4"` |
| curl | Current args | Append `--ipv4` to current args (same proxy handling as default) |
| node | `nodeProbe` (`tls.connect`) | Pass trailing arg `4` to the same script to set `family: 4` |
| python | `pythonProbe` (`socket.create_connection`) | Pass trailing arg `4` to the same script to connect via an `AF_INET` socket |
| bun | `bunProbe` (`fetch`) | None (`nil`); 3 default attempts |

Why exclude bun: `fetch` in Bun 1.4.4 ignores `family` (returns status 200 to A-only github.com even with `family: 6`). Bun's `node:tls` honors `family`, but unlike `fetch` it connects directly without proxy settings, differing from test chains (`fetch`). Letting its success pass control would backfill an unverified `fetch` check with a different transport (violating §2). bun's `fetch` failed 0/30 times on trade-machine Windows. If an `ExternalProbe{Kind: "bun", IPv4: true}` is ever constructed, return `unknown` without running a command.

### 3.3 Documentation

- `docs/runbook/ca-doctor.md` lines 58-61: update retry description to "Attempt 2 tries IPv4 only, and Attempt 3 falls back to default. Test hosts have only IPv4 addresses, and Windows resets ~50% of IPv6 connections to control (GitHub Pages) (2026-11-01, trade machine). Because Bun's `fetch` cannot pin IP family, it tries 3 times with default selection."
- Leave ADR-0066 unchanged: D3 (add control retries) stays the same, and path selection is an implementation detail documented in the runbook.
- Local `docs/handover.md` Windows section: record the root cause and this PR's result.

## 4. Tests (write Red first)

- `probe_test.go`: pass separate default and IPv4 `scriptedProber`s and update `TestProbeClientRepeatsAnUnknownControl` (all test chains `CertRejected`):
    - default `unknown` → IPv4 `Accepted`: INFO; 1 default call, 1 IPv4 call.
    - default `unknown` → IPv4 `unknown` → default `Accepted`: INFO; 2 default calls, 1 IPv4 call (IPv6-only network recovery).
    - default `unknown` → IPv4 `unknown` → default `unknown`: WARN; 2 default calls, 1 IPv4 call.
    - default `Accepted`: INFO; 0 IPv4 calls.
    - default `CertRejected`: WARN; 0 IPv4 calls.
    - IPv4 prober `nil` (bun): 3 default `unknown` → WARN, 3 default calls; default `unknown` → `Accepted` → INFO (unchanged behavior).
- `TestProbeClientDoesNotRepeatTestChains`: test chains run once on default, 0 times on IPv4.
- Live client assembly (extracted function): diagnostic-go, curl, node, and python have IPv4 probers; bun has `nil`. `ExternalProbe{Kind: "bun", IPv4: true}` returns `unknown` without running a command. If bun's control returns `unknown` 3 times on default, it stays WARN even if all test chains return `CertRejected` (never backfilled by direct connection).
- External command args (recorded with fake `Commands`): `--ipv4` appears only for IPv4 curl; trailing `4` appears only for IPv4 node and python; default args stay unchanged (pinning structural behavior invariance).
- Real clients (`TestExternalProbeAdaptersAgainstLocalTLS`, skip if absent): `IPv4: true` probes for curl, node, and python return `Accepted` against a 127.0.0.1 TLS server and `unknown` against `https://127.0.0.1:1/`. Schannel-only curl skips as today.
- diagnostic-go: `GoProbe{IPv4: true}` returns `CertRejected` against a 127.0.0.1 server. Against an IPv6 loopback TLS server (`[::1]`, skip if unavailable), `GoProbe{}` returns `CertRejected` while `GoProbe{IPv4: true}` returns `unknown` (proving IPv4 restriction).

## 5. Order (commit units)

1. `docs(plan): plan the IPv4 retry for the CA control probe` (this plan)
2. `refactor(ca-doctor): build the live client list in one function` (structural only; extract live client assembly in `main.go` without changing behavior; first add tests pinning default args and client order)
3. `fix(ca-doctor): retry an unknown control over IPv4` (3.1, 3.2, and 3.3 runbook; Red → Green)

Check contents after each commit with `git show --name-only`.

## 6. Workspace and workflow

- Keep `%USERPROFILE%\dotfiles` on main on this machine (runner GC / autostart execution source). Work in `git worktree add ..\dotfiles-ca-control-ipv4 -b fix/ca-doctor-control-ipv4 origin/main` and run `git worktree remove` when done.
- Because this machine lacks a signing key, branch commits are unsigned. Ruleset (`protect`) only forbids deleting or force-pushing main and does not require signatures; GitHub's squash merge signs the commit on main.
- Draft PR → `go test -race`, golangci-lint (ca-doctor), and `just ci` → ready → watch all CI pass via `gh pr checks --watch` → owner decides merge.

## 7. Completion criteria

- Section 4 tests fail first and pass after implementation. `go test -race ./...` (tools/ca-doctor), golangci-lint, and `just ci` pass. If any `just ci` leg cannot run on native Windows, note the skipped leg and reason in the PR and cover it via CI results.
- On trade machine Windows, run `ca-doctor --summary` built from the worktree 10 times with 0 `control=unknown` (previously 4 of 8). Paste each run's `ca-live-*` levels into the PR.
- On trade machine WSL, build the same SHA on Linux and verify (running Windows `.exe` from WSL runs as a Windows process and does not test Linux). Also keep WSL `~/dotfiles` on main; create a separate worktree via `git worktree add` and run `just ca-doctor-build` → `just ca-doctor --summary` once in a zsh login shell. Criteria: `OK ca-build`, `INFO ca-platform - WSL Linux; ...`, each `ca-tool-*` pointing to a Linux binary, and `ca-live-*` matching before (all 5 clients INFO).
- All PR CI checks pass.

## 8. Rollback on failure

Single squash merge, so `git revert <merge commit>`. Rebuild local binaries with `just ca-doctor-build`. Delete the worktree and branch together.

## 9. Out of scope

- Tracing where IPv6 connections reset (network issue on this machine; keep in handover).
- Baseline (`example.com`) path (not failing).
- Test-chain connection path (A-only, so already IPv4).

## 10. Owner decisions

- **D1. IPv4 attempts for bun.** → **(b) keep bun at 3 attempts on default `fetch`** (decided per independent review P1, §3.2). Rejected: (a) try IPv4 via Bun's `node:tls` (backfills `fetch` control with a direct connection).

## 11. Independent review record

Round 1 (Codex, 2026-11-01, verdict REVISE, 3 findings). All 3 verified and adopted:

| # | Finding | Verified | Resolution |
| --- | --- | --- | --- |
| P1 | Counting Bun `node:tls` (direct) success as `fetch` (proxy-aware) control success backfills an unverified `fetch` check via another path | Runbook line 56 "curl and Bun may be affected by proxy settings"; `tools/ca-doctor/policy.go:45` (control `Accepted` + all chains rejected = INFO) | Excluded bun from IPv4 (§3.2, D1 = (b)). Dropped `ProbeIPv4` on `TLSProber` in favor of allowing `nil` IPv4 prober. Added bun regression test (§4) |
| P2 | Pinning both attempts 2 and 3 to IPv4 removes default-path recovery on IPv6-only networks if attempt 1 has a transient failure | Current retries in `probe.go` all use default selection | Ordered attempts "default → IPv4 → default" (§3.1) and added recovery test (§4) |
| P2 | Launching Windows `.exe` from WSL runs as a Windows process and does not verify WSL | `tools/ca-doctor/main.go` branches checks by `runtime.GOOS` | Added §7 steps to build the same SHA on Linux in WSL and verify expected lines |

Round 2 (Codex, `resume --last`, verdict APPROVE, no new findings). All 3 previous findings judged resolved in the plan.

## 12. Implementation results (2026-11-01, [#529](https://github.com/hironow/dotfiles/pull/529))

- On trade machine Windows, ran `ca-doctor --summary` with the updated binary 10 times: 0 `control=unknown` (previously 4 of 8).
- On trade machine WSL, built the same SHA on Linux: `ca-build` OK, `ca-platform` WSL Linux, `ca-tool-*` Linux paths. Alternated main (`8ad86f8`) and updated binary 5 times each; all 10 runs reported INFO with `control=accepted` across all 5 clients.
- `go test` (Windows and WSL), `go test -race` (WSL), golangci-lint, and markdownlint all passed. On native Windows `just ci`, golangci-lint ran out of memory midway through `emulator/bigtable-cli` (preceding ruff, ty, and pytest passed). All PR CI checks passed.
- On this Mac, PR branch passed `go test -race` (156 tests), golangci-lint, and cross-builds for Windows and Linux. Ran `ca-doctor --summary` 3 times; all 5 `ca-live` clients were INFO every run. WARN and ERR lines match main (2 system python lines).
- Observed out of scope: in 2 of 24 runs of the updated binary (1 of 18 Windows, 1 of 6 WSL), 1 curl test chain returned unknown (`unverified=1/14`) and emitted WARN, while control succeeded both times. Could not reproduce across 42 consecutive curl runs on Windows. Cause unconfirmed; this plan did not alter test-chain paths.
