# Project conventions for hironow/dotfiles (repo-side)

This codebase is yours: what it's for and how it's built are your call, and you'll keep building on it.

This file records the working rules for **developing the dotfiles repository itself**.
The **hub-and-spoke agent instruction sources** in this repo are the canonical source for global rules shared across all agents (TDD, tooling, commit discipline, observability, and so on), and `just sync-agents` distributes them to each agent's config directory (where they are read as `~/.claude/CLAUDE.md` and similar after deploy).

## Repo role and the two-layer agent instruction structure (most important)

One main purpose of this repo is to **distribute global agent instructions**. The instructions use a **hub-and-spoke** structure (short always-loaded hub + on-demand spokes + mechanical enforcement).

- **Canonical sources are `ROOT_*` at the repo root** (sentinel names so agents do not read them directly):
  `ROOT_AGENTS.md` = cross-tool **base**, `ROOT_CLAUDE.md` = Claude **overlay**
  (imports base via `@AGENTS.md`), `ROOT_AGENTS_docs_agents_*.md` = on-demand **spoke**,
  `ROOT_AGENTS_hooks_*` + `.claude/settings.hooks.json` = hooks,
  `.claude/settings.shared*.json` / `.claude/settings.profiles/` = layered settings fragments (ADR 0037).
- **`just sync-agents` distributes them to each agent home** (base → `~/.codex/AGENTS.md` /
  `~/.gemini/GEMINI.md` / `~/.claude*/AGENTS.md`, overlay → `~/.claude*/CLAUDE.md`,
  spoke → `<agent>/docs/agents/`, hooks go to Claude profiles and Codex (generated from the same canonical source for Codex), settings go to Claude profiles only; both merge update-in-place).
  It does not sync skills or Antigravity's self-managed areas.
  Read `docs/agent-sync.md` before touching `scripts/sync_agents.py`, `ROOT_*`, or `.claude/settings.*.json` (covers absolute-path rewriting for spoke references, hook block ownership and preserving third-party hooks, 4-layer settings composition and full ownership of env, skills, and Antigravity).
- **To change global rules, edit the source and run `just sync-agents`.**
  Direct edits to deployed files (such as `~/.claude/CLAUDE.md`) are overwritten on the next sync.
- **Per-repo enforcement lives as a scaffold in `templates/agent-baseline/`** (not applied to dotfiles itself; expand into a new repo with `just scaffold-agent-baseline <dir>`).
- **This file (`CLAUDE.md`, repo root) is separate** = development rules for the dotfiles repo.
  It is excluded from sync (sync writes only to agent dirs in home and does not touch the repo root). Assistants working in this repo read both the global instructions (`~/.claude/CLAUDE.md` = overlay+base) and this file.

```bash
just sync-agents            # ~/.claude only (default)
just sync-agents p a b      # Named homes only (p = ~/.claude; passing only `a b` omits ~/.claude)
just sync-agents all        # All agents
just sync-agents-preview …  # dry-run
```

## Task runner (only one justfile at root)

The justfile follows the justfile rules of `docs/agents/project-structure.md` (spoke), checked by `tests/unit/test_just_canonical.py` and `tests/unit/test_just_groups.py`. Every public recipe is in one of these groups, by purpose:
`gate` (whole gates: `check`, `ci`, `lint`, `fmt`, ...), `lint` (one checker each), `test`, `setup` (install, deploy, dump, update, clean), `doctor` (host diagnosis and the `check-*` probes), `agents`, `runner` (disk GC and the Windows runner service), `emulator`, `telemetry`, `tailnet`, `cloud`, `dns`, `site`, `debug`, `meta` (`help`).

