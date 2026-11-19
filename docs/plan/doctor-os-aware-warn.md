# Plan: Scope `just doctor` WARNs to "what the operator should inspect on this machine", per OS

**Date:** 2026-11-01
**Status:** Approved (2026-11-01 17:07, owner: D1 = INFO when all rejected, D2 = propose an ADR). Implemented (§11)
**Branch:** `feat/doctor-os-aware-warn`
**Related:** [ADR-0065](../adr/0065-kernel-cve-is-evidence-only.md) (Proposed, kernel capped at WARN), [CA runbook](../runbook/ca-doctor.md), [kernel runbook](../runbook/kernel-doctor.md), [kernel plan](kernel-cve-evidence.md) (D3)
**Blocking decisions:** none (D1 and D2 decided by owner)
**Graduates to:** [ADR-0066](../adr/0066-doctor-warns-only-what-needs-action.md) (Proposed → Accepted on owner decision)

Request: operator (2026-11-01): "I also want doctor's processing to be based on that OS, and not emit too many excessive WARNs" (translated).

## 1. Problem (measured on this Mac, 2026-11-01)

`just doctor` reports `ok=55 warn=103 err=15`. The 103 WARNs break down as follows, with almost nothing requiring operator action:

| Count | Lines | Content | Nature |
| --- | --- | --- | --- |
| 70 | `WARN ca-chain-emudhra-2026-{bun,curl,diagnostic-go,node,python}` | `certificate-rejected` on all 14 test hosts (correctly rejected) | Expanding one fact into one line per host |
| 5 | `WARN ca-live-emudhra-2026-<client>` | `accepted=0 certificate-rejected=14`, "CA-specific distrust unverified" | Summary of those 14 lines |
| 10 | `WARN ca-tool-<tool>` | "active executable: <path>; ... is not TLS remediation proof" | Environment facts and disclaimers |
| 4 | `WARN ca-env` | `SSL_CERT_FILE` / `CURL_CA_BUNDLE` / `REQUESTS_CA_BUNDLE` / `PIP_CERT` are set | The exact settings recommended for macOS by the runbook (`ca-doctor.md:123`); each file is already checked by `OK ca-file-*` |
| 4 | `WARN ca-version-emudhra-2026-{certifi,pip}-{python,system-python}` | "unsupported/unparseable release" | 3 are misclassified: uv venv lacks certifi and pip, and system python lacks certifi (calling "not installed" an "unparseable version"). The remaining 1 is system python's pip 21.2.4 (only branch 26 has a reviewed fix floor) |
| 7 | `ca-platform` `ca-remediation` `ca-coverage` `ca-advice-*`×2 `ca-rust` `ca-os-bundle` | Scope and limitation disclaimers | Identical text every run; no action |
| 1 | `WARN ca-git-verify` | "no explicit http.sslVerify" | Git's default (verify) is simply not overridden |
| 1 | `WARN kernel-coverage` | Kernel check limitation disclaimer | Appears on darwin alongside `OK kernel-not-applicable`, disclaiming something not checked |

All 15 ERRs also expand a single fact—`/usr/bin/python3` accepted test hosts—into 14 host lines plus 1 summary line.

Some lines also do not fit the OS (inflating OK rather than WARN): on macOS, `OK PATH-windows` (WSL `/mnt` leak check) and `OK ollama-policy - ... not applicable on this host`.

## 2. What we preserve (unchanged principles)

- Never mark unverified checks as OK (`ca-doctor.md:87`, ADR-0065 Decision 3).
- Keep ERR semantics and doctor's exit code unchanged: any client accepting even 1 test host is ERR, and any ERR causes exit 1.
- Keep full evidence available: standalone `just ca-doctor` still emits one line per host.
- Keep kernel findings capped at WARN (ADR-0065 Decision 4).

## 3. New rule

**Use WARN only for "what the operator should inspect or act on on this machine".**
Emit check-scope disclaimers and environment facts at a new level, `INFO`.
`INFO` is displayed, counts toward neither OK nor WARN, and does not affect exit codes.
Doctor's final summary line becomes `Doctor summary: ok=N warn=N err=N info=N`.

Checks meaningless on the current OS emit no line at all.

## 4. Changes

