# Architecture Decision Records (ADR)

This directory captures the **why** behind significant architecture
and tooling decisions across the dotfiles repository (the host
environment, the dev container image, CI, the tailnet policy). Live
documentation under `docs/` describes the **what** of the current
implementation; this index points to the recorded decisions that
shaped it. The records of the retired control plane stay here too —
[0045](./0045-coder-control-plane-retired.md) says what was destroyed
and what outlived it.

## Conventions

- File naming: `NNNN-short-title.md` (sequential, lowercase, hyphens)
- Status workflow: `Proposed` → `Accepted` → (`Deprecated` |
  `Superseded by [NNNN]`). A `Proposed` record that is never decided
  and whose subject goes away becomes `Withdrawn`.
- Once `Accepted`, ADRs are **immutable**. To revisit a decision,
  write a new ADR that supersedes the old one and update the old
  ADR's status line — that is the only allowed modification.
- Template lives in
  [`ROOT_AGENTS_docs_agents_docs-discipline.md`](../../ROOT_AGENTS_docs_agents_docs-discipline.md)
  (the source of the spoke agents read as `docs/agents/docs-discipline.md`).

## Index

| #    | Title                                                                                       | Status                                       | Date       | Affects                          |
| ---- | ------------------------------------------------------------------------------------------- | -------------------------------------------- | ---------- | -------------------------------- |
| 0001 | [Migrate dev container to debian-12 + features (single SoT)](./0001-devcontainer-debian-features.md) | Accepted                                     | 2026-05-02 | `.devcontainer/`                 |
| 0002 | [Coder workspace template uses a prebuilt dev container image](./0002-coder-prebuilt-image.md) | Accepted; superseded by [0045](./0045-coder-control-plane-retired.md) | 2026-05-02 | removed: `exe/coder/templates/` |
| 0003 | [Pin GitHub Actions to commit SHAs and add Dependabot updates](./0003-actions-pin-sha.md)            | Accepted (PR #48)                            | 2026-05-02 | `.github/workflows/`             |
| 0004 | [Workspace VMs reach the Coder control plane over the tailnet (B-plan)](./0004-workspace-tailnet-routing.md) | Accepted (PR #47); superseded by [0045](./0045-coder-control-plane-retired.md) | 2026-05-02 | removed: `exe/coder/templates/`, `exe/tailscale/acl.hujson` (the ACL now lives in `tofu/tailnet/`) |
| 0005 | [Rationalise install paths across Mac host and Coder workspace (Linux)](./0005-install-path-rationalization.md) | Accepted (the Linux consumer is now the dev container) | 2026-05-02 | `install.sh`, `dump/<host>/Brewfile` |
| 0006 | [mise tool version pinning strategy](./0006-mise-version-pinning.md) | Accepted; partly superseded by [0060](./0060-frozen-image-generation-has-one-source.md) | 2026-05-02 | `config/mise/config.toml` |
| 0007 | [Coder server install hardening on the control-plane VM](./0007-coder-server-install-hardening.md) | Accepted; superseded by [0045](./0045-coder-control-plane-retired.md) | 2026-05-02 | removed: `tofu/exe/coder.tf`, `tofu/exe/variables.tf` |
| 0008 | [Event-driven Coder workspace runner (GHA-style without GHA)](./0008-event-driven-workspace-runner.md) | Superseded by [0009](./0009-retract-cron-trigger-from-adr-0008.md) (partial — trigger source 2 retracted), then in full by [0045](./0045-coder-control-plane-retired.md) | 2026-05-03 | removed: `exe/coder/templates/dotfiles-job/`, `exe/scripts/` |
| 0009 | [Retract the systemd-timer cron trigger from ADR 0008](./0009-retract-cron-trigger-from-adr-0008.md) | Accepted (2026-05-04 — cron infra reverted in PR #76, never returned); superseded by [0045](./0045-coder-control-plane-retired.md) | 2026-05-03 | retracted a cron / systemd timer that was never added; the stack it would have run on is removed |
| 0010 | [Cloud SQL Postgres for Coder data plane](./0010-cloud-sql-postgres-for-coder.md) | Accepted; superseded by [0045](./0045-coder-control-plane-retired.md) | 2026-05-03 | removed: `tofu/exe/cloudsql.tf`, `tofu/exe/coder.tf`, `tofu/exe/monitoring.tf` |
| 0011 | [exe-coder workspace VM multi-project systemd env delivery](./0011-exe-multi-project-systemd-env.md) | Accepted; superseded by [0045](./0045-coder-control-plane-retired.md) | 2026-05-07 | removed: `exe/coder/templates/`, `exe/scripts/` |
| 0012 | [exe-coder workspace VM RUNOPS_ACTOR_TYPE env injection (per caller path)](./0012-exe-actor-type-env-injection.md) | Accepted; superseded by [0045](./0045-coder-control-plane-retired.md) | 2026-05-09 | removed: `exe/coder/templates/`, `exe/scripts/` |
| 0013 | [Project lifecycle severity classification (= cdr-project / runops project)](./0013-project-lifecycle-severity-classification.md) | Withdrawn — never decided; see [0045](./0045-coder-control-plane-retired.md) | 2026-05-09 | would have affected the removed `exe/` project lifecycle |
| 0014 | [Vendor emulator and telemetry from submodules into dotfiles](./0014-vendor-emulator-telemetry-from-submodules.md) | Accepted | 2026-05-30 | `emulator/`, `telemetry/` |
| 0015 | [Adopt portless for stable .localhost URLs of local HTTP UIs](./0015-adopt-portless-for-local-dev-urls.md) | Accepted; partly superseded by [0054](./0054-run-portless-directly.md) | 2026-05-30 | `config/portless-aliases.yaml`, `docs/portless-urls.md` |
| 0016 | [Integrate vercel-labs/emulate API emulators via npx wrapper](./0016-integrate-emulate-api-emulators-via-npx.md) | Partly superseded by [0055](./0055-run-emulate-with-bunx.md) | 2026-05-30 | `emulator/emulate/`, `justfile` (`emu-api`) |
| 0017 | [Retire the pnpm-global subsystem in favor of corepack + mise npm](./0017-retire-pnpm-global-for-corepack.md) | Accepted; partial supersede by [0027](./0027-bun-only-retire-per-repo-pnpm-carveout.md) | 2026-06-02 | `mise.toml`, `install.sh`, `dump/npm-global` |
| 0018 | [Windows native: minimum-viable deploy with explicit-skip step_*](./0018-windows-native-mvp.md) | Accepted; partial supersede by [0039](./0039-windows-bootstrap-ps1.md) (bootstrap scope) | 2026-06-02 | `install.sh`, `justfile` (Windows deploy) |
| 0019 | [Windows scoop manifest in `dump/` — record-only](./0019-windows-scoop-dump-record-only.md) | Accepted; partial supersede by [0030](./0030-per-host-dump-layout.md) (path) + [0032](./0032-windows-scoop-restore-add-scoop.md) (record-only) | 2026-06-02 | `dump/<host>/scoop.json`, `justfile` |
| 0020 | [Normalize shell-script line endings via `.gitattributes`](./0020-normalize-shell-script-line-endings.md) | Accepted | 2026-06-02 | `.gitattributes` |
| 0021 | [Split git config via `[include]` so dotfiles owns aliases + shared settings](./0021-git-config-include-split.md) | Accepted | 2026-06-02 | `~/.gitconfig`, `config/git/` |
| 0022 | [PowerShell `$PROFILE` starship init from `just deploy` (Windows native)](./0022-powershell-starship-profile-init.md) | Accepted | 2026-06-02 | PowerShell `$PROFILE` |
| 0023 | [Use `mise activate` only in interactive shells, drop manual `shims` PATH entries](./0023-mise-activate-only-no-shims-path.md) | Accepted | 2026-06-02 | `.zshrc`, `mise.toml` |
| 0024 | [PowerShell `$PROFILE` mise activate from `just deploy` (Windows native)](./0024-powershell-mise-activate-profile.md) | Accepted | 2026-06-02 | PowerShell `$PROFILE`, `mise.toml` |
| 0025 | [Wrap mise-managed tools at every justfile call site (補強 of ADR 0023)](./0025-justfile-mise-tool-wrap.md) | Accepted | 2026-06-02 | `justfile` |
| 0026 | [Antigravity CLI: instruction 層のみ共有、skills/settings/mcp は agy 委譲](./0026-antigravity-cli-instruction-layer.md) | Accepted | 2026-06-10 | `~/.gemini/GEMINI.md`, `scripts/sync_agents.py` |
| 0027 | [Bun-only Node policy: retire the per-repo pnpm carve-out](./0027-bun-only-retire-per-repo-pnpm-carveout.md) | Accepted; partial supersede by [0037](./0037-layered-claude-settings-fragments.md) (permissions distribution) | 2026-06-14 | `.claude/` hooks, `ROOT_AGENTS*` |
| 0028 | [Standardize on the Flatt Security PyPI mirror as the default uv index](./0028-flatt-pypi-mirror-default-index.md) | Superseded by [0053](./0053-stop-using-flatt-mirrors.md) | 2026-06-19 | `*/pyproject.toml`, `*/uv.lock` |
| 0029 | [Gate the distributed Claude config with claudelint + official plugin validate](./0029-claude-config-lint-gate.md) | Accepted; partial supersede by [0041](./0041-retire-third-party-claudelint.md) (claudelint retired) | 2026-06-22 | `justfile`, `.github/workflows/claude-lint.yaml` |
| 0030 | [Per-host dump layout (`dump/<host>/`)](./0030-per-host-dump-layout.md) | Accepted | 2026-07-01 | `justfile`, `scripts/dump_host.sh`, `dump/<host>/`, `install.sh` |
| 0031 | [Disable mise `node.corepack` on Windows (`just deploy` `$PROFILE` carve-out)](./0031-disable-mise-corepack-on-windows.md) | Accepted | 2026-07-05 | `justfile` (deploy/clean), `config/mise/config.toml` |
| 0032 | [Windows scoop restore: add `add-scoop` (supersede ADR 0019 record-only)](./0032-windows-scoop-restore-add-scoop.md) | Accepted; supersedes [0019](./0019-windows-scoop-dump-record-only.md) (record-only stance) | 2026-07-05 | `justfile` (`add-scoop`), `dump/<host>/scoop.json` |
| 0033 | [Windows `just deploy` installs the global mise toolset (+ git aliases)](./0033-windows-deploy-global-mise-install.md) | Accepted | 2026-07-05 | `justfile` (deploy/clean), `~/.gitconfig` |
| 0034 | [exe stack mothball mode (`stack_mode`) + AR retention bound](./0034-exe-stack-mothball-mode.md) | Accepted; superseded by [0045](./0045-coder-control-plane-retired.md) | 2026-07-20 | removed: `tofu/exe/`, `exe/docs/` |
| 0035 | [Time-based disk GC for the self-hosted runners (2h retention)](./0035-runner-disk-gc.md) | Accepted | 2026-07-31 | `scripts/runner_gc*.{sh,ps1}`, `scripts/disk_gc.sh`, `scripts/gc_status.sh`, `justfile` (Disk) |
| 0036 | [Install mise `npm:` tools with bun, not the embedded aube](./0036-mise-npm-backend-bun.md) | Accepted; amended by [0040](./0040-npm-args-inert-under-bun.md) (npm_args rationale) | 2026-07-31 | `config/mise/config.toml` |
| 0037 | [Layered Claude settings fragments (shared / OS / profile / machine-local)](./0037-layered-claude-settings-fragments.md) | Accepted | 2026-08-05 | `scripts/sync_agents.py`, `.claude/settings.shared*.json`, `.claude/settings.profiles/` |
| 0038 | [Declarative third-party skills (skill-lock dump, no re-vendoring)](./0038-declarative-third-party-skills.md) | Accepted | 2026-08-14 | `dump/harness/skill-lock.json`, `scripts/skills_lock.py`, `justfile` |
| 0039 | [Windows native bootstrap via `bootstrap.ps1` one-liner](./0039-windows-bootstrap-ps1.md) | Accepted | 2026-08-15 | `bootstrap.ps1`, `tests/unit/test_bootstrap_ps1.py`, `README.md` |
| 0040 | [`npm_args` is inert under the bun backend — drop it, correct ADR 0036's rationale](./0040-npm-args-inert-under-bun.md) | Accepted | 2026-08-15 | `config/mise/config.toml`, `.devcontainer/features/dotfiles-tools/install.sh` |
| 0041 | [Retire the third-party claudelint; official-validator-only gate](./0041-retire-third-party-claudelint.md) | Accepted | 2026-08-16 | `justfile`, `.github/workflows/claude-lint.yaml`, `scripts/check_effective_settings.py` |
| 0042 | [Watchdog for the interactive Windows runner](./0042-interactive-runner-watchdog.md) | Accepted | 2026-09-03 | `scripts/runner_watchdog_win.ps1`, `justfile` (runner recipes) |
| 0043 | [Self-authored skills go through the skills CLI; the `skills/` submodule is retired](./0043-self-authored-skills-through-the-skills-cli.md) | Accepted; supersedes decisions 2–4 of [0038](./0038-declarative-third-party-skills.md) | 2026-09-06 | `dump/harness/skill-lock.json`, `justfile` (skills recipes), `scripts/sync_agents.py` |
| 0044 | [The Python toolchain is uv + ruff + ty; mypy and pyright are retired](./0044-python-toolchain-uv-ruff-ty.md) | Accepted | 2026-09-08 | `config/mise/config.toml`, `ROOT_AGENTS.md`, `ROOT_AGENTS_docs_agents_python-tooling.md`, `templates/agent-baseline/justfile` |
| 0045 | [The Coder control plane is retired, and what outlived it](./0045-coder-control-plane-retired.md) | Accepted | 2026-10-01 | `tofu/` (both stacks removed), `tofu/tailnet/`, `justfile`, `.github/workflows/` |
| 0047 | [rtk is mandatory base tooling and dotfiles owns its Claude hook](./0047-rtk-mandatory-base-tooling.md) | Accepted; its `permissionDecision` scope corrected by [0049](./0049-headroom-mandatory-base-tooling.md) (the decision stands) | 2026-09-29 | `ROOT_AGENTS_hooks_rtk-hook-claude.{sh,py}`, `.claude/settings.hooks.json`, `scripts/sync_agents.py`, `ROOT_AGENTS_hooks_block-prohibited-commands.py`, `ROOT_AGENTS_docs_agents_rtk.md` |
| 0048 | [Claude Code plugins dotfiles requires are declared and installed through the plugin CLI](./0048-required-claude-plugins.md) | Accepted | 2026-10-01 | `dump/harness/claude-plugins.json`, `scripts/claude_plugins.py`, `scripts/deploy.sh`, `justfile` |
| 0049 | [headroom is mandatory base tooling: MCP in every home, the j-cc proxy as its canary, telemetry off](./0049-headroom-mandatory-base-tooling.md) | Accepted | 2026-10-01 | `config/mise/config.toml`, `scripts/headroom_mcp.py`, `scripts/jev_headroom.py`, `scripts/ai_tools_check.py`, `scripts/harden_env.sh`, `.claude/settings.shared.json`, `ROOT_AGENTS_docs_agents_headroom.md` |
| 0050 | [Pin Go sources to LF via `.gitattributes` (go-lint on Windows)](./0050-pin-go-sources-to-lf.md) | Accepted | 2026-10-02 | `.gitattributes`, `tests/unit/test_gitattributes_eol.py` |
| 0051 | [新しい決定記録をdecision queueで追跡する](./0051-adopt-decision-queue-for-new-records.md) | Accepted (PR #461) | 2026-10-06 | `docs/decision-queue.md`、今後のADR/PDR |
| 0052 | [全エージェント共通の指示を刷新する（Go優先、fake/、core/shell設計、Plain Language）](./0052-renew-global-agent-instructions.md) | Accepted (PR #463); limited distribution exception in [0061](./0061-version-generator-in-go.md) | 2026-10-09 | `ROOT_AGENTS.md`、`ROOT_CLAUDE.md`、`ROOT_AGENTS_docs_agents_*.md` |
| 0053 | [Flatt のパッケージミラーをやめ、公式の取得元に戻す](./0053-stop-using-flatt-mirrors.md) | Accepted (PR #463); supersedes [0028](./0028-flatt-pypi-mirror-default-index.md) | 2026-10-11 | `pyproject.toml` と各 `uv.lock`、`scripts/harden_env.sh`、`.zshrc`、`justfile` |
| 0054 | [portless を just の recipe で包まず、直接使う](./0054-run-portless-directly.md) | Accepted (PR #468); supersedes part of [0015](./0015-adopt-portless-for-local-dev-urls.md) | 2026-10-11 | `justfile`、`docs/portless-urls.md` |
| 0055 | [emulate は npx ではなく bunx で動かす](./0055-run-emulate-with-bunx.md) | Accepted (PR #470); supersedes part of [0016](./0016-integrate-emulate-api-emulators-via-npx.md) | 2026-10-12 | `justfile`、`tests/unit/test_justfile_bun_only.py` |
| 0056 | [5 つの Claude home で使っている plugin の和集合を、全 home 共通の宣言にする](./0056-common-claude-plugin-set.md) | Accepted (PR #475); supersedes part of [0048](./0048-required-claude-plugins.md); partly superseded by [0057](./0057-shared-plugins-need-no-per-home-settings.md) | 2026-10-16 | `dump/harness/claude-plugins.json`、`scripts/claude_plugins.py`、`tests/unit/test_claude_plugins.py` |
| 0057 | [共通セットの plugin は、home ごとの設定なしで動くものに限る](./0057-shared-plugins-need-no-per-home-settings.md) | Accepted (PR #476); supersedes part of [0056](./0056-common-claude-plugin-set.md) | 2026-10-16 | `dump/harness/claude-plugins.json`、`scripts/claude_plugins.py`、`tests/unit/test_claude_plugins.py` |
| 0058 | [Pi の web 検索を Ollama 経由に寄せ、pi 本体の計測を全機体で止める](./0058-pi-web-search-ollama.md) | Accepted; partly superseded by [0062](./0062-one-windows-ollama-for-wsl.md) | 2026-10-19 | `dump/harness/pi-packages.json`、`scripts/install_pi_extensions.py`、`tests/unit/test_install_pi_extensions.py` |
| 0059 | [remote-pi を外し、host 提供パッケージを vendor させない](./0059-retire-remote-pi.md) | Accepted | 2026-10-19 | `dump/harness/pi-packages.json`、`scripts/install_pi_extensions.py`、`tests/unit/test_install_pi_extensions.py` |
| 0060 | [画像の凍結世代を 1 か所に持ち、install.sh の版本領域を生成する](./0060-frozen-image-generation-has-one-source.md) | Accepted; partly superseded by [0061](./0061-version-generator-in-go.md) | 2026-10-21 | `config/mise/image-tools.toml`、`scripts/mise_versions.py`、`install.sh`、`.devcontainer/features/dotfiles-tools/install.sh`、`justfile`、`tests/unit/test_mise_versions.py` |
| 0061 | [版本の生成器を Go にする（stdlib のみ、TOML サブセット + Python oracle）](./0061-version-generator-in-go.md) | Accepted (PR #486); partly supersedes [0060](./0060-frozen-image-generation-has-one-source.md) and adds a limited exception to [0052](./0052-renew-global-agent-instructions.md) | 2026-10-21 | `tools/mise-versions/`、`justfile`、`tests/unit/test_mise_versions.py` |
| 0062 | [共存機の Ollama は Windows の Scoop ollama-full に 1 台だけ置き、WSL はクライアントにする](./0062-one-windows-ollama-for-wsl.md) | Accepted; partly supersedes [0058](./0058-pi-web-search-ollama.md) | 2026-10-25 | `scripts/ollama_host.py`、`scripts/install_pi_extensions.py`、`docs/runbook/ollama-windows-wsl.md` |
| 0063 | [宣言した機体だけ、tailnet の中だけの Tailscale 転送を Ollama の公開と数えない](./0063-declared-tailnet-forward-of-ollama.md) | Accepted | 2026-10-25 | `scripts/ollama_host.py`、`tests/unit/test_ollama_host.py`、`.github/workflows/unit-test.yaml`、`docs/runbook/ollama-windows-wsl.md` |
| 0064 | [mirrored の WSL にはブリッジを置かず、共有の loopback で Windows の Ollama を使う](./0064-mirrored-wsl-uses-the-shared-loopback.md) | Accepted | 2026-10-25 | `scripts/ollama_host.py`、`tests/unit/test_ollama_host.py`、`docs/runbook/ollama-windows-wsl.md` |
| 0065 | [Linux カーネルの CVE は dotfiles が直さず、報告と助言だけを行う](./0065-kernel-cve-is-evidence-only.md) | Proposed（決裁待ち） | 2026-10-29 | `tools/kernel-doctor/`、`justfile`、`scripts/doctor.sh`、`tests/unit/test_doctor_kernel.py`、`docs/runbook/kernel-doctor.md` |
| 0066 | [doctor の WARN は手を動かすべきことだけにし、注意書きは INFO で出し、OS に合わない行は出さない](./0066-doctor-warns-only-what-needs-action.md) | Proposed（決裁待ち） | 2026-11-01 | `scripts/doctor.sh`、`scripts/doctor_lines.py`、`scripts/ollama_host.py`、`tools/ca-doctor/`、`tools/kernel-doctor/`、`docs/runbook/ca-doctor.md`、`docs/runbook/kernel-doctor.md` |

## Reading order for newcomers

1. [`0001`](./0001-devcontainer-debian-features.md) — why debian-12
   with devcontainer features instead of an Alpine or Ubuntu base.
2. [`0005`](./0005-install-path-rationalization.md) — why `install.sh`
   is one entry point with a per-OS dispatch.
3. [`0006`](./0006-mise-version-pinning.md) — how tool versions are
   pinned so every consumer installs the same ones.
4. [`0044`](./0044-python-toolchain-uv-ruff-ty.md) — the Python
   toolchain (uv + ruff + ty) this repo and its scaffolds enforce.
5. [`0045`](./0045-coder-control-plane-retired.md) — what the retired
   control plane was, and the three classes of object that outlived
   its destruction. Read it before any ADR between 0002 and 0013.

## Related

- [`../../ROOT_AGENTS_docs_agents_docs-discipline.md`](../../ROOT_AGENTS_docs_agents_docs-discipline.md)
  — ADR template + when to write one
- [`../../tofu/tailnet/README.md`](../../tofu/tailnet/README.md) — the
  one IaC stack this repository still owns
- [`../agent-sync.md`](../agent-sync.md) — how the `ROOT_*` sources
  reach each agent's home

## 決定変更ログ (Decision Change Log)

- 2026-10-06: [ADR-0051](./0051-adopt-decision-queue-for-new-records.md)のA案を採択。
  今後の未決ADR/PDRを[decision queue](../decision-queue.md)で追う。
  [公開PR #461の裁定](https://github.com/hironow/dotfiles/pull/461#issuecomment-6020609790)。
  既存49件のAccepted本文は変更しない。
- 2026-10-11: [ADR-0052](./0052-renew-global-agent-instructions.md)を採択。全エージェント共通の指示を刷新した。
  [公開PR #463の裁定](https://github.com/hironow/dotfiles/pull/463#issuecomment-6104926585)。
- 2026-10-11: [ADR-0053](./0053-stop-using-flatt-mirrors.md)を採択し、[ADR-0028](./0028-flatt-pypi-mirror-default-index.md)を置き換えた。
  Flatt のミラーをやめ、pypi.org と npmjs から取る。[公開PR #463の裁定](https://github.com/hironow/dotfiles/pull/463#issuecomment-6104926585)。
- 2026-10-11: [ADR-0054](./0054-run-portless-directly.md)を採択し、[ADR-0015](./0015-adopt-portless-for-local-dev-urls.md)の一部を置き換えた。
  portless を just の recipe で包まず、直接使う。[公開PR #468の裁定](https://github.com/hironow/dotfiles/pull/468#issuecomment-6106249810)。
- 2026-10-12: [ADR-0055](./0055-run-emulate-with-bunx.md)を採択し、[ADR-0016](./0016-integrate-emulate-api-emulators-via-npx.md)の一部を置き換えた。
  emulate は npx ではなく bunx で動かす。[公開PR #470の所有者裁定](https://github.com/hironow/dotfiles/pull/470#issuecomment-6113089576)。
- 2026-10-16: [ADR-0056](./0056-common-claude-plugin-set.md)を採択し、[ADR-0048](./0048-required-claude-plugins.md)の一部を置き換えた。
  5 つの Claude home で使う plugin の和集合 40 個を全 home 共通にする。[公開PR #475の所有者裁定](https://github.com/hironow/dotfiles/pull/475#issuecomment-6209808795)。
- 2026-10-16: [ADR-0057](./0057-shared-plugins-need-no-per-home-settings.md)を採択し、[ADR-0056](./0056-common-claude-plugin-set.md)の一部を置き換えた。
  共通セットは home ごとの設定なしで動く plugin に限り、doctor で見張る。[公開PR #476の所有者裁定](https://github.com/hironow/dotfiles/pull/476#issuecomment-6211696383)。
- 2026-10-19: [ADR-0058](./0058-pi-web-search-ollama.md)を採択。
  Pi の web 検索は `npm:@ollama/pi-web-search` に一本化し、pi 本体の計測（install report と opt-in analytics）は全機体で止め、Ollama がなければ公式 download 手順で自動導入する。本セッションでの所有者の直接指示。
- 2026-10-19: [ADR-0059](./0059-retire-remote-pi.md)を採択。
  `npm:remote-pi` は host 提供パッケージを `dependencies` で宣言して古い実体を vendor するため retire し、他機体の settings からも `pi remove` で除く。本セッションでの所有者の選択（A）。
- 2026-10-21: [ADR-0060](./0060-frozen-image-generation-has-one-source.md)を採択（[ADR-0006](./0006-mise-version-pinning.md) の一部を置換）。
  画像の凍結世代（bake する mise 道具、検証つき tarball、bare Linux の bootstrap）を `config/mise/image-tools.toml` 1 か所に集め、`scripts/mise_versions.py` が `install.sh` の版本領域を生成し、`just lint` / `just check` が drift を落とす。本セッションでの所有者の裁定（[PR #485](https://github.com/hironow/dotfiles/pull/485)）。
- 2026-10-21: [ADR-0060](./0060-frozen-image-generation-has-one-source.md) の Python/writer 指定と [ADR-0052](./0052-renew-global-agent-instructions.md) の本生成器の配布要件 → [ADR-0061](./0061-version-generator-in-go.md)。
  Go＋自作 TOML サブセット＋Python oracle に変更し、repo 内の生成器だけ `go run` の限定例外とする。他の決定は維持。[PR #486 の所有者裁定](https://github.com/hironow/dotfiles/pull/486#issuecomment-6314535355)。
- 2026-10-25: [ADR-0062](./0062-one-windows-ollama-for-wsl.md)を採択し、[ADR-0058](./0058-pi-web-search-ollama.md) の Decision 4 と、Decision 3 の Windows・WSL での適用を置き換えた。
  共存機の Ollama は Windows の Scoop `extras/ollama-full` に 1 台だけ置き、WSL はクライアントにする（PR #502 の実装の記録）。DR 間整合検査で検出した矛盾を所有者が裁定した。
- 2026-10-25: [ADR-0063](./0063-declared-tailnet-forward-of-ollama.md)を採択。宣言した機体だけ、tailnet の中だけの Tailscale 転送を、厳しい条件で Ollama の公開と数えない。Funnel は認めない。
- 2026-10-25: [ADR-0064](./0064-mirrored-wsl-uses-the-shared-loopback.md)を採択。mirrored の WSL にはブリッジを置かず、共有の loopback で Windows の Ollama を使い、doctor が接続の前に持ち主を確かめる。
- 2026-10-29: [ADR-0065](./0065-kernel-cve-is-evidence-only.md)を起票（Proposed、決裁待ち）。CVE-2026-98432（Linux カーネル IPv4 TCP の use-after-free）を契機に、カーネルは dotfiles が直さないこと、版の比較はクリーンな上流形かつレビュー済み branch のときだけ行い未判定を修正済みと数えないこと、kernel-doctor の所見は doctor の `err` に入れないこと、WSL カーネルを管理しない方針（0058 / 0064）を維持することを定める。
- 2026-11-01: [ADR-0066](./0066-doctor-warns-only-what-needs-action.md)を起票（Proposed、決裁待ち）。`just doctor` の WARN を、その機体で手を動かすべきことだけにする。範囲の注意書きと事実は INFO で出して警告に数えず、`ca-doctor --summary` でクライアントごとの 1 行にまとめ、その OS に合わない検査の行は出さない。ERR と終了コードの契約は変えない。