| recipe | Description |
|---|---|
| `just` / `just help` | List recipes |
| `just ci` | Fast container-free gate: ruff / shellcheck / markdownlint / meta-semgrep + `lint-claude` + unit tests (`tests/unit/`) + `semgrep --test` + `tofu test` + `instruction-budget` + `skills-lock-check` + `emu-lint` (emulator `ruff format --check` + ruff canonical + ty + markdownlint; the semgrep leg currently has 0 targets due to `.semgrepignore`) + `check-forbidden-tokens-branch`. `check` itself also includes legs for Go, JS/TS (`js-lint` = oxlint, `js-typecheck` = `bun check --no-script`, `vp fmt --check`), Pi extensions, and Quint. The JS/TS legs run after installing root `package.json` dev dependencies with `bun install --frozen-lockfile --ignore-scripts` (ADR-0079) |
| `just lint-claude` | Official `claude plugin validate --strict` (skipped when the claude CLI is absent) + stdlib effective-settings validation (ADR 0037/0041). Third-party claudelint is **retired** (ADR 0041, trust decision). In CI, the `Claude Config Lint` workflow runs official validate via pinned `bunx @anthropic-ai/claude-code` (CI does not run `just ci`) |
| `just ci-all` | `ci` + `test` + `test-install` (including Podman sandbox) |
| `just check-all` | prek hooks + `ci-all` (manual final gate before push; not a git hook, ADR 0085) |
| `just test` | devcontainer sandbox tests (see below) |
| `just semgrep-test` | Run `semgrep --test` on `.semgrep/rules/**` with co-located fixtures |
| `just dump-skills-lock` / `restore-skills-lock` / `skills-place` / `skills-update` / `skills-lock-check` | Skill declaration (`dump/harness/skill-lock.json`) and placement (ADR 0043, `docs/agent-sync.md`). Tooling for audits, README tables, and fork comparisons lives in the `justfile` on the hironow/skills side. Steps are in `docs/agents/skills-maintenance.md` (spoke) |

## Python lint scope (repo-side exception)