### 4.1 Add `INFO` to the line protocol

- `scripts/doctor_lines.py`: `parse` / `fmt` handle `INFO`; `failed()` does not count INFO as a failure.
- `scripts/doctor.sh`: read loops for ca-doctor / kernel-doctor / ai_tools_check / ollama_host accept `INFO` lines and count `info`. Consistency checks for ca and kernel (exit code + line combinations) treat INFO as "neither OK nor WARN" (e.g., ca-doctor exiting 0 with only OK and INFO lines is valid).
- `Report` in `tools/ca-doctor` and `tools/kernel-doctor`: INFO does not raise exit code (keep 0 = no WARN or ERR, 1 = has WARN, 2 = has ERR).

### 4.2 Add `--summary` to ca-doctor and use it in doctor

- Under `--summary`, omit the per-host `ca-chain-*` lines; instead put counts on `ca-live-<incident>-<client>` and list any accepted host names.
- If 1 or more hosts were accepted, that single line is ERR (same judgment as today). On this Mac, ERR drops from 15 lines to 1 line, with exit 1 unchanged.
- `just ca-doctor` (without `--summary`) emits all lines as before.
- **Handling old binaries.** Today's binary exits 2 with `ERR ca-arguments` on unknown flags before checking freshness (`tools/ca-doctor/main.go:41-42`). As-is, doctor.sh would accept that as a real ERR and never advise rebuilding. Therefore, when output is solely the single line `ERR  ca-arguments` with exit 2, doctor.sh rejects the result and emits `WARN ca-build - CA check binary does not support this checkout -- run: just ca-doctor-build; then just doctor`. Accept all other ERRs as today. If a new binary that knows `--summary` runs against an old checkout, the freshness check returns `WARN ca-build` as before.

### 4.3 Review `ca-doctor` line levels (both standalone and `--summary`)

| Line | Before | After | Reason |
| --- | --- | --- | --- |
| `ca-tool-*` active executable | WARN | INFO | Fact stating which executable was probed |
| `ca-tool-*` not on PATH (explicitly states installation unnecessary) | WARN | INFO | No action needed |
| `ca-tool-*` wrapper / version command failed | WARN | WARN (unchanged) | Could not inspect; operator should look |
| `ca-env` CA file vars (`SSL_CERT_FILE` `SSL_CERT_DIR` `CURL_CA_BUNDLE` `REQUESTS_CA_BUNDLE` `PIP_CERT` `GIT_SSL_CAINFO` `GIT_SSL_CAPATH` `NODE_EXTRA_CA_CERTS`) | WARN | INFO | Contents checked by `ca-file-*` / `ca-path-*`; recommended by runbook |
| `ca-env` proxy vars, `NODE_OPTIONS`, `GODEBUG`, `PYTHONHTTPSVERIFY` | WARN | WARN (unchanged) | Can alter TLS behavior |
| `ca-env` ERR conditions | ERR | ERR (unchanged) | |
| `ca-platform` `ca-remediation` `ca-coverage` `ca-advice-*` `ca-rust` | WARN | INFO | Identical disclaimer every run |
| `ca-os-bundle` (when package version retrieved) | WARN | INFO | Version fact; keep WARN when unretrievable |
| `ca-git-verify` (not overridden) | WARN | INFO "not overridden in this config context (Git default: verify)" | Fact about Git default state; do not mark OK |
| `ca-version-*-{certifi,pip}` (not installed in that Python) | WARN "unparseable" | INFO "not installed in this Python" | Fix misclassification |
| `ca-version-*` (installed, outside branches with reviewed fixes) | WARN "unparseable" | WARN "no reviewed fix floor for release branch N" | Fix wording only |
| `ca-live-*` (control accepted, all test hosts rejected) | WARN | **operator decision (D1 below)** | |

### 4.4 Branch `kernel-doctor` by OS

- On machines where no Linux kernel was checked (darwin, native Windows), omit `kernel-coverage`, leaving only the single `OK kernel-not-applicable` line (which already states WSL and Linux VMs used from this machine were not checked).
- On machines where a kernel was checked (Linux, WSL), emit `kernel-coverage` as INFO. Keep kernel findings themselves at WARN (ADR-0065 Decision 4).

### 4.5 Omit OS-inapplicable lines in doctor.sh

