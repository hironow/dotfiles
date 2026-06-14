# Project conventions for hironow/dotfiles (repo-side)

このファイルは **dotfiles リポジトリ自体を開発するとき** の運用ルールを記録する。
全エージェント共通の global 規約 (TDD / tooling / commit discipline / observability
等) は本リポの **hub-and-spoke な agent 指示 source 群** が正本で、`just sync-agents`
で各エージェント設定ディレクトリへ配布される (= デプロイ後に `~/.claude/CLAUDE.md`
等として読まれるもの)。

## このリポの役割と「agent 指示の二層構造」(最重要)

本リポは **global なエージェント指示を配布する** のが主目的の一つ。指示は monolith
から **hub-and-spoke** に移行済み (短い常時 load + on-demand spoke + 機械 enforcement)。

- **source 群 (repo root, `ROOT_*` sentinel 名なので agent は直接読まない):**
    - `ROOT_AGENTS.md` = cross-tool **base** (短い常時 load)
    - `ROOT_CLAUDE.md` = Claude 専用 **overlay** (先頭で `@AGENTS.md` を import)
    - `ROOT_AGENTS_docs_agents_*.md` = on-demand **spoke** (tdd / commit / python 等)
    - `ROOT_AGENTS_hooks_*.sh` + `.claude/settings.hooks.json` = Claude hooks (機械 enforcement)
    - `.claude/settings.shared.json` = Claude **共有 settings fragment** (env block + 選別
      top-level キー。`settings.hooks.json` 同様 CC からは読まれない純粋な source)
- **`just sync-agents` (`scripts/sync_agents.py`) の配布 (per-tool):**
    - base → codex `~/.codex/AGENTS.md` / gemini `~/.gemini/GEMINI.md` /
      claude-family `~/.claude*/AGENTS.md`
        - **`~/.gemini/GEMINI.md` は Gemini CLI (2026-06-18 sunset) と Antigravity
          CLI (`agy`) が共有する** global rules (issue google-gemini/gemini-cli#16058)。
          base sync 先は変更不要で、既存の gemini ターゲットがそのまま Antigravity を兼ねる。
    - overlay → claude-family `~/.claude*/CLAUDE.md` (`@AGENTS.md` で base を import)
    - spoke → `<agent>/docs/agents/*` (base 内の `docs/agents/` 参照は配布時に
      **その agent home の絶対パスへ rewrite**。相対だと作業 project 側に解決して外すため)
    - hooks + settings → **claude-family のみ**。settings.json は user キーを壊さず
      **update-in-place マージ** (manifest 非追跡)。sync が所有するのは command が
      `<agent>/hooks/` を指す block のみで、毎回その managed block を最新 fragment で
      置換 (hook command 変更でも stale 重複が残らない)、user 作成 block は保持
        - `.claude/settings.shared.json` も同一 settings.json へ **逐次** update-in-place
          マージ (hooks merge の直後)。**env block は sync が丸ごと所有=置換** (fragment から
          消えた env キーは target からも除去される。machine 固有 env は `settings.local.json`
          へ逃がす)、`settings` 内の top-level キーは **upsert** (theme/language/plugins 等の
          未宣言キーは保持)。top-level キーの削除は自動伝播しない。これにより env は **fragment
          一本が正本** で、repo `.claude/settings.json` は env を持たず global から継承する
    - `ROOT_AGENTS_<x>_<y>(.ext|/)` → `<agent>/<x>/<y>` (`_`→`/`) の従来規約も継続
    - **`skills` は additive** (`ADDITIVE_DIRECTORIES`): 欠落 skill のみ追加、既存
      target は**上書きしない・削除しない**。`bunx skills` CLI が `~/.agents/skills`
      へ install した symlink (上流 + `bunx skills add <skills-repo>`) を churn/orphan
      削除しないため。skill の投入は CLI (`bunx skills add`) を優先する
    - **Antigravity CLI (`agy`) は自己管理 — dotfiles は skills/settings/mcp を sync
      しない**: Antigravity は skills を `agy plugin` (=
      `~/.gemini/antigravity-cli/plugins/<name>/skills/`)、settings/mcp を `agy import`
      (= `~/.gemini/antigravity-cli/settings.json` + `mcp/`) で持つ。これらを raw sync
      すると agy の自己管理を迂回/clobber する (= `bunx skills` へ委譲するのと同理由)
      ため dotfiles は触らない。instruction 層 (`~/.gemini/GEMINI.md`) のみ共有で兼用。
      既存の `~/.gemini/skills/` additive は Antigravity が plugins/ から読むため
      vestigial だが additive で無害・残置 (詳細 ADR 0026)。
- **global ルールを変えるときは上記 source を編集して `just sync-agents`。**
  配布先 (`~/.claude/CLAUDE.md` 等) を直接編集しても次の sync で上書きされる。
- **per-repo enforcement は `templates/agent-baseline/` に scaffold 保管** (dotfiles
  自身には未適用。`just scaffold-agent-baseline <dir>` で新規 repo へ展開)。
- **本ファイル (`CLAUDE.md`, repo root) は別物** = dotfiles repo の開発時ルール。
  sync の対象外 (sync は home の agent dir のみ書き、repo root は触らない)。repo で
  作業するアシスタントは「global (`~/.claude/CLAUDE.md` = overlay+base) + 本ファイル」
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
| `just ci` | fast non-Docker gate: ruff / shellcheck / markdownlint / meta-semgrep + unit tests (`tests/unit/`) + `semgrep --test` + `tofu test` + `portless-doc-check` + `instruction-budget` |
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
- **Node は bun 一本。agent は npm/yarn/pnpm を一切叩けない** (guard が常時 block、
  `corepack pnpm`/`pnpm@ver`/`corepack --cwd … pnpm` 含む。**ADR 0027** が ADR 0017 の
  per-repo pnpm carve-out を partial supersede)。corepack のマシン供給自体は **ADR 0017**
  のまま温存 (node 同梱シム + `PNPM_HOME` は store アンカーのみ、`pnpm add -g` は依然
  abort、global CLI は mise npm: のみ)。`corepack enable`/`prepare`/`use` は素通り。
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