- The Python toolchain is **uv + ruff + ty** per the global rules (ADR 0044). However, **ruff at the repo root (`scripts/` `tests/` `tools/`, etc.) uses the default rules (413 rules since ruff 0.16) + W605 + PTH (enforcing pathlib)**, and does not apply the canonical select from the spoke (measured 2026-09-08: canonical produces 851 findings even excluding ANN in tests; the effort is not worth it for test-heavy tooling).
- Always pass `encoding="utf-8"` when reading or writing text, and pass `encoding="utf-8", errors="replace"` when using `text=True` in subprocess (Japanese Windows defaults to cp932).
  `tests/unit/test_text_io_encoding.py` checks all first-party Python via AST.
  Keep `tests/unit/` passing completely on native Windows as well. `emulator/` applies the canonical rules (excluding ANN / PLR2004 / PLR0911 / PLR0915 in tests/**; see `emulator/pyproject.toml` for reasons). The canonical ruff version for gates comes from `[dependency-groups].lint` and uv.lock in root and emulator, while the mise pin is only for interactive local use (`just bump-tool` updates all 4 places including RTTM together). The justfile invokes ruff via `uv run --frozen --only-group lint ruff`.
- Running ty per OS follows the global rules (ADR 0069), split by stage. At the repo root, `check-ty` in `just check` runs ty for win32 / linux / darwin, while the explicit `just lint` runs it once. Neither runs as a git hook: prek keeps read-only guards and the fast `mise-versions-check` (ADRs 0083/0084/0085). `emulator/` and RTTM also run ty once (emulator runs in Linux containers). Patterns that fail only on Windows and the checks that catch them are documented in `docs/runbook/windows-host.md`.

## Test model (important)

- `just test` **builds a dedicated image on every run with Podman 5+ and @devcontainers/cli, and tests the actual up → exec flow in a disposable snapshot**.
  The snapshot contains only git-tracked working files and does not mount the live host repo or `.git`.
  Before startup, it explicitly sets the active engine socket and pins podman-compose.
  Because the socket grants engine control privileges, do not treat it as a security sandbox completely isolated from the host.
  Failures in required tools, connections, builds, or runtime fail the test.
- **In CI, the dev container tests (`test-just.yaml`) run on pushes to main, on demand, and on the ready pull requests that change anything outside its `paths-ignore` (ADR-0089).** Pull requests get `just check` from `check.yaml` as three parallel jobs (`just check-except-go`, `just go-lint`, `just go-test`; no container; tools from `.devcontainer/ci-bootstrap.sh --tools-only`) behind the gate `just check (no container)`, the unit suite as shards from `unit-test.yaml` (3 Linux, 6 Windows) whose gates prove that the shards ran every collected test once, and `just small-checks` (shellcheck, actionlint, `just semgrep-test`). Refresh `tests/durations/unit.json` and `unit-windows.json` from the `unit-durations` and `unit-windows-durations` artifacts of a main run. `just ci-audit` measures CI per job and per push; `just ci-shard-check` checks shard completeness.
- `tests/*.py` are sandbox and image tests (`test_just_sandbox.py` / `test_devcontainer.py`, etc., enumerated and run by `just test`). Put container-free static checks in `tests/unit/` (picked up by `test-unit` in `just ci`; files placed at root are not picked up by any gate). After adding or renaming a recipe, run **full `just test`**, not `just ci`. Keep sandbox assertions environment-independent (on the mount source side) (memory `feedback_just_test_ci_vs_local`).
- **semgrep**: Validate `.semgrep/rules/**` with `semgrep --test` (`just semgrep-test`, included in `ci`).
  `.semgrep` contains intentional-violation fixtures and is excluded from ruff in `pyproject.toml`.

## Local development stack (emulator / telemetry / portless)

ADR 0014 (emulator vendoring) / 0015 (portless) / 0016 (emulate) / 0072 (telemetry uses otel-lgtm).

- **emulator** (`emulator/compose.yaml`): `just emu-up` = **lite by default** (firebase +
  spanner + pgadapter + postgres = GCP core). Heavyweight/amd64 services are opt-in:
    - `just emu-up-only <service...>` — Start named services (bypasses the profile gate; used when an external repo borrows only `firebase-emulator`)
    - `just emu-up-group <cap>` — lite + capability (bigtable/search/graph/vector/ml/
      inspect/full)
    - `just emu-up-full` — All data services. `emu-start`/`emu-start-full` run clean+prebuild+up+wait
    - **Teardown enables all profiles**: `emu-stop`/`emu-clean` internally run
      `COMPOSE_PROFILES=full,cli PODMAN_COMPOSE_PROVIDER=podman-compose podman compose --in-pod=false down --remove-orphans`.
      Compose profiles also gate `down`, so running without profiles stops only lite and leaves profiled heavy services running.
- **telemetry** (`telemetry/compose.yaml`): A single upstream `grafana/otel-lgtm` container (ADR 0072; holds no custom config or dashboards). `just tel-up` (OTLP :4317/:4318, Grafana :3000) / `tel-down`.
  Shares `shared-otel-net` with emulator; the in-network destination is `lgtm:4317`.
- **portless**: There is no just recipe. Use `portless` directly, and register aliases from the `portless alias <name> <port> --force` list in `docs/portless-urls.md` to expose HTTP UIs at `https://<name>.localhost`.
  **HTTP(S) UIs only** — wire protocols such as Pub/Sub(9399) / Firestore(8080) / OTLP gRPC(4317) are unsupported and stay on `localhost:PORT`. Update that list if you change ports or the service order in `just emu-api`.
- **emu-api** (`just emu-api`): Runs vercel-labs/emulate via host bunx (4100-4108). `emu-api-stop`.
- The operator manages starting the Podman machine and service.
  Do not assume automatic recovery after host or VM boot based solely on `restart: unless-stopped`.
  Run isolated verification through the same manifest in `tests.utils.isolation`, and do not clean it up with shared-stack recipes.

## Repo-specific pitfalls (see memory)

- **`~/.config/mise/config.toml` is a symlink to the main tree** on some machines (including this operator's Mac). **Checking out another commit in the main tree replaces the live tool set and `[env]` across the entire machine.**
  Detaching to an older commit disables rtk and headroom machine-wide if they were not in that commit (they disappear from `mise ls --current`, `mise x -- rtk` falls back to an old binary in `~/.local/bin`, `shims/headroom` fails with "No version is set for shim", and telemetry env vars disappear) without warning.
  **Keep `/Users/nino/dotfiles` on main at all times, and do branch work only in worktrees.**
  `cp -f` in `scripts/deploy.sh` follows the symlink and **overwrites the file onto itself**, so `just deploy` does not fix it — fix it by checking main back out.
  `mise-config` in `just doctor` detects drift between the live config and `origin/main`.
- **The `skills/` glob in `.git/info/exclude`** silently drops new SKILL.md files under `plugins/*/skills/**` → `git add -f` is required (memory `project_dotfiles_skills_exclude`).
- **prek stash/rollback** can drop staged changes and **does not stash untracked files**. Hooks no longer rewrite files or run ty (ADR 0085), but the stash caveat remains → verify included files after commit with `git show --name-only`, and move new files meant for a separate commit out of the way while the hook runs (memory `feedback_prek_stash_partial_commit`).
- **statusline-command.sh causes `.git/index.lock` races** → when `Unable to create .git/index.lock` appears, confirm no active git write process is running and remove the stale lock (memory `feedback_statusline`).
- **commit.gpgsign=true** — All commits are GPG-signed. Re-sign with `git commit-tree -S` when rewriting history, and temporarily toggle the ruleset for force pushes (memory `feedback_git_history_rewrite_gpg`).
- **Node uses only bun. Agents cannot run npm/yarn/pnpm at all** (the guard blocks them at all times, including `corepack pnpm`/`pnpm@ver`/`corepack --cwd … pnpm`; **ADR 0027** partially supersedes the per-repo pnpm carve-out in ADR 0017). Machine provisioning of corepack itself remains as in **ADR 0017** (node-bundled shim + `PNPM_HOME` as store anchor only; `pnpm add -g` still aborts; global CLIs use mise npm: only). However, native Windows does not use pnpm and does not set up corepack (**ADR 0070**). `corepack enable`/`prepare`/`use` pass through.
- **The mise npm backend must be `bun` (ADR 0036), and the bun backend does not read `npm_args` (ADR 0040)**. With `auto` (aube), claude-code "succeeds" as a 500-byte stub.
- On **native Windows**, bare `bash` resolves to WSL in System32, so shebang recipes must run from Git Bash. Read `docs/runbook/windows-host.md` before touching justfile shell settings, `scripts/*.sh`, mise config, or Python that runs on Windows (covers shell selection, cygpath, `%APPDATA%\uv`, npm backend stubs, runner Machine PATH, and cp932).
- **Self-hosted runner disk GC (ADR 0035 / 0067)**: The WSL vhdx grows with container and build caches, and WSL itself fails to start once C: runs out of space. `just runner-gc-install` installs GC, and `just status` reports status and hook acceptance. Read `docs/runbook/runner-disk-gc.md` before touching `scripts/runner_gc*` or `just runner-gc*` / `disk-gc` / `wsl-compact`.
- Use only official Microsoft devcontainer features (no community features; memory `feedback_no_community_devcontainer_features`).

## docs / handover / intent

- `docs/handover.md` / `docs/intent.md` are **gitignored** (local only, untracked).
  Dated backups are ignored via the `docs/handover-*.md` / `docs/intent-*.md` globs.
- `docs/adr/` holds ADRs (immutable once Accepted). Other files under `docs/` describe only the current state (history lives in ADRs / git).

## Git / PR

- default branch = `main`. feature / fix / chore / docs go through branch → PR → **squash merge** to `main`.
- **CI does not run on draft PRs** (all workflow jobs have `if: … pull_request.draft == false` and trigger on `ready_for_review`). Use `gh pr create --draft` while working, and `gh pr ready` when ready to validate.
  `ci.yaml` in hironow/skills works the same way.
- Conventional Commits (type encodes structural/behavioral). See `ROOT_AGENTS.md` for details.
- YAML files use `.yaml` (not `.yml`); Compose files are named `compose.yaml`.