- Emit `PATH-windows` only on WSL (when `uname -r` contains `microsoft`, matching existing `wsl-clipboard` condition).
- Omit `ollama-policy - ... not applicable on this host`. Leave applicability to `host_policy()` (`scripts/ollama_host.py:337-351`), which targets native Windows and WSL while excluding containers on WSL kernels. doctor.sh does not detect OS itself.
- Contract to signal "not applicable" to parent: when `host_policy()` is `None`, `ollama_host.py --check` prints nothing and exits **exit 3** (keeping exit 0 / 1 / 2 meanings unchanged; confirm 3 is unused before implementing). doctor.sh advances silently only when **exit 3 and total captured output (stdout + stderr) is empty**. If exit 3 produces any output, treat as a mismatch: emit `WARN ollama-inspection` and count zero OK / INFO / WARN / ERR from that output. Change the current "count per line as read" loop (`scripts/doctor.sh:456-466`) to "classify all lines first and verify against exit code before counting", matching ca and kernel. Zero lines with any other exit code (including 0 / 1), or exit 2+ other than 3, still emits `WARN ollama-inspection - checker unavailable`.
- Write separate tests for macOS, plain Linux, WSL, container on WSL kernel, native Windows, and checker failure (0 lines, exit 1).

## 5. Operator decisions (decided 2026-11-01 17:07)

- **D1. Level for clients that reject all test hosts.** → **(a) INFO** (keep "CA distrust is not proven" in the text; never mark OK). Rejected: (b) keep WARN (leaves 5 on this Mac).
- **D2. Record format.** → **Propose ADR-0066**. Because this rule (WARN only when action is needed; disclaimers are INFO) changes an established pattern, propose a new ADR and add a row to `docs/decision-queue.md` (decision-record-governance skill). Since ADR-0065 is Proposed, reference kernel-coverage handling from the new ADR without editing ADR-0065's body.

## 6. Workflow (TDD, 1 PR, separate structural and behavioral commits)

1. Create a worktree from `origin/main` (`git worktree add ../dotfiles-doctor-os-aware -b feat/doctor-os-aware-warn origin/main`). Keep `/Users/nino/dotfiles` on main.
2. Propose the ADR and add a row to decision-queue (docs commit).
3. Run Red → Green per item:
   - Go: in `tools/ca-doctor/*_test.go`, add tests for 4.2 and 4.3 line levels and wording, `--summary` aggregation (all rejected, partial accepted, mixed unknown), and `Report` exit code (0 on INFO only). In `tools/kernel-doctor/main_test.go`, add tests omitting `kernel-coverage` on darwin/windows and emitting INFO on linux.
   - Python: in `tests/unit/test_doctor_lines.py`, test INFO parse / fmt / failed. In `tests/unit/test_doctor_ca.py` and `test_doctor_kernel.py`, test doctor.sh tallying and consistency checks when fake binaries emit INFO (exit 0 with OK+INFO valid; INFO alone with 0 OK invalid).
   - Reproducing old binary: current fake binaries ignore args (`tests/unit/test_doctor_ca.py:33`). Add a fake binary returning `ERR  ca-arguments` and exit 2 on unknown args like the current CLI, and confirm doctor.sh emits `WARN ca-build` without counting ERR. Also verify real security ERRs (e.g., `ERR  ca-live-...`) still count.
   - ollama: cover the 6 cases in 4.5 (without breaking existing container tests in `tests/unit/test_ollama_host.py`). On doctor.sh, verify with fake checkers: "exit 3 with no output (silent)", "exit 3 with OK line (WARN, uncounted)", "exit 3 with unrecognized text (WARN, uncounted)", and "exit 1 with no output (WARN)". PATH-windows: emitted only on WSL.
4. Update runbooks (`ca-doctor.md` "Results and limitations" table and lines 86-87; `kernel-doctor.md`) and README's doctor description in the same commit.
5. Run `just ca-doctor-build`, `just kernel-doctor-build`, `just ci`, and `just doctor` locally on Mac.
6. Open draft PR → mark ready (CI does not run on drafts, `.github/workflows/unit-test.yaml:16,27`) → verify all CI checks pass via `gh pr checks --watch` → squash merge.

