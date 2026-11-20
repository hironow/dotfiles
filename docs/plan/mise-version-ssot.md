# Make mise tool versions an SSOT (one source + generation + drift check)

**Date:** 2026-10-21
**Status:** Accepted (2026-10-21, owner decision; PR #485) / implemented
**Branch:** `feat/mise-version-ssot`
**Related:** ADR 0006 (mise pinning strategy; this generalizes and implements the build-time check promised in its §3) / ADR 0005 (install path) / ADR 0036, 0040 (npm backend is bun) / ADR 0027 (bun-only) / ADR 0044 (ruff/ty) / ADR 0051 (track decisions in queue) / Preceding: PR #484 (playwright-cli)
**Blocking decisions:** none (confirmed with user on 2026-10-21: target is **only tools mise owns**, plus the **uv / just / sheldon constants** the image installs via verified tarballs; source is **1 new file**; generator is **Python (recorded in plan and ADR as an exception to the language rule; see "Exception ruling" below)**)
**Graduates to:** ADR 0060 (Proposed, decided in user's PR comment) + pending-decision row in decision-queue. Done once stable.

## Purpose

The repository's README states that "both environments install the same tool versions from the same source", yet **versions of the same tools are handwritten in multiple places, and changes on one side go unnoticed**.

- Measured (F1–F3): `config/mise/config.toml` has 37 tools, and `/etc/mise/config.toml` baked into the devcontainer has 18 tools. Of the 18 overlapping tools, only 3 match in value (golangci-lint / quint / cf); the rest differ by generation ("host uses `latest`, image uses frozen versions"). Moreover, **the image installs the same tools via two paths, and uv and just disagree between those two paths** (tarball uv 0.12.21 vs mise frozen 0.13.1; just 1.58.0 vs 1.59.0). Because mise shims come first on PATH, mise's version wins at runtime and the mismatch stays silent.
- ADR 0006 §3 requires "mise.toml and feature constants must match; the implementing PR adds a build-time check", yet **only 1 check exists, for quint (`tests/unit/test_sandbox_check_tools.py`)** (F6).

This change consolidates the versions used by the image and bootstrap into **a single source file**, **generates** the corresponding regions of `install.sh`, and **checks** in `just check` that regeneration produces no diff. Each tool's version then lives in one place, and CI blocks single-sided bumps.

## Confirmed facts (verified against primary sources)

- **F1** (measured 2026-10-21 by parsing both files with `tomllib` + regex): `config/mise/config.toml` has 37 tools, and the `/etc/mise` heredoc in `.devcontainer/features/dotfiles-tools/install.sh` has 18 tools. 18 overlap; exact pins matching on both sides are only 3: `aqua:golangci/golangci-lint` 2.15.0, `npm:@informalsystems/quint` 0.33.0, and `npm:cf` 1.0.0-beta.18. The other 15 use `latest` (`lts` for `node`) on host and frozen versions in the image.
- **F2**: `install.sh` (root, bootstrap) pins `_mise_ver="2026.9.0"` (L172) and `_just_ver="1.58.0"` (L252). The latter already disagrees with `1.59.0`, which `just = "latest"` in `config/mise/config.toml` resolves to today.
- **F3**: The image installs the same tools via two paths. `.devcontainer/features/dotfiles-tools/install.sh` places verified tarballs in `/usr/local/bin` (`UV_VERSION="0.12.21"` L102, `JUST_VERSION="1.58.0"` L140, `SHELDON_VERSION="0.8.5"` L156), while `/etc/mise/config.toml` installs via mise (`uv = "0.13.1"`, `just = "1.59.0"`). `devcontainer.json` sets PATH to `/root/.local/bin:/opt/mise/shims:/usr/local/bin:...` (L77), so **shims win**. uv and just disagree between these two paths, and sheldon exists only on the tarball side (not baked into `/etc/mise`).
- **F4**: The consolidated target versions exist upstream (verified via `curl -o /dev/null -w %{http_code}`): uv 0.13.1 `uv-x86_64-unknown-linux-gnu.tar.gz.sha256` = 200, just 1.59.0 `SHA256SUMS` = 200, sheldon 0.8.5 tarball = 200.
- **F5**: sheldon in `config/mise/config.toml` is `aqua:rossmacarthur/sheldon = "0.8.5"` (matching the image tarball). rust (host `1.99.1` + rust-analyzer) and `RUSTUP_VERSION="1.29.1"` / `RUST_TOOLCHAIN="1.99.0"` (used to build the evaluator in the image) serve separate roles.
- **F6**: ADR 0006 §3 (`docs/adr/0006-mise-tool-version-pinning.md` L165, L191) states "fail the image build with a build-time check when feature hardcoded constants and mise.toml disagree", yet only 1 test exists: `test_quint_is_baked_at_the_same_pin_as_the_workstation`.
- **F7**: mise does not read the repo's `config/mise/config.toml` as a project config (measured with `mise config ls` in `/tmp`). The image sees only the baked `/etc/mise/config.toml` (as does `post-create.sh`). Therefore, the "image tool list" must derive uniquely from the generation source.
- **F8**: Five existing tests parse `install.sh` strings (`test_sandbox_check_tools.py` via heredoc → `tomllib`, `test_go_tooling.py`, `test_devcontainer_download_retries.py` per logical line, `test_install_mise_bootstrap.py`, `test_mise_data_dir_relocation.py`). Generated regions must preserve the formats those tests parse.
- **F9**: prek gates split by stage. **pre-commit calls `just fmt` and `just lint`** (`just-fmt` / `just-lint` in `.pre-commit-config.yaml`), whereas **`just check` is pre-push only** (`just-check`, `stages: [pre-push]`), and pre-push is not installed by default (note at top of file; the pre-push shim belongs to git-lfs). `just ci` depends on `check`. Checks meant to block commits belong in `lint` (e.g., `scripts/check_uv_exclude_newer.py` and `scripts/check_mcp_node_runner.py` are in both `lint` and `check`).
- **F10**: Generator conventions already exist (`scripts/sync_agents.py` managed blocks + `--preview`, `scripts/skills_lock.py` `dump/restore/place/check`, `scripts/bump_tool.py` "rewrite all declarations together + refusal conditions"). New ADRs are tracked as pending rows in `docs/decision-queue.md` (ADR 0051) and marked Accepted on the owner's PR comment.
- **F11**: ruff / ty are pinned in 3 places (root / emulator pyproject, `config/mise/config.toml`), and `just bump-tool` rewrites all declarations in one command (excluded from scope by user ruling).

## Changes

### 1. `config/mise/image-tools.toml` (new, source of truth)

**Frozen generation** used by the image (devcontainer) and bootstrap on hosts without mise. **Write each tool's version once.**

```toml
[settings.npm]
package_manager = "bun"

[tools]              # -> baked into /etc/mise/config.toml (18 tools)
bun = "1.4.3"
just = "1.59.0"      # the tarball path (/usr/local/bin) also uses this value
uv = "0.13.1"        # same
... (remaining 16)

[fetch]              # -> SHA/attestation-verified tarball (/usr/local/bin)
mise_tools = ["uv", "just"]   # versions come from [tools] (do not write here)
"aqua:rossmacarthur/sheldon" = "0.8.5"   # not a mise tool, so write here

[bootstrap]          # -> install.sh (Linux hosts without mise yet)
mise = "2026.9.0"    # just uses [tools].just as-is
```

- The generator `scripts/mise_versions.py` owns the mapping to each target (all `[tools]` → heredoc; `[tools].uv/just` + other `[fetch]` entries → tarball constants; `[bootstrap]` → root `install.sh`). Document this mapping in generator comments and this plan.
- Move explanatory comments currently in the heredoc (reason for npm backend, quint gate, ADR 0040 note, etc.) to the corresponding entries in this file.

### 2. `scripts/mise_versions.py` (new, generator)

- `sync`: rewrite the following regions from section 1 and output committable text:
    - `/etc/mise/config.toml` heredoc in `.devcontainer/features/dotfiles-tools/install.sh` (replace **the body between existing `cat > … <<'EOF'` and `EOF`**; do not invent new markers; body is valid TOML with a generated header + `[settings.npm]` + `[tools]`)
    - `UV_VERSION` / `JUST_VERSION` / `SHELDON_VERSION` in the same file (line-by-line replacement)
    - `_mise_ver` / `_just_ver` in `install.sh` (root) (line-by-line replacement)
- `--check`: regenerate and exit non-zero on any diff (by default without `--quiet`, print which file and region drifted).
- Also check **list and value consistency** (split comparison targets per independent review #1, #2):
    - Every key in `[tools]` and **mise tools in `[fetch]`** (`uv` / `just` / `aqua:rossmacarthur/sheldon`) must exist in `config/mise/config.toml`. Where `config/mise` has an exact pin, values must also match (this protects quint / golangci-lint / cf / sheldon today). Because `sheldon` uses an inline table on host (`config/mise/config.toml:91`), extract its `version` for comparison.
    - **Do not compare `[bootstrap]` against host.** `mise` is absent from `[tools]` in `config/mise/config.toml` (mise does not install itself), so including it in the host subset check would **fail in the normal initial state**. Compare `[bootstrap].mise` only against `_mise_ver` in root `install.sh`.
- Offline only. Because sheldon's per-arch SHA256 values are **hashes, not versions**, do not generate them (when bumping to a new release, update those 2 lines in `install.sh` alongside the source version; document this step in a comment in the source file).

#### Exception ruling: generator in Python

`ROOT_AGENTS.md` requires "new services / CLIs / tools in Go". Judging that this generator does not literally fit that category, **we write it in Python with the user's ruling (2026-10-21)**. Reasons:

- It is **glue** rewriting files inside the repo, not a distributed executable tool (not a shipped binary, so the "one binary per OS" rationale does not apply). Comparable scripts in `scripts/` are already Python run via `uv run` through `just` (`scripts/bump_tool.py` = "bulk rewrite of all declarations + refusal conditions" has the same shape).
- TOML parsing uses the **standard library (`tomllib`)**. Go would require adding a new third-party TOML parser dependency, conflicting with "standard library first".
- Tests ride on the existing pytest unit suite (`tests/unit/`) and existing Python gates (`ruff` / `ty`) in `just lint` / `just ci`.

Record this ruling in ADR 0060 as well.

### 3. `.devcontainer/features/dotfiles-tools/install.sh`

- The heredoc body becomes generated output, starting with a "Generated; written by `just mise-versions-sync`" header. Move existing explanatory comments in the block to `config/mise/image-tools.toml`.
- Update surrounding prose to point to the source file and checks (feature's "this prebuild block is the sole pin record; bump with config/mise/config.toml / project config takes precedence and consistency test guards it", and root's `_just_ver` note "bump together with just in config/mise/config.toml"). Since "project config takes precedence" contradicts measurement (repo `config/mise/config.toml` is not read as project config), align prose with reality.
- The 3 lines `UV_VERSION` / `JUST_VERSION` / `SHELDON_VERSION` become generated output.
- **Behavior change**: `UV_VERSION` 0.12.21 → 0.13.1, `JUST_VERSION` 1.58.0 → 1.59.0 (matching mise's frozen versions). Because shims already won on PATH order, the image changes only to make the duplicates match (F3). sheldon stays at 0.8.5.
- Keep the verified download structure unchanged (sha256 sidecar / `gh attestation verify` / `SHA256SUMS` grep; F4 confirmed the new version URLs are live).

### 4. `install.sh` (root)

- `_mise_ver` / `_just_ver` become generated output. **Behavior change**: `_just_ver` 1.58.0 → 1.59.0 (the bootstrap path installing just on bare Linux; eliminates F2 mismatch).

### 5. `justfile`

- Add `mise-versions-sync` (generator `sync`) and `mise-versions-check` (`--check`), and **wire `mise-versions-check` into both `lint` and `check`** (F9; pre-commit runs `lint`, `just check` / pre-push and `just ci` run `check`; same placement as `check_uv_exclude_newer.py`).

### 6. `tests/unit/test_mise_versions.py` (new)

Deterministic, offline checks. Capture RED first.

- Committed `install.sh` (both files) matches generator output (no drift).
- Generator **detects drift and exits non-zero** (verified by modifying 1 character in a temporary copy; verifies the checker itself).
- Tools in `[tools]` and `[fetch]` ⊆ `config/mise/config.toml`, and values match exact pins in `config/mise` (including extracting `version` from inline tables).
- **Normal case**: check passes even when `mise` is absent from host `[tools]` (`[bootstrap].mise` is compared only against `_mise_ver` in root `install.sh`).
- Negative cases (verifying the checker itself): `mise-versions-check` exits non-zero when changing only (a) sheldon in the source file, (b) sheldon in `config/mise`, (c) 1 character in a generated `install.sh` region, or (d) `_mise_ver` in root `install.sh`.
- **No tool version is written twice** inside the source file (reject overlaps between `[tools]` and `[fetch]` / `[bootstrap]`: the "one place" invariant).
- Constants in root `install.sh` / feature `install.sh` match source values.
- Formats read by the 5 existing tests (F8: heredoc readable by `tomllib`, constant lines remain logical lines) are preserved.

### 7. `docs/adr/0060-*.md` (Accepted after ruling), `docs/decision-queue.md` (decided log after ruling), and ADR 0006 Status

State explicitly in ADR 0060 **what is kept** and **what is replaced** (independent review #1 finding 4).

- **Kept**: verified image downloads (SHA + attestation, first half of ADR 0006 Decision 3) / rejecting `mise.lock` (same Strategy B rejection) / relocating `MISE_DATA_DIR=/opt/mise` (Decision 4) / `MISE_OFFLINE=1` in the image (Decision 5) / `config/mise/config.toml` as the cross-OS host declaration / exception ruling to write the generator in Python (above).
- **Replaced (including facts already true in current code; partly supersedes the relevant parts of ADR 0006)**:
    - **Decision 1 "turn every `= "latest"` into a concrete pin"** → Actual host pins tools needing gates/reproducibility and tracks `latest` / `lts` elsewhere (this practice solidified after 0006 was written). ADR 0060 records this role-based policy as a decision and treats host and image generation differences as separate channels.
    - **Decision 3 "image reuses verified binaries via `mise use --system`"** → Actual image installs a **separate copy into `/opt/mise` via regular `mise install` alongside verified tarballs** (`.devcontainer/features/dotfiles-tools/install.sh` has no `mise use --system`). ADR 0060 records this coexistence (versions matched via generation) as a decision.
    - **Decision 3 "fail the image build with a build-time check"** → Changes the enforcement mechanism. **Generation** from one source prevents mismatches up front, and **drift checks at commit time (`just lint`) and CI (`just ci`)** block them earlier (without waiting for image build).
    - Keep "same pin across 3 OSes" as a **claim about the host declaration**, and record the image's frozen generation in `config/mise/image-tools.toml` (with the check enforcing matching values for shared tools).
- After ruling, following `docs-discipline.md`, edit **only the Status line of ADR 0006** to show partial supersession (existing style: `Accepted; partly superseded by [0060](0060-...md) (Decision 1's "concrete pin everywhere" and Decision 3's system backend / build-time check mechanism)`). Leave the body untouched.

Move to Accepted upon the user's PR comment ruling.

Add one "pending decision" row to `docs/decision-queue.md` (ADR 0051 format: ID / What to decide / Kind / Author / Decider / Deadline = public PR), and move it to the "decided log" after ruling.

### 8. `README.md`

Update the source-file description under "Structure" (`config/mise/config.toml (pins)`) to describe the two roles (host and image).

### 9. `docs/plan/mise-version-ssot.md` (this file)

## Verification

- RED: run section 6 tests first and record failures with error messages (missing source file / `install.sh` differs from generated output).
- GREEN: `just mise-versions-check` green and `just ci` (including `check`) green.
- Semantic equivalence: diff the generated heredoc against today's and record that **the tool set and values match** (only the 2 values uv / just, comments, and markers change).
  Also verify `tests/unit/test_sandbox_check_tools.py`, `test_go_tooling.py`, `test_devcontainer_download_retries.py`, `test_install_mise_bootstrap.py`, and `test_mise_data_dir_relocation.py` stay green (in `just ci`).
- Negative cases: verify changing 1 value in the source file fails `just mise-versions-check`, and changing 1 constant in `install.sh` also fails. Also verify **blocking at the pre-commit stage**: modify 1 character in a generated region and confirm both `just lint` (what pre-commit calls) and `just check` exit non-zero.
- Real image verification: tarball constants generated from `config/mise/image-tools.toml` are actually fetched during image build.
  With Podman 5+, the configured Compose provider, devcontainer CLI, and target socket ready, run local `just test` to verify fresh build → up → exec.
  Check the CI sandbox leg when existing opt-in conditions are met; never count a skip as proof of success.
- Post-merge: because host config does not change (same set and values), `mise -C / install` is unnecessary. Run `just doctor` if needed.

## Out of scope (not doing this time)

- ruff / ty (3 locations, already moved together by `just bump-tool`; F11).
- rustup 1.29.1 / rust 1.99.0 and quint evaluator v0.7.0 used to build the evaluator in the image (build-time tools tied to quint releases, distinct from host rust).
- mise itself installed via apt (current apt repo version; pinning belongs to apt pinning, whereas this source tracks versions of tools mise installs), and scoop / brew / GitHub Actions / plugin / skill refs (different lifecycles managed by `dump` or Dependabot).
- `dump/macbook/Brewfile` and `dump/harness/*.json` (machine records / separate lock mechanisms).
- (Carried over from previous PR) adding `.playwright-cli/` to global gitignore.
- **Rewriting the generator in Go** — owner's wish (2026-10-21, "That is for later" (translated)). Added in Python with a recorded exception as repo glue (also noted under Neutral in ADR 0060). When rewriting later, replace `scripts/mise_versions.py` with a Go tool and migrate the `just lint` / `just check` wiring and tests (currently pytest).

## Risks / unverified

- The generator writes into two shell scripts; corrupting a generated region breaks image builds (mitigated by existing F8 tests + CI devcontainer leg + `just check` drift check).
- Bumping `UV_VERSION` / `JUST_VERSION` changes `/usr/local/bin` in the image. Effective versions should stay unchanged since shims win, **but attestation/SHA-verified fetches of the new versions are proven only during image build** (F4 checked only URL existence).
- If someone forgets a region is generated and edits the heredoc by hand, the next `just check` fails (intended; documented in block comments and this plan).
- Because sheldon's SHA256 cannot be generated offline, bumping sheldon updates 1 line in the source + 2 lines in `install.sh` ("version in one place, hashes next to fetch"; documented in source comments).
- Native Windows / other hosts unverified (this change covers repo files and the generator; runtime impact is only via `install.sh`).

## Ruling (2026-10-21)

The owner marked Accepted in this session ("It is ok" (translated)).
Recorded the Go rewrite as future work under "Out of scope".
Updated ADR-0060 to Accepted, moved the decision-queue row to the decided log, and updated only the Status line of ADR-0006 to partial supersession.

## Reviews

### #1 (Codex `codex exec`, 2026-10-21) — REVISE → all 4 items adopted/decided

- **Finding 1 (P2, cannot detect single-sided sheldon bump)**: excluding `[fetch]` tools from consistency checks let host-only bumps (`config/mise/config.toml:91` aqua sheldon 0.8.5) pass unnoticed.
  → **Adopted**. Include `[fetch]` / `[bootstrap]` in checks and extract `version` from inline tables. Added negative cases (a) and (b) to tests.
- **Finding 2 (P2, wiring only `check` does not stop pre-commit)**: pre-commit runs `just fmt` / `just lint`, whereas `just check` is pre-push only (and pre-push is not installed by default).
  → **Adopted**. Rewrote F9 and wiring targets from measured facts to wire both `lint` and `check`. **Correcting an error from PR #484**: reporting "each commit passed `just check`" was wrong; it actually ran `just lint`. Corrected that plan error here too.
- **Finding 3 (P2, new Python generator violates language rule)**: `ROOT_AGENTS.md` requires new services / CLIs / tools in Go.
  → **Kept Python with user ruling + recorded exception** ("Exception ruling" above), following the finding's path of recording an explicit exception ruling in the plan before implementation. Recorded the counter-arguments (stdlib TOML suffices, not a distributed binary, matches existing glue, fits existing pytest) in the plan.
- **Finding 4 (P2, conflating "fulfilling" with "changing" ADR 0006)**: 0006:170 "same pin across 3 OSes" and 0006:180 system backend differ from keeping separated generations and dual installs; "fulfills §3 / leaves 0006 unchanged" is inaccurate.
  → **Adopted**. Added "Kept / Replaced" sections to ADR 0060, and after ruling edited only the Status line of 0006 per `docs-discipline.md` to record partial supersession (matching existing phrasing).

### #2 (Codex `codex exec resume --last`, 2026-10-21) — REVISE (2 items left) → all adopted

- **Rest of finding 1 (it put a host condition on `[bootstrap].mise` that cannot be compared)**: `config/mise/config.toml` has no `mise` in `[tools]` (measured: `^mise\b` matches 0 times), so including it in the host inclusion check fails the normal case.
  → **Adopted**. Split the comparison targets (`[tools]`+`[fetch]` → host, `[bootstrap].mise` → `_mise_ver` in the root `install.sh`). Added the normal case (no `mise` on the host) and negative case (d) (only `_mise_ver` changes).
- **Rest of finding 4 (the ADR's replaced items left out the `system` backend and Decision 1's pin-everything rule)**: ADR 0006 Decision 1 says "make every `= "latest"` a concrete pin", and Decision 3 says "reuse verified binaries with `mise use --system`". Today the host follows a per-use policy, and the image does not use `mise use --system` (measured: 0 matches in install.sh; a regular `mise install` puts a separate copy in `/opt/mise`).
  → **Adopted**. ADR 0060's "Replaced" section now names Decision 1's pin-everything rule, Decision 3's system backend, and the form of the build-time check (replaced by generation plus a commit-time and CI check). These are **facts that already hold, not changes this work introduces**; ADR 0060 records them as decisions.

### #3 (Codex `codex exec resume --last`, 2026-10-21) — APPROVE

Confirmed resolution of the remaining 2 items (splitting comparison targets, ADR replacement scope). No remaining blocking findings (noting approval covers the plan, not implementation/test results yet).

### Implementation and gates (2026-10-21)

- RED → GREEN: `tests/unit/test_mise_versions.py` ran **3 failed / 9 passed** before sync (only the 3 drift-dependent tests), then **12 passed** after sync. All 5 existing `install.sh`-dependent tests (26 tests) stayed green (heredoc shape and constant lines preserved = F8).
- Generation diff: `UV_VERSION` 0.12.21 → 0.13.1, `JUST_VERSION` 1.58.0 → 1.59.0, `_just_ver` 1.58.0 → 1.59.0. Heredoc tool set and values are identical (comments moved to source, generated header added).
- `just lint` (pre-commit target) and `just ci` green (final: `just ci` EXIT 0, unit 1726 passed / 33 skipped). Independent diff review approved at #3 (all 4 prior findings adopted below).
- **Two self-mistakes (recorded)**: (a) `tmp_path / <absolute path>` stayed an absolute path per pathlib behavior, so negative tests **overwrote real files (`config/mise/config.toml`, both `install.sh` files, and the source file)** (recovered via `git checkout` and hand-fixing the source). To kill this bug class, added 3 test assertions: "relative paths only", "stay inside checkout", and "fail if `str.replace` misses" (`tree()` / `mutate()`). (b) Reporting in PR #484 that "each commit passed `just check`" was inaccurate — pre-commit calls `just lint`. Corrected in F9 and Review #2.
- **Diff review #1 (Codex) = REVISE (2 × P2) → both adopted** (with reproduction):
    - Consistency check allowed `latest` in the source file (allowing image to track latest while host stayed pinned) → allow only concrete versions in the source file, and require exact match if host is pinned. Added negative case (quint = `latest`).
    - Unescaped TOML strings produced broken output from valid inputs containing quotes/backslashes (reproduced with quotes in `rename_exe`) → implemented key/value escaping and **self-checked by re-parsing generated TOML with `tomllib` before writing to verify equality with the source**. Added boundary-input tests.
- **Diff review #2 (Codex) = REVISE (2 × P2) → both adopted** (with reproduction):
    - Loose "concrete version" check accepted `24` / `prefix:24` / empty string (mise request syntax resolves partial versions to moving targets) → allow only full versions (`X.Y.Z` + prerelease) and apply to `[bootstrap]` too. Added negative tests.
    - Inline tables (e.g., `uv = { version = "0.13.1" }`) were written into shell constants as Python dict reprs, breaking fetch URLs (reproduced `UV_VERSION="{'version': '0.13.1'}"`) → extract `version` via `concrete()` and added tests.
- **Issue caught by repo's own check**: first `just ci` failed in `tests/unit/test_text_io_encoding.py` (requiring `encoding=` on `subprocess.run(text=True)`; 1 failed / 1721 passed). Fixed and re-ran.
