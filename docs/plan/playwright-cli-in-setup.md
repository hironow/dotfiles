# Add playwright-cli to initial setup (mise declarations)

**Date:** 2026-10-21
**Status:** done (→ playwright-cli comments in `config/mise/config.toml`). Merged in [#484](https://github.com/hironow/dotfiles/pull/484) (main `bfb36079`). Follow-up for the fallback line in hironow/skills is also done (skill now instructs `bunx --package @playwright/cli`). Closed by owner instruction (2026-11-02, chat)
**Branch:** `feat/playwright-cli-mise`
**Related:** ADR 0006 (mise pinning strategy) / ADR 0023 (activate-only) / ADR 0017 (retired pnpm global → global CLIs via mise `npm:` backend) / ADR 0027, 0036, 0040 (Node is bun, npm backend is bun, bun uses `bun_args`) / `playwright-cli` skill in hironow/skills (declared in `dump/harness/skill-lock.json`)
**Blocking decisions:** none (confirmed with user on 2026-10-21: version is `latest` / do not install bundled browsers / scope is `config/mise/config.toml` only)
**Graduates to:** `done` once stable. No new decision, so no ADR is created (rejected alternatives and reasons remain in this plan)

## Purpose

The `playwright-cli` skill in hironow/skills assumes `playwright-cli` is on PATH (F1).
However, the CLI itself is not declared in initial setup on any machine, and the skill's fallback `bunx --package @playwright/mcp playwright-cli` also fails (F2).
Add 1 line to `config/mise/config.toml` so `install.sh` → `mise install` (initial setup on Mac / Linux / WSL) puts it on PATH.
Keep scope limited to this change (do not touch global gitignore from F8 here; see "Out of scope").

## Confirmed facts (verified against primary sources)

- **F1**: `playwright-cli` is not installed on this Mac (`command -v playwright-cli` is empty; absent from `mise ls --current`). Only the skill exists at `~/.agents/skills/playwright-cli`, symlinked to `~/.claude/skills` and `~/.codex/skills`.
- **F2**: The skill's fallback does not work. `@playwright/mcp` on the npm registry exposes only `bin: playwright-mcp` across all 14 recent releases (no version ships a `playwright-cli` bin). `@playwright/cli` (`bin: {playwright-cli: ...}`) provides `playwright-cli`.
- **F3**: Running `mise install` for `"npm:@playwright/cli" = "0.1.22"` with a dedicated `MISE_DATA_DIR` installs to `installs/npm-playwright-cli/0.1.22/bin/playwright-cli`, and `mise which playwright-cli` returns that path (`--version` is `0.1.22`). **However, separating `MISE_DATA_DIR` (and scratch `HOME`) does not isolate the declared tool set**: on this machine mise also reads the user's global config, so `mise install` installed 36 tools (4.1 GB) (measured 2026-10-21). Only the installation destination is isolated.
- **F4**: No browser binary is downloaded. After installing `latest` (→ 0.1.22) with `PLAYWRIGHT_BROWSERS_PATH` set to an empty dedicated dir, and after `open --browser=chrome` → `close`, that dedicated dir remained empty (0 entries), and existing `~/Library/Caches/ms-playwright/chromium-*` did not grow (measured 2026-10-21). However, the CLI does write small metadata (`b/browser@<hash>` 1.1 KB × n and `cli-update-check.json`) to default `~/Library/Caches/ms-playwright/`.
- **F5**: Verified live with Chrome on this Mac: `playwright-cli open --browser=chrome https://example.com` opened headless and `close` succeeded (works without bundled browsers). Output went to `.playwright-cli/` in the working directory.
- **F6**: `@playwright/cli` `latest` is `0.1.22` (published 2026-09-28); `next` is `0.1.18-alpha-...`. `0.1.22` depends on `playwright` / `playwright-core` `1.64.0-alpha-...` (pinned by the package).
- **F7**: mise does not read `config/mise/config.toml` as a project config (`mise config ls` in a `/tmp` dir containing `config/mise/config.toml` resolves only `~/.config/mise/config.toml`). The devcontainer's `post-create.sh` reads baked `/etc/mise/config.toml`. Therefore, this addition does not appear in image or sandbox tool lists.
- **F8**: `playwright-cli` creates `.playwright-cli/` in cwd by default (measured in F5). `dump/gitignore-global` (`just deploy` places it at `~/.config/git/ignore`) lists `.cursor/`, `.cline/`, `.copilot/`, and `.indexing/`, but not `.playwright-cli/`.
- **F9**: Homebrew also has `playwright-cli` 0.1.22, depending on brew's `node` (pulling in brew's node separately from mise's node).
- **F10**: `just bump-tool` is dedicated to ruff / ty (`TOOLS` in `scripts/bump_tool.py`). `npm:` tools (portless / quint / cf, etc.) are updated manually line-by-line.
- **F11**: `latest` resolved to **0.1.22** (`mise install` printed `mise ✓ npm:@playwright/cli@0.1.22`, dir name under `installs/npm-playwright-cli/`). `--version` printed `0.1.22`, `open --browser=chrome https://example.com` returned `Page Title: Example Domain`, and `close` succeeded. Live run took place outside the repo (`/tmp/pwiso`), creating no `.playwright-cli/` in the repo.

## Changes

### 1. `config/mise/config.toml` — `"npm:@playwright/cli" = "latest"`

Place in the "AI agent CLIs" block (`npm:@openai/codex`, etc.). Note in comments:

- CLI assumed on PATH by hironow/skills' `playwright-cli` skill (skill fallback is broken).
- Not a gate tool, so `latest` like other agent CLIs.
- `npm:` resolves via `[settings.npm] package_manager = "bun"` (ADR 0036 / 0040); does not invoke npm / yarn / pnpm, so compatible with bun-only (ADR 0027).
- Do not install bundled browsers (use `--browser=chrome` or run `playwright-cli install-browser` if needed).
- Do not run `playwright-cli install --skills` (skills are managed by hironow/skills and `just skills-place`).

### 2. `tests/unit/test_mise_playwright_cli.py` (new)

Guardrail for the declaration. Capture RED first. Deterministic (offline).

- `npm:@playwright/cli` exists under `[tools]` in `config/mise/config.toml`.
- Key is not `playwright` (the test runner itself) or a registry alias (`npm:playwright` is a different package).
- Value is `latest` or an exact semver (reject empty, ranges, or `^` notation).

### 3. `docs/plan/playwright-cli-in-setup.md` (this file)

## Verification

- RED: run tests before Change 1 and record failures with error messages.
- GREEN: `just ci` (including unit) green. Because no test enumerates all keys of `[tools]` (reads in `tests/unit/` target rtk / headroom / quint / ruff / ty by name), this does not affect other gates.
- Isolated physical verification (verifying `latest` resolution and no bundled browsers together; independent review #1 finding 2):
    - Place config under dedicated `MISE_DATA_DIR` and scratch `HOME`, and set **`PLAYWRIGHT_BROWSERS_PATH` to an empty dedicated dir**. Run outside the repo (preventing `.playwright-cli/` in repo). Because the declared tool set is not isolated, also record the list and size of installed tools (F3).
    - Run `mise install` with `"npm:@playwright/cli" = "latest"` and record the **resolved actual version** (dir name under `installs/npm-playwright-cli/`) (F11).
    - Verify `PLAYWRIGHT_BROWSERS_PATH` stays empty both right after install and after `--version` / `open --browser=chrome` → `close`, and that no browser binary was added to default `~/Library/Caches/ms-playwright` (CLI metadata itself is written; F4).
- Post-merge on main: `mise -C / install` → `just deploy` → `just doctor` (record ok / warn / err counts) → `playwright-cli --version` in a mise-activated shell.
- Devcontainer verification: in addition to F7 static checks, run `just test` with Podman 5+, the configured provider, CLI, and socket ready.
  Never claim runtime success from static checks alone.

## Out of scope (not doing this time)

- Bundled browser install (adding `install-browser` to `install.sh`) — rejected by user decision; Chrome suffices (F5).
- Baking into `/etc/mise` in the devcontainer image — sandbox is for `just check` and has no browser (F7).
- Adding `brew "playwright-cli"` to `dump/macbook/Brewfile` (F9) — Mac-only, pulls brew's node, and conflicts with the policy that global CLIs use mise `npm:` (ADR 0017, corepack section comments in `install.sh`).
- Fixing the skill's fallback line — handled in hironow/skills; note as a follow-up in the PR body.
- Adding `.playwright-cli/` to global gitignore (F8) — independent config change affecting untracked-file display across all repos, so exclude from this PR (independent review #1 finding 1; also matches user-confirmed scope "`config/mise/config.toml` only"). Propose in a separate PR if `.playwright-cli/` becomes a nuisance in repos using the CLI.
- Extra checks in `scripts/ai_tools_check.py` / doctor — Change 2 tests enforce declaration presence; adding to doctor is separate.

## Risks / unverified

- Native Windows: `install.sh` skips `mise install` on Windows, where `bootstrap.ps1` installs mise. The Windows `npm:` + bun path is not physically verified in this plan (same path as other `npm:` tools).
- Because of `latest`, CLI command syntax could change. The skill in hironow/skills is pinned to upstream commit `metadata.upstream: microsoft/playwright-cli@655530f`. Switch to a pin if breakage occurs (manual bump per F10).
- The CLI writes `~/Library/Caches/ms-playwright/cli-update-check.json` on startup (F4). Disabling update checks/telemetry is not handled here (separate layer from rtk/headroom in ADR 0047).
- The F5 live run ran inside main's working tree and created `.playwright-cli/` (deleted; main is clean).

## Reviews

### #1 (Codex `codex exec`, 2026-10-21) — REVISE → all adopted

- **Finding 1 (P2, scope mismatch)**: despite `Blocking decisions` stating "scope is `config/mise/config.toml` only", global gitignore changes and tests were included in the same PR. Separate independent config changes.
  → **Adopted**. Removed gitignore changes and tests, moving them to "Out of scope" as a follow-up. Separating changes affecting untracked display across all repos from CLI declaration checks is right.
- **Finding 2 (P2, missing verification of no bundled browsers)**: separating `MISE_DATA_DIR` does not isolate browser caches, and F4 on pinned 0.1.22 alone does not generalize to `latest` resolution.
  → **Adopted**. Added steps under "Verification" setting `PLAYWRIGHT_BROWSERS_PATH` to an empty dedicated dir and confirming no browser binaries exist both after install and after Chrome execution, then ran it (F4, F11: `latest` → 0.1.22, dedicated dir 0 entries before/after, Chrome run succeeded). This also revealed our earlier phrasing "isolated" was inaccurate (`MISE_DATA_DIR` separation does not isolate the declared tool set; updated F3 with measured facts).

### #2 (Codex `codex exec resume --last`, 2026-10-21) — APPROVE

- Confirmed resolution of findings 1 and 2 ("No further required fixes"). Accepted our measurements as reported (did not re-run). Judged that because the new declaration rides existing paths (global mise config + `mise -C / install`) and `just ci` covers unit tests and `just check`, no extra mechanism is needed at this scale.

### Post-implementation gates

- `just ci` (worktree `feat/playwright-cli-mise`): exit 0 (fast gate passed; includes markdownlint 0 issues, semgrep 0 findings, forbidden-token branch/tree clean).
- RED → GREEN: `tests/unit/test_mise_playwright_cli.py` ran 2 failed / 1 passed before the declaration, then 3 passed after.
