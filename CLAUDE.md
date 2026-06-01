# Project conventions for hironow/dotfiles (repo-side)

このファイルは **dotfiles リポジトリ自体を開発するとき** の運用ルールを記録する。
全エージェント共通の global 規約 (TDD / tooling / commit discipline / observability
等) は本リポの **`ROOT_AGENTS.md`** が正本で、`just sync-agents` で各エージェント設定
ディレクトリへ配布される (= デプロイ後に `~/.claude/CLAUDE.md` として読まれるもの)。

## このリポの役割と「agent 指示の二層構造」(最重要)

本リポは **global なエージェント指示を配布する** のが主目的の一つ。

- **`ROOT_AGENTS.md` (repo root) が唯一の source。** `just sync-agents` が各 agent の
  main_file へ配る:
    - claude / claude-work-a..d → `~/.claude*/CLAUDE.md`
    - gemini → `~/.gemini/GEMINI.md`
    - codex → `~/.codex/AGENTS.md`
    - `ROOT_AGENTS_<x>_<y>(.ext|/)` → `<agent>/<x>/<y>` (commands / skills / hooks /
      agents)。ファイル名中の `_` (ROOT_AGENTS_ の後) が `/` に変換される。
- **global ルールを変えるときは `ROOT_AGENTS.md` を編集して `just sync-agents`。**
  配布先 (`~/.claude/CLAUDE.md` 等) を直接編集しても次の sync で上書きされる。
- **本ファイル (`CLAUDE.md`, repo root) は別物** = dotfiles repo の開発時ルール。
  sync の対象外 (sync は home の agent dir のみ書き、repo root は触らない)。repo で
  作業するアシスタントは「global (`~/.claude/CLAUDE.md` = ROOT_AGENTS) + 本ファイル」
  の両方を読む。

```bash
just sync-agents            # ~/.claude のみ (default)
just sync-agents a b        # + ~/.claude-work-a, -b
just sync-agents all        # 全 agent
just sync-agents-preview …  # dry-run
```

## タスクランナー (justfile は root に 1 つだけ)

| recipe | 内容 |
|---|---|
| `just` / `just help` | recipe 一覧 |
| `just ci` | fast non-Docker gate: ruff / shellcheck / markdownlint / meta-semgrep + `semgrep --test` + `tofu test` + `portless-doc-check` |
| `just ci-all` | `ci` + `test` + `test-install` (Docker サンドボックス込み) |
| `just check-all` | prek hooks + `ci-all` (push 前の最終 gate) |
| `just test` | devcontainer サンドボックステスト (下記) |
| `just semgrep-test` | `.semgrep/rules/**` を co-located fixture で `semgrep --test` |

## テストモデル (重要)

- `just test` は **@devcontainers/cli で sandbox image をビルドし pytest を image 内
  で実行**する。サンドボックスは **git-tracked ファイルだけ** を throwaway tempdir に
  snapshot し、host repo / `.git` を **マウントしない** (host 汚染が構造的に不可能)。
  Docker + devcontainer CLI が必要。
- `tests/*.py` は sandbox / 静的検査 (`test_just_sandbox.py` / `test_justfile_env_checks.py`
  等)。recipe 追加・改名後は `just ci` でなく **full `just test`** を回す。sandbox assert は
  環境非依存 (mount source 側) に保つ (memory `feedback_just_test_ci_vs_local`)。
- **semgrep**: `.semgrep/rules/**` を `semgrep --test` で検証 (`just semgrep-test`, `ci` 組込み)。
  `.semgrep` は intentional-violation fixture を含むため `pyproject.toml` で ruff 除外。

## ローカル開発スタック (emulator / telemetry / portless — vendored)

ADR 0014 (vendoring) / 0015 (portless) / 0016 (emulate)。

