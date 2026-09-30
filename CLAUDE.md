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
    - `.claude/settings.shared.json`, `.claude/settings.shared.{macos,linux,windows}.json`,
      `.claude/settings.profiles/<key>.json` = Claude **層状 settings fragment**
      (shared → OS overlay → profile。env block + 選別 top-level キー。
      `settings.hooks.json` 同様 CC からは読まれない純粋な source。詳細 ADR 0037)
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
        - settings fragment は **4層を合成して1つの desired state** にしてから同一
          settings.json へ update-in-place マージ (hooks merge の直後)。層は後勝ちで
          ① `settings.shared.json` → ② `settings.shared.<os>.json` (実行 OS、欠落=空) →
          ③ `settings.profiles/<AgentTarget.key>.json` → ④ **`<agent home>/settings.sync-local.json`**
          (git 非追跡・machine 固有の最終上書き層)。**env は合成後に sync が丸ごと所有=置換**
          (fragment 群から消えた env キーは target からも除去。machine 固有 env は ④ へ —
          `settings.local.json` は **project scope 専用で user scope では読まれない**ため
          逃し先にならない)。`settings` 内は key-wise 後勝ち + **両辺 dict のみ1段 deep-merge**
          (shared の `permissions.deny` と profile の `permissions.defaultMode` が合成される)、
          target へは top-level **upsert** (enabledPlugins 等の未宣言キーは保持)。top-level
          キーの削除は自動伝播しない。env は **fragment 群が正本** で、repo
          `.claude/settings.json` は env を持たず global から継承する (詳細 ADR 0037)
    - `ROOT_AGENTS_<x>_<y>(.ext|/)` → `<agent>/<x>/<y>` (`_`→`/`) の従来規約も継続
    - **skills は sync しない (ADR 0043)**: 自作 (hironow/skills) もサードパーティも
      `bunx skills` CLI の store (`~/.agents/skills`) に入れ、git は正規化宣言
      `dump/harness/skill-lock.json` だけを追跡する。各 home の `skills/` には
      `just skills-place` が store への相対 symlink を張る (symlink 不可なら追跡付きコピー)。
      `just dump-skills-lock` (宣言更新、hironow/skills の record 消失を拒否) /
      `just restore-skills-lock` (新マシン: store 復元 → place) / `just skills-update`
      (hironow/skills merge 後: store 更新 → place)。CLI には `-a universal` で store だけを
      書かせ、home には CLI を触らせない。**同名衝突は hironow/skills が勝つ**
      (`just skills-lock-check`、`ci` 組込み)。旧 `skills/` submodule・`skills/learned`・
      additive sync・除外 toml は撤去済み
    - **Antigravity CLI (`agy`) は自己管理 — dotfiles は skills/settings/mcp を sync
      しない**: Antigravity は skills を `agy plugin` (=
      `~/.gemini/antigravity-cli/plugins/<name>/skills/`)、settings/mcp を `agy import`
      (= `~/.gemini/antigravity-cli/settings.json` + `mcp/`) で持つ。これらを raw sync
      すると agy の自己管理を迂回/clobber する (= `bunx skills` へ委譲するのと同理由)
      ため dotfiles は触らない。instruction 層 (`~/.gemini/GEMINI.md`) のみ共有で兼用。
      `~/.gemini/skills/` は `skills-place` の link 先だが Antigravity は plugins/ から読むため
      vestigial・無害 (詳細 ADR 0026)。
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
| `just ci` | fast non-Docker gate: ruff / shellcheck / markdownlint / meta-semgrep + `lint-claude` + unit tests (`tests/unit/`) + `semgrep --test` + `tofu test` + `portless-doc-check` + `instruction-budget` + `skills-lock-check` + `emu-lint` (emulator の `ruff format --check` + ruff canonical + ty + markdownlint。semgrep leg は `.semgrepignore` で現状 target 0) |
| `just lint-claude` | 公式 `claude plugin validate --strict` (claude CLI 不在時は skip) + stdlib の effective-settings 検証 (ADR 0037/0041)。サードパーティ claudelint は**退役済み** (ADR 0041、trust 判断)。CI gate は `Claude Config Lint` workflow が pinned `bunx @anthropic-ai/claude-code` で公式 validate を回す (CI は `just ci` 非実行) |
| `just ci-all` | `ci` + `test` + `test-install` (Docker サンドボックス込み) |
| `just check-all` | prek hooks + `ci-all` (push 前の最終 gate) |
| `just test` | devcontainer サンドボックステスト (下記) |
| `just semgrep-test` | `.semgrep/rules/**` を co-located fixture で `semgrep --test` |
| `just dump-skills-lock` / `restore-skills-lock` / `skills-place` / `skills-update` / `skills-lock-check` | skill の宣言 (`dump/harness/skill-lock.json`) と配置 (ADR 0043): 自作 (hironow/skills) もサードパーティも `bunx skills` CLI の store (`~/.agents/skills`) に入れ、各 home へは `skills-place` が相対 symlink を張る。監査・README 表・fork 比較の tooling は hironow/skills 側の `justfile`。手順は `docs/agents/skills-maintenance.md` (spoke) |

## Python lint の範囲 (repo-side の例外)

- Python toolchain は global 規約どおり **uv + ruff + ty** (ADR 0044)。ただし **repo root
  (`scripts/` `tests/` `tools/` など) の ruff は default rule + W605 + PTH (pathlib 強制)**で、
  spoke の canonical select は当てない
  (2026-09-08 計測: canonical は tests の ANN を除外しても 851 件。tests 中心の tooling に対して
  作業量が価値に見合わない)。
