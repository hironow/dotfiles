# Plan: Fix false doctor WARNs found on physical Windows and WSL machines

**Date:** 2026-11-01
**Status:** Approved (2026-11-01 19:32, owner: D1, D2, and D3 all as recommended). Implemented; awaiting Windows and WSL re-verification (§9)
**Branch:** `fix/doctor-windows-wsl-warn`
**Related:** [ADR-0066](../adr/0066-doctor-warns-only-what-needs-action.md) (Accepted, baseline for this plan), [ADR-0065](../adr/0065-kernel-cve-is-evidence-only.md) (Proposed, kernel capped at WARN), [ADR-0062](../adr/0062-one-windows-ollama-for-wsl.md) (runbook is the source of truth for Ollama judgment), preceding plan [doctor-os-aware-warn](doctor-os-aware-warn.md) (§10 stated Windows/WSL/Linux-specific WARNs would be planned separately after seeing per-host outputs)
**Blocking decisions:** none (D1–D3 decided by owner)
**Graduates to:** [ADR-0066](../adr/0066-doctor-warns-only-what-needs-action.md) (reflected in Context and Decisions 2 and 5)

Input: comment on #526 (2026-11-01 19:17 JST). Output of `just doctor` on main `f582147` run on the trade machine's native Windows and WSL (Ubuntu 24.04, kernel `6.18.54.1-microsoft-standard-WSL2`).

## 1. Purpose and completion criteria

Align lines that misfired on physical Windows and WSL machines with ADR-0066 Decision 1 (WARN only for "what the operator should inspect or act on on this machine"). Keep ERR rules and exit code contracts unchanged (ADR-0066 Decision 6).

Completion criteria:

- For each item 2.1-2.7 below, write a failing test first, implement it, and pass `just ci` with exit 0.
- All PR CI checks pass.
- On this Mac, after merging to main, run `just ca-doctor-build` → `just kernel-doctor-build` → `just doctor` and verify WARN and ERR do not exceed current counts (`warn=1 err=1`) and exit code stays unchanged (1, system python ERR). Because ca-doctor and kernel-doctor block stale binaries with `WARN ca-build` / `WARN kernel-build` when sources change (`tools/ca-doctor/main.go:46`, `tools/kernel-doctor/main.go:121`), verification without rebuilding does not count. `just ci` go-test does not rebuild the binaries doctor uses.
- Ask the trade machine's operator for physical Windows and WSL verification (unmeasurable from this Mac). Include the post-merge SHA in the request. Consider complete once results (from `just doctor` with rebuilt binaries at that SHA) arrive on the PR confirming lines changed as expected in §7 and expected WARNs / ERRs and exit codes remain. Until then, keep it in handover's Windows and WSL section as "implemented; awaiting physical verification".

## 2. Changes

### 2.1 Windows curl (Schannel) exits 35 when rejecting a certificate (Report 1)

Facts (read upstream curl `lib/vtls/schannel.c` and `lib/strerror.c` on 2026-11-01):

- Among Schannel handshake failures, only `SEC_E_WRONG_PRINCIPAL` and `SEC_E_UNTRUSTED_ROOT` produce exit 60 (`CURLE_PEER_FAILED_VERIFICATION`). All others exit 35 (`CURLE_SSL_CONNECT_ERROR`) with `schannel: next InitializeSecurityContext failed: <name> (0x........) - <description>` on stderr.
- Certificate-related names emitted by `Curl_sspi_strerror` include `CRYPT_E_REVOKED`, `CRYPT_E_NO_REVOCATION_CHECK`, `CRYPT_E_REVOCATION_OFFLINE`, `CRYPT_E_NOT_IN_REVOCATION_DATABASE`, `CRYPT_E_NO_REVOCATION_DLL`, `SEC_E_CERT_EXPIRED`, `SEC_E_CERT_UNKNOWN`, and `SEC_E_CERT_WRONG_USAGE`.

Change (`CurlOutcome` in `tools/ca-doctor/probe.go`):

- On exit 35, return `CertRejected` if stderr contains `schannel:` and any of the following names followed immediately by a space and `(0x`: `CRYPT_E_REVOKED`, `SEC_E_CERT_EXPIRED`, `SEC_E_CERT_WRONG_USAGE`.
- Keep names indicating revocation could not be checked (`CRYPT_E_NO_REVOCATION_CHECK`, `CRYPT_E_REVOCATION_OFFLINE`, etc.) and the broad `SEC_E_CERT_UNKNOWN` as `Unknown` (not a certificate rejection verdict).
- Continue suppressing stderr text from output (used only for classification).