- **emulator** (`emulator/compose.yaml`): `just emu-up` = **lite 既定** (firebase +
  spanner + pgadapter + postgres = GCP コア)。重量級/amd64 サービスは opt-in:
    - `just emu-up-only <service...>` — 名指し起動 (profile gate を bypass。外部 repo が
      `firebase-emulator` だけ間借りする時に使う)
    - `just emu-up-group <cap>` — lite + capability (bigtable/search/graph/vector/ml/
      inspect/exporters/full)
    - `just emu-up-full` — 全データサービス。`emu-start`/`emu-start-full` は clean+prebuild+up+wait
    - **teardown は profile を全有効化**: `emu-stop`/`emu-clean` は内部で
      `COMPOSE_PROFILES=full,cli docker compose down --remove-orphans`。compose profiles は
      `down` も profile-gate するため、無指定だと lite しか落とせず profiled heavy が残る。
- **telemetry** (`telemetry/compose.yaml`): `just tel-up` (otel-collector :4317 →
  Tempo/Grafana) / `tel-down`。`shared-otel-net` を emulator と共有。
- **portless** (`config/portless-aliases.yaml`): `just portless-up` で HTTP UI を
  `https://<name>.localhost` に。**HTTP(S) UI のみ** — Pub/Sub(9399) / Firestore(8080) /
  OTLP gRPC(4317) 等の wire protocol は不可で `localhost:PORT` のまま。`just portless-doc`
  が `docs/portless-urls.md` を生成 (`portless-doc-check` が drift を ci で防ぐ)。
- **emu-api** (`just emu-api`): vercel-labs/emulate を host npx で (4100-4108)。`emu-api-stop`。
- OrbStack VM は **16 GiB / 4 vCPU** 推奨 (`orb config set memory_mib 16384` / `cpu 4`、
  要再起動)。10 GiB だとフルスタック + 外部 repo の二重起動で guest OOM。
  `restart: unless-stopped` のコンテナは VM 起動時に自動復活する (telemetry は復活しない)。

## このリポ特有の罠 (memory 参照)

- **`.git/info/exclude` の `skills/` glob** が `plugins/*/skills/**` の新規 SKILL.md を
  silent drop する → `git add -f` 必須 (memory `project_dotfiles_skills_exclude`)。
- **prek の stash/rollback** で staged ファイルを取りこぼすことがある → commit 後に
  `git show --name-only` で収録を検証 (memory `feedback_prek_stash_partial_commit`)。
- **statusline-command.sh が `.git/index.lock` レース** を起こす → `Unable to create
  .git/index.lock` が出たら active な git 書込みプロセス不在を確認して stale lock を
  除去 (memory `feedback_statusline`)。
- **commit.gpgsign=true** — 全 commit が GPG 署名される。履歴書き換え時は
  `git commit-tree -S` で再署名、force push は ruleset 一時トグル
  (memory `feedback_git_history_rewrite_gpg`)。
- **mise の npm backend は `--ignore-scripts=true`** — postinstall 必須の npm ツール
  (claude-code native binary 等) は `npm_args` で上書き (memory `project_mise_npm_ignore_scripts`)。
- **pnpm は corepack 供給の per-repo 専用、global CLI は mise npm: のみ** (ADR 0017)。
  `pnpm add -g` 禁止 (`$PNPM_HOME/bin` を PATH に載せないので自然に abort する)。
  `dump/npm-global` / `add-pnpm-g` / `update-pnpm-g*` / `check-pnpm-g` は退役済み。
- devcontainer features は Microsoft 公式のみ (community 不可、memory
  `feedback_no_community_devcontainer_features`)。

## docs / handover / intent

- `docs/handover.md` / `docs/intent.md` は **gitignored** (ローカルのみ、追跡しない)。
  dated backup は `docs/handover-*.md` / `docs/intent-*.md` glob で ignore。
- `docs/adr/` は ADR (Accepted 後 immutable)。`docs/` の他は現状のみ記述 (履歴は ADR / git)。

## Git / PR

- default branch = `main`。feature / fix / chore / docs は branch → PR → **squash merge** to `main`。
- Conventional Commits (type が structural/behavioral を encode)。詳細は `ROOT_AGENTS.md`。
- YAML は `.yaml` (not `.yml`)、Docker Compose は `compose.yaml`。