## 7. Completion criteria

- `just doctor` on this Mac: 1 ERR line (system python `ca-live`), still exit 1; at most 3 WARNs (with D1 = (a)); no `ca-chain-*` or `kernel-coverage` lines.
- `just ca-doctor` (standalone) still emits per-host lines (only 4.3 levels and wording change).
- `just ci` and all PR CI checks pass.
- On physical native Windows and WSL, the operator runs `just ca-doctor-build`, `just kernel-doctor-build`, and `just doctor` and pastes ERR and WARN lines into the PR (cross-build success is not physical verification). Also record this in Next Actions in post-merge handover.

## 8. Rollback on failure

- Since this is 1 squash-merged PR, revert with `git revert <merge commit>` and rebuild local binaries with `just ca-doctor-build` and `just kernel-doctor-build`.
- doctor.sh can still read outputs from binaries using the old protocol (without INFO) just as before (only adds INFO handling without altering the 3 existing levels).

## 9. Independent review record

Round 1 (Codex, 2026-11-01, verdict REVISE, 3 findings). All 3 verified against code and adopted:

| # | Finding | Verified | Resolution |
| --- | --- | --- | --- |
| P1 | Old binaries return `ERR ca-arguments` (exit 2) for `--summary`, which doctor.sh accepts as a valid ERR | `tools/ca-doctor/main.go:41-42` parses args before freshness; doctor.sh acceptance is at `scripts/doctor.sh:379-381` | Added old-binary handling in 4.2 and test in 6 |
| P2 | Detecting ollama applicability by OS alone diverges from excluding containers on WSL kernels; removing the 0-line check misses execution failures | `scripts/ollama_host.py:343-351`, `ollama_lines -eq 0` check in doctor.sh | Switched 4.5 to delegate to `host_policy()` and signal "not applicable" via exit 3 |
| P2 | CI does not run on draft PRs, so "pass CI before marking ready" cannot work | `.github/workflows/unit-test.yaml:16,27` | Fixed ordering in 6 |

Round 2 (Codex, `resume --last`, verdict REVISE, 1 finding). Previous P1 and item 3 judged "resolved in plan"; ollama marked "partially addressed":

| # | Finding | Verified | Resolution |
| --- | --- | --- | --- |
| P2 | Cannot detect mismatch when exit 3 also emits result lines; current loop counts OK before checking exit code and ignores unrecognized lines | `scripts/doctor.sh:456-466` increments `ok`, etc. as each line is read | Updated 4.5 to "not applicable only when exit 3 and entire output is empty", classifying lines before counting; added 4 tests in 6 |

Because finding 2 was a narrow change adopting the reviewer's exact fix directly, no round 3 review was run.

## 10. Out of scope

- Downgrading system python CA ERR to WARN (remains ERR per runbook).
- Inspecting the Podman machine VM kernel with kernel-doctor.
- Cataloging Windows / WSL / Linux-specific WARNs (unmeasurable from this Mac; plan separately after seeing `doctor` output on each machine).

## 11. Implementation results (2026-11-01, this Mac)

- `just doctor` (after rebuilding binaries in the worktree): `ok=52 warn=6 err=1 info=31` (before: `ok=55 warn=103 err=15`). Of the 6 WARNs, 5 came from `claude-plugins` marketplace path mismatch (`/Users/nino/dotfiles`) due to running from a worktree and are unrelated; the remaining 1 is system python pip 21.2.4 (`outside the reviewed fix branches (26)`). ERR is the single `ca-live` line for system python, exit 1 unchanged.
- `ca-chain-*`, `kernel-coverage`, `PATH-windows`, and `ollama-policy` no longer appear in doctor. Standalone `just ca-doctor` still emits all 84 per-host lines (6 clients × 14).
- Plan adjustment discovered during implementation: for "entire output is empty" in 4.5, checked only the checker's stdout (`2>/dev/null`). At runtime, `uv run` itself emitted a stderr warning (`VIRTUAL_ENV=... does not match the project environment path`) that mixed in via `2>&1`, causing exit 3 to be misread as non-empty output. Because ollama check stderr was already neither counted nor shown, dropping it loses nothing. Pinned by `test_uv_noise_on_stderr_does_not_break_the_silent_exit`.