Tests (Red first): add a `CurlOutcome` table to `probe_test.go`: exit 35 + `CRYPT_E_REVOKED` → `CertRejected`, exit 35 + `CRYPT_E_REVOCATION_OFFLINE` → `Unknown`, exit 35 without `schannel:` (OpenSSL handshake failure) → `Unknown`, exit 60 → `CertRejected` as before, truncated → `Unknown`.

Effect: Windows `ca-live-emudhra-2026-curl` moves from WARN `unverified=14/14` to all-rejected INFO (ADR-0066 Decision 3). Remains ERR if any host is accepted.

### 2.2 Windows control connection resets intermittently (Report 2; root cause is IPv6)

Facts: from Windows on the trade machine to the control URL, 3 of 10 attempts hit `Connection was reset` (curl and python); from WSL, 10 of 10 succeeded. All 14 test hosts did not reset (`certificate-rejected=14 unverified=0`). Cause not yet verified.

Change (`ProbeClient`): only when control URL returns `Unknown`, retry up to 2 times with the same client (3 attempts total). Do not retry `Accepted` or `CertRejected`. Do not retry test hosts (no resets reported, and avoids tripling timeouts for unreachable hosts). Retries share the global concurrency budget.

Reason: control tests "can this client establish TLS at all?", which a single reset does not answer. If all 3 return `Unknown`, keep WARN as before. Never mark unverified as OK.

Tests: using a fake `TLSProber` (control returns `Unknown` first, `Accepted` second) gives INFO; 3 `Unknown`s give WARN and stop at 3 control attempts; `CertRejected` control is tried only once.

