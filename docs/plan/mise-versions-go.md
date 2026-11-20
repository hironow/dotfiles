# Port the version generator from Python to Go (stdlib only + Python as oracle)

**Date:** 2026-10-21
**Status:** done (→ [ADR-0061](../adr/0061-version-generator-in-go.md), [tools/mise-versions/README.md](../../tools/mise-versions/README.md)). ADR-0061 Accepted via [decision in #486](https://github.com/hironow/dotfiles/pull/486#issuecomment-6314535355). Merged in [#486](https://github.com/hironow/dotfiles/pull/486) (main `b59476e1`)
**Branch:** `refactor/mise-versions-go`
**Related:** [ADR-0060](../adr/0060-frozen-image-generation-has-one-source.md) (replaces Decision 5 and Decision 2 writer specification → ADR-0061), [ADR-0052](../adr/0052-renew-global-agent-instructions.md) (distribution exception for `go run` on this generator only) / `ROOT_AGENTS_docs_agents_go-tooling.md` (stdlib first; third-party modules need a platform reason) / `ROOT_AGENTS_docs_agents_dependency-policy.md` / Preceding: PR #485 (version SSOT)
**Blocking decisions:** none (confirmed with user on 2026-10-21: **Go stdlib only**, **custom parser for only the required TOML subset**, correctness verified independently using **remaining Python tests as an oracle (`tomllib`)**)
**Graduates to:** ADR-0061 (Accepted)

## Purpose

The version generator added in PR #485 is `scripts/mise_versions.py` (Python, using stdlib `tomllib`).
ADR-0060 Decision 5 recorded it as an "exception to the language rule (new tools in Go)", and the owner stated, "I want to rewrite it in Go in the future" (translated).

This change performs that port. **Behavior stays unchanged** (same CLI, same generated output, same checks).
Correctness is guaranteed two ways: (a) Go unit tests, and (b) keeping Python tests as an **oracle** that independently verifies generated output with `tomllib`.
We also record that **both `install.sh` files are byte-identical before and after the port**.

## Confirmed facts (verified against primary sources)

- **F1**: The current generator is `scripts/mise_versions.py` (Python, stdlib `tomllib`). `just lint` (pre-commit) and `just check` / `just ci` invoke `{{UV_RUN}} scripts/mise_versions.py check`, and `just mise-versions-sync` invokes `sync`. Five regions are generated: `/etc/mise/config.toml` heredoc body, `UV_VERSION` / `JUST_VERSION` / `SHELDON_VERSION`, and `_mise_ver` / `_just_ver` in root `install.sh`.
- **F2**: Go module conventions: dedicated module under `tools/<name>/` (`tools/simple-server/` precedent: `go.mod` + `main.go` + `main_test.go` + `README.md` + empty `go.sum`), `module <name>` / `go 1.27`. Share root `.golangci.yaml` via `--config`; `just go-lint` (`golangci-lint run` + `fmt --diff`) and `just go-test` (`go test -short ./...`) automatically pick up `*go.mod`. `.golangci.yaml` uses only gofumpt as formatter and enables gocyclo / gosec / revive, etc. (functions must stay small).
- **F3**: The `go-tooling` spoke states "standard library first; third-party modules require a platform reason (Cloud client / protocol SDK)". Because Go's stdlib lacks a TOML parser, write a **custom parser for only the required subset** (user ruling). **Fail on unknown syntax** (never misread silently).
- **F4**: Required TOML constructs are limited. `config/mise/image-tools.toml` (ours, small): comments, `[settings.npm]`, `[tools]` (strings and 1 inline table), `[fetch]` (string array `mise_tools` and strings), `[bootstrap]`. `config/mise/config.toml` (large, handwritten): each key under `[tools]` is a string or inline table (`{ version = "...", os = [...], ... }`). Quoted keys (e.g., `"npm:cf"`) appear in both.
- **F5**: Current checks cover 4 areas: (a) generated output matches committed files (drift), (b) host consistency (tools in `[tools]` and `[fetch]` exist in `config/mise/config.toml`, and values match when host has an exact pin; `[bootstrap].mise` is absent on host so compared only against `_mise_ver` in `install.sh`), (c) source values are full versions only (`X.Y.Z` + prerelease), (d) round-trip of generated TOML. Plus a structural check that "no version is written in two places".
- **F6**: Current test suite is `tests/unit/test_mise_versions.py` (16 tests), including 3 drift-dependent tests, detection of 4 single-sided edits (source only / host only / generated region / `_mise_ver`), and idempotency. Five existing `install.sh`-dependent tests (26 tests: `test_sandbox_check_tools` / `test_go_tooling` / `test_devcontainer_download_retries` / `test_install_mise_bootstrap` / `test_mise_data_dir_relocation`) protect the heredoc and constant-line formats.
- **F7**: Single-file Go programs run from outside the module via `go run tools/<name>/main.go ...` (file mode, as in `justfile`'s `tools/simple-server/main.go` precedent). Multiple files would require `cd tools/<name> && go run .`.
- **F8**: Pre-port baseline blobs (used for equivalence verification): `.devcontainer/features/dotfiles-tools/install.sh` = `6031f9ae9642955066b95d0d06aa7197b3899ee9`, `install.sh` = `8f89c6d635d956cfab8055e14d665240f5d3908a` (`git hash-object`).

## Changes

### 1. `tools/mise-versions/` (new Go module, stdlib only)

- `main.go` (single file; keep F7 file mode so `justfile` can call `go run tools/mise-versions/main.go …`):
    - CLI: `mise-versions sync|check [--root DIR]`. **Default root preserves current behavior: "checkout resolved from the running source location"** (`runtime.Caller(0)` locates `tools/mise-versions/main.go` and steps up 2 levels; explicit `--root` wins; current Python uses `Path(__file__).resolve().parents[1]`, keeping the rule compatible). Match exit codes and output (`check` reports drift and exits non-zero; `sync` lists modified files).
    - TOML subset reader: comments / blank lines / table headers / bare & quoted keys / basic strings (resolving `\"` `\\` `\n` `\r` `\t` `\uXXXX` escapes) / inline tables / string arrays. **Unknown syntax fails with line number.**
    - Generation: write heredoc body and 5 constants using the same order and escaping (quote keys only when needed, escape values). Before writing, **self-check by re-parsing the generated TOML with the same parser and verifying equality with the source**.
    - Checks: 4 checks from F5 + structural check. For host config `[tools]`, read only required keys (interpret unknown shapes within F4; error on unparseable keys). **Run all checks before writing** (preserving validate-first so a failed `sync` modifies neither file).
- `main_test.go`: parser boundaries (quotes / escapes / inline tables / arrays / comments / rejecting unknown syntax), generation round-trip, detecting 4 single-sided edits, idempotency, temp trees via `--root`.
- `README.md` (following `tools/simple-server/README.md`): what the tool does, `sync` / `check` usage, `config/mise/image-tools.toml` as source of truth, and integration in `just lint` / `just check`.
- `go.mod` (`module mise-versions` / `go 1.27`) and empty `go.sum` (zero dependencies).

### 2. `tests/unit/test_mise_versions.py` — **rewrite as oracle**

Stop importing generator internals and **invoke it as a CLI**. Verify independently using `tomllib` (checking the Go parser's correctness with an independent implementation).

- Committed `install.sh` (both files) pass `check` with no drift.
- Generated heredoc parses with `tomllib` and **matches `settings` / `tools` in the source exactly** (= escaping and serialization oracle).
- All 5 constants match source values.
- Independently compute host consistency (`[tools]` / `[fetch]` ⊆ host, exact pin match, `[bootstrap].mise` compared only against `_mise_ver`) using `tomllib` and verify agreement.
- 4 single-sided edits (temp tree) make `check` exit non-zero.
- Structural check that "no version is written in two places".

### 3. `justfile`

- Unify `lint` (currently invokes `{{UV_RUN}} scripts/mise_versions.py check` directly) and `check` legs to **call `just mise-versions-check`** (consolidating implementation into one recipe so legs do not break after deleting the script). Switch `mise-versions-check` / `mise-versions-sync` to Go (`mise exec -- go run tools/mise-versions/main.go check` / `… sync`). Keep wiring targets (`lint` and `check`) unchanged.

### 4. Delete `scripts/mise_versions.py`

### 5. `docs/adr/0061-*.md` (Proposed) + `docs/adr/README.md` + `docs/decision-queue.md`

"Generator in Go (stdlib only, custom TOML subset + Python oracle)."
During follow-up alignment consultation, the owner approved scoping supersession to ADR-0060 Decision 5 and Decision 2's writer implementation/path specification, plus ADR-0052 Decision 1's `go run` distribution exception for this generator only.
After recording the ruling by proxy on the public PR, update **only the Status line** of those 2 older ADRs to partial supersession. Leave their bodies untouched.

### 6. `docs/plan/mise-versions-go.md` (this file)

## Verification

- **Port equivalence (two stages, addressing finding #4)**:
    - **Stage A (unchanged header)**: run `sync` with the Go version emitting the **exact same generated header string** as today, and record that both `install.sh` files are **byte-identical** to F8 blobs (proving the port preserves semantics).
    - **Stage B (comment update)**: update the generated header and surrounding prose (note above `_just_ver` in `install.sh`, feature prebuild note, `GENERATED by …` in header) to the Go tool name (`tools/mise-versions/main.go`). Show via `git diff` that **only comment lines changed** (generated TOML and constant values unchanged). Leave historical notes in ADRs / plans untouched (historical records).
- **RED → GREEN**: write Go tests first and record build/test failures before implementing; same for oracle tests.
- **Oracle (Python + `tomllib`) — comparing accepted syntax and rejections (addressing finding #2)**:
    - Generated heredoc parses with `tomllib` and **matches `settings` / `tools` in the source exactly**.
    - All 5 constants match source values.
    - **Boundary inputs (via CLI)**: put values with quotes/backslashes (e.g., `rename_exe`) in source → `sync` → re-parse with `tomllib` and verify match; inline-table tool (e.g., `uv = { version = "0.13.1" }`) → `UV_VERSION="0.13.1"`.
    - **Invalid inputs rejected by both Go and `tomllib`**: put duplicate keys / table redefinitions / invalid escapes into source, confirm `check` exits non-zero, and confirm `tomllib` also rejects them. **Failed `sync` modifies neither output file** (preserving current validate-first behavior).
    - 4 single-sided edits (source only / host only / generated region / `_mise_ver`) make `check` exit non-zero.
    - Structural check that "no version is written in two places".
    - **Default root compatibility (addressing finding #3)**: running from another directory (e.g., `/tmp`) targets the checkout, and explicit `--root` takes precedence.
- `just go-lint` (`golangci-lint run` + `fmt --diff`) / `just go-test` / `just ci` (EXIT 0, including updated `lint` and `check` legs). Measure and record `go run` execution time (since it runs in pre-commit).
- All 5 existing `install.sh`-dependent tests (26 tests) stay green.
- After deletion, `grep` confirms no references to `scripts/mise_versions.py` remain in **executable code or current documentation** (excluding historical notes in ADRs / plans).

## Out of scope (not doing this time)

- Porting other Python glue (`scripts/bump_tool.py`, `scripts/check_*.py`, `scripts/skills_lock.py`, etc.) to Go. Same rationale applies, but out of scope here.
- Full TOML spec support (only the required subset; fail on unknown syntax and extend only when needed).
- `tools/rttm` ruff 0.17.0 → 0.17.1 (separate item).
- Updating `docs/handover.md` (separate item).

## Risks / unverified

- **Misreading by the custom parser** is the largest risk. Mitigations: (a) fail on unknown syntax, (b) `tomllib` oracle tests (independently recomputing generated output and host consistency), (c) byte-level equality before/after porting.
- `go run` compiles on demand (expected ~0.3 s warm from build cache). Since it runs on pre-commit `just lint`, measure it and consider reusing a built binary if slow (measured during verification of this plan).
- Adds 1 Go module (`go.sum` empty = zero dependencies). Increases Dependabot Go group surface, though zero dependencies should yield zero PRs.
- Native Windows: handle `go run` path separators and `--root` resolution in Go using `filepath`. No physical Windows run here (keep `tests/unit` passing on native Windows).

## Reviews

### #1 (Codex `codex exec`, 2026-10-21) — REVISE → all 4 items adopted

- **Finding 1 (P1, swapping only the recipe breaks `lint` / `check`)**: current `lint` and `check` call `{{UV_RUN}} scripts/mise_versions.py check` directly (verified: 4 locations in justfile) and will fail after deletion.
  → **Adopted**. Specified in Changes: "unify `lint` / `check` legs to `just mise-versions-check` and consolidate implementation into one recipe".
- **Finding 2 (P1, insufficient oracle test coverage)**: comparing committed data alone cannot catch implementations that only handle normal inputs or accept invalid input only to fail on drift.
  → **Adopted**. Added CLI-level boundary inputs (escapes / inline tables), duplicate keys / table redefinitions / invalid escapes verified against **both Go and `tomllib` rejections**, and verifying failed `sync` writes nothing.
- **Finding 3 (P2, default root incompatibility)**: current Python uses `Path(__file__).resolve().parents[1]` (script checkout), whereas plan wrote cwd.
  → **Adopted**. Matched compatibility rule resolving checkout from `runtime.Caller(0)`, added `--root` precedence and "invoke from another directory" to acceptance tests.
- **Finding 4 (P2, byte-identity conflicts with removing old path)**: generated header itself contains `scripts/mise_versions.py`, so old path cannot be removed while staying byte-identical.
  → **Adopted**. Split verification into two stages (Stage A: unchanged header for byte identity → Stage B: comment-only update shown by diff). Scoped old-path grep to executable code and current docs, excluding ADR / plan history.

### #2 (Codex `codex exec resume --last`, 2026-10-21) — APPROVE

Rechecked all 4 resolutions against current code. No remaining blocking findings (plan approval).

### Implementation and gates (2026-10-21)

- **Stage A (equivalence)**: Go version with unchanged generated header gave `check` = `up to date`, `sync` wrote nothing. `git hash-object` matched pre-port (`.devcontainer/…/install.sh` = `6031f9ae…`, `install.sh` = `8f89c6d6…`).
- **Stage B**: updated header and prose to Go tool name (`tools/mise-versions/main.go`). Diff after `sync` was **3 comment lines only** (verified with `git diff`; generated TOML and constant values unchanged). Updated old path in 4 justfile places (→ recipe call and Go invocation) and 2 prose places; none remain in executable code or current docs.
- **RED → GREEN**: Go first failed `go test` to build due to unimplemented references (RED) → green after implementation. Python oracle rewritten to CLI-driven: **17 passed**.
- **lint**: `golangci-lint run` = **0 issues** (fixed gofumpt formatting, gosec G115 rune conversion, perfsprint, and struct alignment — 3 items). `go test -short` also green.
- **Speed**: `check` took **2.07 s** in Python vs **2.12 s** in Go (including `mise exec`, warm). Cold `go run` build adds **+9 s** once.
- Removed `scripts/mise_versions.py` (`git rm`).
- First `just ci`: **EXIT 1** (formatting in Python oracle test). Wrapper exited 0 on notification, while inner EXIT 1 was the true result. Fixed formatting; re-run returns inner exit code directly.
- Re-run `bc90261c6`: **EXIT 0**. Because it overlapped with edits, not used as final guarantee; re-run once more after all edits finish.

### Implementation review #1 — REVISE (6 items)

1. Windows `write_text` converts to CRLF → set `newline="\n"` and check LF bytes after modification. Also handle `.exe` suffix explicitly. Physical native Windows execution unverified.
2. Accepted empty array elements and invalid inline-table commas → parent reproduced in temp copy (`tomllib` rejects, Go `sync` exited 0). Reject empty elements while allowing trailing commas in arrays.
3. Allowed redefining/extending an inline table via section header → parent reproduced (same). Treat inline tables as closed and reject appending.
4. Accepted raw control chars and invalid UTF-8 in basic strings → parent reproduced accepting raw 0x01. Validate control characters in strings and UTF-8 across input.
5. Host `[tools]` redefinitions vanished during extraction → parent reproduced (same). Parse preserving headers and original line numbers to reject duplicates.
6. Oracle invalid inputs could appear to pass by failing later on version checks or drift → confirmed in code. Changed to equal-value duplicate keys and invalid escapes in non-version metadata, requiring syntax-error line numbers in both `check` / `sync` and byte invariance of both output files.

Also added regression tests for whitespace normalization in headers and rejecting invalid headers. New Go tests were observed failing on 11 syntax cases and host header duplicates before the fix.

### ADR alignment review #1

Codex read all 60 ADRs and compared the other 59 across 5 categories, noting that 0060 Decision 2's writer specification is also superseded, 0052 distribution requirements apply, and cross-references were missing.
Parent verified against original texts, and the owner approved the exact supersession scope and the `go run` exception limited to this generator, permitting proxy recording on this PR.

Clarified that partial versions are valid TOML and separated syntax checks from version semantic checks.
Updated Proposed format, reversal conditions, alternatives, and undecided status.
Initial rubric R1–R10 = 1/1/1/2/2/1/1/1/1/0 (11/20). Not finalized before re-check and public ruling record.

### Implementation review #2 — REVISE (2 items)

- Applied subset restrictions to non-target host headers (quoted / deeply nested tables) → separated checking whether the leading component is `tools` from strict validation of target headers.
- `TrimSpace` stripped NBSP / VT / FF, which are invalid in TOML → standardized on trimming only space / tab. Normalize CRLF separately and reject raw control characters even in comments.

Parent's CLI oracle observed **5 failed** before the fix (3 invalid whitespace, 2 non-target headers).
After fix `bd0ba4722`: **EXIT 0**: Go lint **0 issues**, Go tests pass, oracle 33 + existing install-dependent 26 = **59 passed**. Physical Windows unverified.

ADR rescore 17/20 (1/2/2/2/2/2/1/2/2/1). Added missing Japanese summary. R1/R10 remain pending public ruling URL.

### Final review and gates

- Codex implementation review #3 (`be886bb5b`): **APPROVE**. Verified statically that the remaining 2 findings are resolved and ADR scope is exact. Does not imply independent test execution.
- Post-code-freeze `just ci` (`bb427c485`): **EXIT 0, 1743 passed / 33 skipped**, including Go lint/test for the new module and generation drift checks.
- Parent verified existence of relative Markdown links in the new ADR, plan, queue, and index, fixing wrong paths for 0025/0050.
- First `just test` timed out at the 40-minute limit after image build succeeded (29% of tests, zero assertion failures). Re-run on latest commit `b03506cfd`: **EXIT 0, 126 passed / 0 skipped, 2389.66s**.
- [PR CI](https://github.com/hironow/dotfiles/actions/runs/39590732935) passed all 6 checks on `bde7401`. CI sandbox log also shows **126 passed / 0 skipped**. After the final record-only commit, re-verify all CI checks on the latest SHA.
- ADR filing re-evaluation (parent): R1–R10 = 1/2/2/2/2/2/2/2/2/1 (18/20). Not finalized prior to recording public ruling URL.
- Verified body and URL of [PR #486 proxy ruling record](https://github.com/hironow/dotfiles/pull/486#issuecomment-6314535355) (posted with owner permission) via API. Marked 0061 Accepted, updated only Status lines of 0060/0052, and synced queue and index. Adoption rubric (parent): all 2s across R1–R10 (20/20), backed by public ruling, independent reviews, cross-references, and invariance checks.
- Separate follow-up: `tools/rttm` Ruff stays at 0.17.0. Re-checked PyPI at 2026-10-21T12:22:27 UTC: 0.17.1 was published 2026-10-15T15:22:33.667796 UTC, so 7 days elapse at 2026-10-22T15:22:33.667796 UTC. Do not relax quarantine.