- テキストの読み書きは必ず `encoding="utf-8"`、subprocess の `text=True` には
  `encoding="utf-8", errors="replace"` を渡す (日本語版 Windows の既定は cp932)。
  `tests/unit/test_text_io_encoding.py` が自前の Python 全体を AST で検査する。
  `tests/unit/` は native Windows でも全部通る状態を保つ。`emulator/` は canonical を適用済み (tests/** は ANN / PLR2004 /
  PLR0911 / PLR0915 を除外、理由は `emulator/pyproject.toml`)。gate の ruff 版は root /
  emulator の `[dependency-groups].lint` と uv.lock が正で、mise の pin を `just bump-tool`
  で同時に動かす (`tests/unit/test_ruff_ty_pins.py` が不一致を検出)。justfile は
  `uv run --frozen --only-group lint ruff` で呼ぶ。

## テストモデル (重要)

- `just test` は **@devcontainers/cli で sandbox image をビルドし pytest を image 内
  で実行**する。サンドボックスは **git-tracked ファイルだけ** を throwaway tempdir に
  snapshot し、host repo / `.git` を **マウントしない** (host 汚染が構造的に不可能)。
  Docker + devcontainer CLI が必要。
- `tests/*.py` は sandbox / image 検査 (`test_just_sandbox.py` / `test_devcontainer.py` 等、
  `just test` が列挙して回す)。Docker 不要の静的検査は `tests/unit/` に置く (`just ci` の
  `test-unit` が拾う。root に置くとどの gate にも乗らない)。recipe 追加・改名後は `just ci` でなく
  **full `just test`** を回す。sandbox assert は
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
- **prek の stash/rollback** は staged を取りこぼすことがあり、**untracked は stash しない**
  (新規テストが未 commit の helper を import すると、hook の ty が staged 版と食い違って落ちる)
  → commit 後に `git show --name-only` で収録を検証し、別 commit に入れる新規ファイルは
  hook の間だけ退避する (memory `feedback_prek_stash_partial_commit`)。
- **statusline-command.sh が `.git/index.lock` レース** を起こす → `Unable to create
  .git/index.lock` が出たら active な git 書込みプロセス不在を確認して stale lock を
  除去 (memory `feedback_statusline`)。
- **commit.gpgsign=true** — 全 commit が GPG 署名される。履歴書き換え時は
  `git commit-tree -S` で再署名、force push は ruleset 一時トグル
  (memory `feedback_git_history_rewrite_gpg`)。
- **Node は bun 一本。agent は npm/yarn/pnpm を一切叩けない** (guard が常時 block、
  `corepack pnpm`/`pnpm@ver`/`corepack --cwd … pnpm` 含む。**ADR 0027** が ADR 0017 の
  per-repo pnpm carve-out を partial supersede)。corepack のマシン供給自体は **ADR 0017**
  のまま温存 (node 同梱シム + `PNPM_HOME` は store アンカーのみ、`pnpm add -g` は依然
  abort、global CLI は mise npm: のみ)。`corepack enable`/`prepare`/`use` は素通り。
- **mise の npm backend は `bun` 必須 (ADR 0036)、bun backend は `npm_args` を読まない
  (ADR 0040)**。`auto` (aube) だと claude-code が 500 バイトの stub のまま「成功」する。
- **native Windows** では bare `bash` が System32 の WSL に落ち、shebang レシピは Git Bash から
  叩く必要がある。justfile の shell 設定、`scripts/*.sh`、mise 設定、Windows で動く Python を
  触る前に `docs/runbook/windows-host.md` を読む (shell 選択、cygpath、`%APPDATA%\uv`、
  npm backend の stub、runner の Machine PATH、cp932)。
- **self-hosted runner のディスク GC (ADR 0035)**: WSL の vhdx が docker と開発キャッシュで
  膨らみ、C: が尽きると WSL 自体が起動しなくなる。`just runner-gc-install` が GC を仕掛け、
  `just status` が状態と hook の受理を出す。`scripts/runner_gc*` や `just runner-gc*` /
  `disk-gc` / `wsl-compact` を触る前に `docs/runbook/runner-disk-gc.md` を読む。
- devcontainer features は Microsoft 公式のみ (community 不可、memory
  `feedback_no_community_devcontainer_features`)。

## docs / handover / intent

- `docs/handover.md` / `docs/intent.md` は **gitignored** (ローカルのみ、追跡しない)。
  dated backup は `docs/handover-*.md` / `docs/intent-*.md` glob で ignore。
- `docs/adr/` は ADR (Accepted 後 immutable)。`docs/` の他は現状のみ記述 (履歴は ADR / git)。

## Git / PR

- default branch = `main`。feature / fix / chore / docs は branch → PR → **squash merge** to `main`。
- **draft PR では CI が回らない** (全 workflow の job に `if: … pull_request.draft == false`、
  `ready_for_review` で起動)。作業中は `gh pr create --draft`、検証したくなったら `gh pr ready`。
  hironow/skills の `ci.yaml` も同じ扱い。
- Conventional Commits (type が structural/behavioral を encode)。詳細は `ROOT_AGENTS.md`。
- YAML は `.yaml` (not `.yml`)、Docker Compose は `compose.yaml`。