Root cause was IPv6 (2026-11-01, trade machine; [ca-control-ipv4](ca-control-ipv4.md) §1). The control URL has both IPv4 and IPv6 addresses, and Windows prefers IPv6. Roughly half of IPv6 connections reset (curl `-6`: 19 of 30; `-4`: 0 of 30). Test hosts have only IPv4 addresses. Because 3 retries alone remained flaky (WARN in 4 of 8 runs), [#529](https://github.com/hironow/dotfiles/pull/529) restricted the 2nd attempt to IPv4 (except Bun). Where the reset happens has not been traced.

### 2.3 Two-component version (pip `24.0`) reports "unparseable" (Report 3)

Facts: `stableVersion` (`tools/ca-doctor/policy.go:177`) accepts only `x.y.z`. Ubuntu system pip is `24.0`. If pip releases a two-component fix like `26.3`, it would still emit WARN even when patched.

Change: for observed tool versions only, compare `x.y` as `x.y.0`. In both PEP 440 and Go versioning (`1.27` = `1.27.0`), an omitted trailing component is 0. Incident fix floors (`minimum` in `incidents/*.json`) still accept only 3 components (keep `incidents.go:78` validation unchanged). Leave kernel-doctor unchanged (ADR-0065 Decision 3: compare only full `x.y.z` strings).

Tests (`VersionEvidenceFor`): pip `24.0` → WARN `24.0 is outside the reviewed fix branches (26)`, `26.3` → OK, `26.2` → ERR (`26.2.0 < 26.2.2`), `26` → WARN unparseable, `26.3rc1` → WARN unparseable. Fix floor `26.2` still fails validation.

Effect: system pip `24.0` still warns (out-of-branch warns per ADR-0066's previous plan §4.3), with accurate wording. Two-component patched versions no longer trigger false WARNs.

### 2.4 Branch `brew - missing` by OS (first half of Report 4)

Facts: justfile states "brew is optional on Linux (WSL and mise-managed machines lack Homebrew)" (`justfile` dump recipe) and "native Windows has no brew" (`update-brew`). `scripts/doctor.sh:30` emits `WARN brew - missing` without checking OS.

Change (`scripts/doctor.sh`):

- macOS: unchanged (OK if present, WARN if missing).
- Linux (including WSL): OK if present, else `INFO brew - not installed (optional on Linux; Brewfile steps are skipped)`.
- native Windows (`MINGW*|MSYS*|CYGWIN*`): emit no line (ADR-0066 Decision 5).
- Add a `log_info` helper right after `log_err` (increments `info`). Currently no helper counts INFO; only child-check blocks count their INFOs.

Tests: add an OS × brew matrix in `tests/unit/test_doctor_os_gating.py` covering Darwin / Linux / WSL / MINGW (mocking `has` and `uname` with shell functions).

### 2.5 Windows `ca-os-bundle` always emits WARN (second half of Report 4)

Facts: `storeInventory` (`tools/ca-doctor/main.go:250`) looks for `dpkg-query`, `rpm`, `apk`, and (on macOS) `brew`. None exist on Windows, so it always reports `WARN ca-os-bundle - OS CA bundle/revocation update state not established`. Windows root store and CTL (disallowed list) are updated via Windows Update, not packages (CA runbook "native Windows" row).

Change:

- [Tidy First structural commit] change `storeInventory(ctx)` to `storeInventory(ctx, goos string)`, passing `runtime.GOOS` at the call site (no behavior change).
- [Behavioral] when `goos == "windows"`, return `INFO ca-os-bundle - Windows root store and disallowed list are updated by Windows Update, not by a package; not inventoried here; check Windows Update and organisational certificate distribution (docs/runbook/ca-doctor.md)`. On Linux when no package version can be read (unknown distro), keep WARN as before.

Tests: `storeInventory(ctx, "windows")` returns 1 INFO line without executing any package command on PATH (empty dir PATH). Existing fake `dpkg-query` test passes `"linux"`.

### 2.6 Downgrade kernel third-party figures and advice lines to INFO (Report 5, Decision D1)

Facts: on WSL, each CVE emits 7 WARN lines: 1 `kernel-version-*` (`unverified-vendor`), 1 `kernel-observed-*` (NVD figures, etc.), and 5 `kernel-advice-*` (fixed advice text from the record) (`tools/kernel-doctor/main.go:201-207`). Observed and advice text never vary by machine state.

Change (recommended): make `kernel-observed-*` and `kernel-advice-*` INFO. Keep `kernel-version-*` (below fix floor or unverified vendor kernel) and `kernel-sysctl-*` at their current levels. On WSL, kernel WARNs drop to 1 line per CVE (`kernel-version-*`).

Relation to ADRs:

- ADR-0065 Decision 4 (kernel findings cap at WARN, never `err`) sets an upper bound; INFO sits below it. Decision 2 (`just doctor` prints as advisory) is also satisfied since INFO is displayed.
- ADR-0066 Decisions 1 and 2 cover kernel-doctor and classify third-party figures (facts) and static advice (disclaimers) as INFO. PR #526 verified only on macOS and missed those two line kinds. This aligns implementation with ADR-0066 without changing decisions.
- Because the reporter asked for an owner ruling, confirm as D1.

Tests: in kernel-doctor `assessmentFindings`, verify observed and advice are INFO, version stays WARN, and exit codes in `Report` and `--json` depend only on WARN version lines. `tests/unit/test_doctor_kernel.py` already verifies INFO counting, so update only expected counts. Add one sentence to `kernel-doctor.md` noting "figures and advice are INFO".

### 2.7 Make Ollama `docker-desktop` uninspected status INFO (from reported Windows WARN list, Decision D2)

Facts: `ollama_host.py` (`scripts/ollama_host.py:1531`) groups "stopped distros" and "`docker-desktop` (platform-managed)" under the same `WARN ollama-inspection - ... stopped/platform-managed, uninspected`. The Ollama runbook (the judgment source of truth per ADR-0062 Decision 4, `docs/runbook/ollama-windows-wsl.md:159`) says "stopped or unreachable WSL distros emit uninspected WARN; platform-managed distros also report uninspected", and does not specify WARN for platform-managed distros. `docker-desktop` cannot be an ADR-0062 Ollama client (Docker Desktop's internal distro).

Change (recommended): emit `INFO ollama-inspection - WSL docker-desktop: platform-managed, not an Ollama client; not inspected` for `docker-desktop`. Keep stopped user distros at WARN per the runbook. State explicitly on runbook line 159: "platform-managed distros report as INFO".

Tests: split the existing test in `tests/unit/test_ollama_host.py` (around line 1633, stopped `Ubuntu` + `docker-desktop`) so stopped `Ubuntu` is WARN, `docker-desktop` is INFO, and neither is started.

## 3. Update ADR-0066 (while still Proposed)

- Add the 2026-11-01 Windows and WSL measurements (`ok=61 warn=11 err=1 info=20` / `ok=54 warn=12 err=1 info=26`) and the lines fixed by this plan to Context.
- Add to Decision 5 examples: "Homebrew line is WARN only on macOS, INFO on Linux, omitted on native Windows" and "Windows OS CA store line is INFO". Add to Decision 2 examples: "kernel third-party figures and static advice".
- Update Consequences "physical Windows and WSL verification still required" to list verified facts and remaining work (re-verification after this plan's changes).
- Update the Option A action under "Decision (pending)" ("merge the `feat/doctor-os-aware-warn` PR …", already done) to the current state.
- Add nothing to the decision change log (still Proposed). Update the "Next step" column in decision-queue.
- Re-run the cross-DR check from proposal time (relations to ADR-0062 and ADR-0065); stop and consult the owner if any conflict appears.

## 4. Order (commit units)

1. `refactor(ca-doctor): pass the OS to the CA store inventory` (2.5 structural change only)
2. `fix(ca-doctor): count Schannel certificate rejections from curl` (2.1)
3. `fix(ca-doctor): retry an unknown control probe before calling it unknown` (2.2)
4. `fix(ca-doctor): compare two-part tool versions as x.y.0` (2.3)
5. `feat(ca-doctor): report the Windows root store as INFO` (2.5 behavioral)
6. `feat(doctor): show brew only where it is used` (2.4)
7. `feat(kernel-doctor): show third-party figures and advice as INFO` (2.6, only if D1 approved)
8. `feat(ollama): show the platform-managed distro as INFO` (2.7, only if D2 approved)
9. `docs(adr): record the Windows and WSL measurement in ADR-0066` (3)

Each commit follows Red → Green. Check contents after each commit with `git show --name-only`.
Work in a worktree while keeping `/Users/nino/dotfiles` on main.
Draft PR → `just ci` → rebuild `just ca-doctor-build` → `just kernel-doctor-build` → `just doctor` in worktree (inspect effect on Mac) → ready → all CI pass → squash merge (`--watch`, no `--auto`) → run the same 3 commands on main to confirm §1 Mac criteria → comment on the PR with post-merge SHA and §7 request → update handover.

## 5. Owner decisions

- D1 (approve): make kernel observed and advice lines INFO? (Recommended: yes; applies ADR-0066 Decisions 1 and 2 within ADR-0065 Decision 4's upper bound.)
- D2 (approve): make Ollama `docker-desktop` line INFO? (Recommended: yes; matches runbook wording; stopped user distros stay WARN.)
- D3 (approve): add control retries (2.2) or keep WARN until root cause is found? (Recommended: add; max 3 attempts, control only; keep root-cause investigation in handover.)

## 6. Out of scope

- `ollama-owner`, `ollama-health`, `ERR ollama-bridge` on trade machine: genuine configuration issues; operator starts Windows Ollama on that machine and runs `ollama_host.py --setup` (per runbook).
- `python-retired`, `rtk-pi-extension`: genuine WARNs cleared by operator action on that machine.
- Windows `docker - daemon unreachable` was an observation log from that time, not a current procedure requesting Docker installation.
  Check current managed-runtime requirements under Podman 5+ in ADR 0067.
- `kernel-version-*` `unverified-vendor` WARN: per ADR-0065 Decision 3 (do not judge vendor kernels).
- `ollama-inspection` WARN for stopped user WSL distros: required as WARN by Ollama runbook.
- `ca-os-bundle` WARN on Linux when package version cannot be retrieved.

## 7. Request for Windows and WSL re-verification (posted on PR)

On the trade machine, run `git pull` (verify post-merge SHA with `git rev-parse --short HEAD`) → `just ca-doctor-build` → `just kernel-doctor-build` → `just doctor`.
Expected: on Windows, `ca-live-*-curl` is INFO (if control succeeds), `brew` and `ca-os-bundle` WARNs disappear, and `docker-desktop` is INFO; on WSL, `brew` is INFO and kernel has 1 WARN line. Comment results on the PR.

## 8. Review record

- Codex round 1 (2026-11-01): REVISE, 1 finding.
    - [P2] Completion criteria omit verifying rebuilt binaries after changes and verifying on target OSes → **Adopted**. Confirmed in `tools/ca-doctor/main.go:46` and `tools/kernel-doctor/main.go:121` that old binaries stop with `WARN ca-build` / `WARN kernel-build` when source changes. Added rebuilds and SHA confirmation to §1 completion criteria, §4 sequence, and §7 request.
- Codex round 2 (2026-11-01, `resume --last`): APPROVE, no new findings. Previous P2 judged resolved in §1 and §4.

## 9. Implementation results (2026-11-01, this Mac)

- `just ci` exited 0 (unit 1995 passed; golangci-lint and `go test` passed on both ca-doctor and kernel-doctor).
- Rebuilt binaries in worktree and ran `just doctor`: `ok=52 warn=6 err=1 info=31`, matching §11 of the previous plan. Of the 6 WARNs, 5 are `claude-plugins` from running in a worktree and 1 is system pip 21.2.4 (out of branch). ERR is the 1 system python `ca-live` line. Changes in this plan target Windows and WSL, so this Mac's output is unchanged.
- Plan adjustment during implementation: wrote 2.4's brew logic using `if` rather than `case "$(uname -s)" in`. Three existing tests (`test_doctor_windows.py`, `test_doctor_npm_rogue.py`, `test_retired_python_tools.py`) locate the Windows-only section as the first `case "$(uname -s)" in` and broke during the first `just ci`.
- Requested Windows and WSL re-verification on #526 after merge (2026-11-01 20:09, [comment](https://github.com/hironow/dotfiles/pull/526#issuecomment-6557133995), §7). The `ca-live` line became INFO on both Windows and WSL during [#529](https://github.com/hironow/dotfiles/pull/529) verification. Because full `just doctor` output has not yet arrived, this plan remains "implemented; awaiting physical verification".
