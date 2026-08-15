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
    - **`skills` は additive** (`ADDITIVE_DIRECTORIES`): 欠落 skill のみ追加、既存
      target は**上書きしない・削除しない**。`bunx skills` CLI が `~/.agents/skills`
      へ install した symlink (上流 + `bunx skills add <skills-repo>`) を churn/orphan
      削除しないため
    - **skills は宣言管理 (ADR 0038)**: サードパーティ skill の実体は CLI が持ち、
      git は正規化宣言 `dump/harness/skill-lock.json` のみ追跡する
      (`just dump-skills-lock` で更新 / `just restore-skills-lock` で新マシン復元 —
      best-effort, upstream HEAD)。`skills/` submodule は**自作 skill 専用**で、
      **home→repo の skills import は全面廃止** (`skills/learned` のみ例外)。
      lock 管理名が submodule に再出現すると `just skills-lock-check` (`ci` 組込み)
      が fail する
    - **skills 品質ゲート**: SKILL.md を1つも含まない dir は構造ゲートで、
      `dump/harness/skills-sync-exclude.toml` (機械可読 SSoT) の `exclude` 記載名は
      denylist で除外される (junk の流入も防ぐ)
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
| `just ci` | fast non-Docker gate: ruff / shellcheck / markdownlint / meta-semgrep + `lint-claude` + unit tests (`tests/unit/`) + `semgrep --test` + `tofu test` + `portless-doc-check` + `instruction-budget` |
| `just lint-claude` | 公式 `claude plugin validate --strict` (claude CLI 不在時は skip) + stdlib の effective-settings 検証 (ADR 0037/0041)。サードパーティ claudelint は**退役済み** (ADR 0041、trust 判断)。CI gate は `Claude Config Lint` workflow が pinned `bunx @anthropic-ai/claude-code` で公式 validate を回す (CI は `just ci` 非実行) |
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
- **bun backend では `npm_args` は読まれない (ADR 0040)** — mise は package manager ごとに
  別キーを読む (bun は `bun_args` のみ)。claude-code の native binary が動くのは
  **bun の default-trusted リストに載っていて postinstall が走る**から。postinstall 必須で
  default-trusted に**無い** npm ツールを足すときは `bun_args` / trustedDependencies を検討
  (memory `project_mise_npm_ignore_scripts`)。
- **npm backend の package manager は `bun` 必須 (ADR 0036)**。既定の `auto` は mise 内蔵の
  **aube** を使い、その virtual-store レイアウトが claude-code の postinstall を無力化する
  (263MB の native binary が展開されず `bin/claude.exe` が **500 バイトのスタブ**のまま残り、
  シムが `node claude.exe` を実行して `ERR_UNKNOWN_FILE_EXTENSION`)。**install は成功扱いで
  何も報告しない** — 動き続けるのは npm-global の野良コピーが PATH で mise を shadow して
  いるからで、その野良を消す `just prune-rogue-npm-globals` こそが `claude` を壊す、という
  倒錯が起きる。関連する罠:
    - **backend を変えても既存 install は直らない**。`mise uninstall … && mise install …`
      で入れ直すまでスタブのまま。
    - **bun は `node_modules/.bin` にシムを作らず `<install>/bin/` に置く**。mise activate
      前に開いたシェルは aube 時代の `.bin`(空) を PATH に掴んだままなので、mise 版に到達
      できない。`mise env` は正しく `bin/` を出すので、**シェルを開き直せば直る**。
    - **Windows では削除済みの exe でプロセスが動き続ける**。prune 後も現行セッションは
      平然と動くが、次回起動時にそのパスは無い。`ps -W` で実体パスを確認しないと気付けない。
    - **WinGet 版は野良コピーの陰に隠れる**。野良が PATH 勝負に勝っている間は見えず、
      prune した瞬間に現れる (実測: 隠れていた WinGet 2.1.198 が mise の 2.1.215 より
      6 patch 古かった)。`just doctor` の `winget-shadow` が検出する。
- **Windows の shell 選択 (最重要運用)**: WSL の `C:\Windows\System32\bash.exe` が Git Bash を
  shadow する (Windows は bare `bash` を PATH より先に System32 で解決する) ため、`just` の
  bash 系レシピが WSL に落ちうる (WSL 未導入 host では顕在化しない)。効き方が2層に分かれる:
    - **plain レシピ** (`doctor` / `harden-env` 等 `bash scripts/*.sh`) → justfile の
      `set windows-shell := ["sh", …]` (#231) + prelude で解決済み。System32 に `sh.exe` は
      無いので `sh`=Git Bash に解決するが、**raw な非 login msys sh は呼び出し元の PATH 順を
      保存する**ため、素の永続 PATH (Machine の System32 が User の Git `usr\bin` より先) では
      内側 `bash` が WSL に落ちていた (doctor が WSL Ubuntu の apt just 1.21 で走る実害)。
      現在は windows-shell の prelude が `/usr/bin` を PATH 先頭に足してから内側
      `/usr/bin/sh` に exec するので → **PowerShell からでも直接叩ける**
      (recipe shell 内に閉じた scoped prepend で、下記の blanket prepend 非推奨とは別物。
      ガード: `tests/unit/test_windows_shell_usr_bin_path.py`)。
    - **shebang レシピ** (`dump` / `scaffold-agent-baseline` 等 `#!/usr/bin/env bash`。
      `deploy` / `clean` は #231 同様に `bash scripts/*.sh` の plain レシピへ移行済みで
      PowerShell から直接叩ける — `tests/unit/test_deploy_clean_linewise.py` がガード) → `set shell` /
      `windows-shell` の影響外で `env→bash` が PATH 順に従う。素の PowerShell は System32(WSL)
      が先なので失敗する → **Git Bash から叩く** (`/usr/bin` 先頭ゆえ `env→bash`=Git Bash)。
      PowerShell 固執なら Git `usr\bin` を PATH 先頭に prepend する手もあるが、`find` / `sort` 等
      Windows 版コマンドを shadow するため blanket prepend は非推奨。
  旧来の注意も継続: PowerShell の shebang レシピは Git `usr\bin` が (登録) PATH に無いと
  `could not find cygpath` で全滅。**native Windows の uv は `%APPDATA%\uv\uv.toml` を読む** —
  無いと quarantine が効かず `uv run` が uv.lock を書き換え、pre-commit が落ちる
  (`just harden-env` が書く)。cygpath / uv とも `just doctor` の Windows セクションが検出して
  修正手順を提示する。
- **Node は bun 一本。agent は npm/yarn/pnpm を一切叩けない** (guard が常時 block、
  `corepack pnpm`/`pnpm@ver`/`corepack --cwd … pnpm` 含む。**ADR 0027** が ADR 0017 の
  per-repo pnpm carve-out を partial supersede)。corepack のマシン供給自体は **ADR 0017**
  のまま温存 (node 同梱シム + `PNPM_HOME` は store アンカーのみ、`pnpm add -g` は依然
  abort、global CLI は mise npm: のみ)。`corepack enable`/`prepare`/`use` は素通り。
  `dump/npm-global` / `add-pnpm-g` / `update-pnpm-g*` / `check-pnpm-g` は退役済み。
- **WSL self-hosted runner の disk ratchet (ADR 0035)**: runner を載せた WSL distro の
  `ext4.vhdx` は docker の image / stopped container / **BuildKit build cache** が
  無制限に積み上がる (既定で GC policy が無い)。放置すると C: が枯渇し、しかも
  **空きが尽きると vhdx を展開できず WSL 自体が起動不能になる** (`I/O error @util.cpp`
  → systemd 起動失敗) デッドロックに入る。`just runner-gc-install` が **2時間保持**の
  GC を三重に仕掛ける (job-completed hook / hourly timer / journald cap)。関連する罠:
    - **状態確認は `just status`**。Windows/WSL 両 leg の timer・task・hook を一度に出し、
      **hook が runner に受理される形式か**と**直近ジョブで拒否されていないか**まで見る
      (下記の事故を二度と見逃さないため)。
    - **hook のパスは `.sh`/`.ps1`/`.js` 拒否検証がある**。runner が
      `ArgumentException: ... is not a valid path to a script` で弾くため、拡張子なしの
      `/usr/local/bin/runner-gc` は **877 ジョブ全てで失敗**していた (`.env` 上は正しく
      見えるので気付けない)。値は**パスであること**も必須で、`powershell.exe -File <script>`
      のようなコマンド行も同じ検証で落ちる。**失敗はジョブ自身の Worker ログにしか残らない**
      (journal にもタスク履歴にも出ない)。
    - **job 検出は `pgrep -x Runner.Worker` 必須**。`pgrep -f` は GC 自身のコマンド行に
      マッチして「常時ジョブ実行中」と誤判定し、GC を無言で永久停止させる。
    - **さらに hook は `Runner.Worker` の内側から呼ばれる**ので、素直に検出すると
      「自分を起動したジョブ」を理由に**毎回 SKIP** する。プロセス**祖先**と突き合わせ、
      祖先でない worker (= 同時実行の別ジョブ) のときだけ退避する。
    - **rootless docker のホストでは root の timer が別 daemon を掃除する**。hourly timer は
      root で走るが root の context は `/var/run/docker.sock` (rootful) に解決し、実在庫は
      `/run/user/<uid>/docker.sock` (rootless) 側にある。`docker info` は空の rootful でも
      成功するため **回収ゼロで exit 0** になる。GC は root 実行時、runner ディレクトリの
      **所有ユーザで docker leg を再実行**する (`runuser` + `XDG_RUNTIME_DIR`)。root 自身の
      leg も残すので rootful 専用ホストは無影響。
    - **toolcache は「世代数」でなく `major.minor` 系列で回収する**。workflow は
      `go-version: 1.25.x` / `node-version: 22.x` / `python-version: 3.13` のように**系列**を
      pin し、`setup-*` は系列内の最新 patch に解決する。単純な「最新 N 世代を残す」は matrix が
      使う版を消す (この runner では rvc-hfie=3.10 / m4k3=3.13 / just-ag=3.14 と Python が3系列)。
      **系列ごとに最新 patch を残し**、`RUNNER_GC_TOOLCACHE_KEEP` (既定 5) で系列数を上限する。
    - **並び替えは `sort -V` 必須**。辞書順だと `1.25.8` が `1.25.11` より後に来て**最新版を消す**。
      削除単位は `<version>/` ディレクトリ丸ごと (`<version>/<arch>.complete` マーカーが内側に
      あるため、部分削除は「cached のはずが実体無し」を作る)。
    - **最終使用時刻は取れない**。`relatime` かつ `_tool` を walk する処理 (GC 自身を含む) が
      atime を書き換えてしまう。mtime は install 時刻で使用時刻ではない (matrix で現役の
      Python 3.10.20 は mtime が7週前)。だから時間予算でなく系列で判定している。
    - この leg だけは `RUNNER_GC_FORCE=1` でも job 実行中はスキップする (cache 喪失は時間の損
      だが、使用中の toolcache 削除は job を即死させるため)。
    - **Windows→WSL dispatch は `MSYS_NO_PATHCONV=1` / `MSYS2_ARG_CONV_EXCL='*'` 必須**。
      Git Bash が `/usr/local/bin/...` や `/mnt/c/...`、素の `/` すら Windows パスへ
      書き換えてから `wsl.exe` に渡すため。
    - **guest 内で消しても C: は増えない。返すのは `fstrim`**。vhdx は解放済み ext4 block を
      Windows から掴んだままなので、45GB prune しても C: が動かず「GC が効いていない」と見える。
      WSL の vhdx は通常 **sparse** なので `fstrim /` でホールパンチすれば**無停止・非管理者で**
      即返却される (実測 43.5GB、vhdx 実占有 174→130GB)。GC の root leg 末尾で実行する。
    - **スラックは実占有 (`du -B1`) で測る**。`stat -c %s` は論理サイズ=高水位マークで decrease
      しないため、`論理 - 使用` は「既に返却済みの分」まで slack に数えて過大報告する
      (実測: 報告130GB / 実際33GB)。`just wsl-compact` は sparse フラグ
      (`fsutil sparse queryflag`) も出す。**sparse なら compaction 不要、非 sparse なら必要**で
      機体ごとに答えが違う。
    - **実際に肥大するのは docker ではなく開発キャッシュ**。`~/.cache/uv` 単体で 44GB
      (姉妹機は 126GB)、Windows profile 全体が ~2.5GB なのと対照的。`just disk-gc` は
      **WSL の runner ユーザ HOME まで掃除する** (`DISK_GC_NO_WSL=1` で無効化)。hourly timer に
      は載せない (対話作業と共有のため)。`~/.cache/huggingface` は既定で対象外
      (`DISK_GC_HUGGINGFACE=1` で opt-in。単一モデル 77GB、wheel の再取得とは訳が違う)
    - **compaction は非 sparse 機のフォールバック**。既存スラックの返却に管理者権限 +
      `wsl --shutdown` (= runner 停止) が要るため `just wsl-compact` は計測と手順提示に
      留める advisory。**`wsl --manage --set-sparse` を自分で有効化しない** — MS が
      データ破損リスクで無効化中 (`--allow-unsafe` が必要)。既に sparse な vhdx を
      `fstrim` で使うのは別物で、こちらは安全。
    - **workspace sweep は両 leg 共通**。WSL 側は `_work/<repo>` が 23GB (toolcache 3GB より
      遥かに大きい) で、埋まったのはこちらなので非対称は逆向きだった。判定は
      `.runner-gc-last-used` マーカー (Linux でもディレクトリ mtime は「直下の増減」しか
      追わず、深い階層の再ビルドを見ないため)。runner 所有ディレクトリは**名前の明示列挙**
      (`_` 接頭辞判定だと `_foo` という実リポを永久に除外する)。旧 `bin.*`/`externals.*` は
      **`bin`/`externals` が symlink のときだけ**、かつ **24h フロア**で回収 (update は
      staging 後に symlink を切替えるため 2h だと途中を掴む)。`RUNNER_GC_ROOT` で単一
      install を対象にできる (多忙な runner では idle window が来ないので、破壊的経路を
      合成 root で検証するため)。**ジョブ実行中に走らせるには `RUNNER_GC_ROOT` と
      `RUNNER_GC_ALLOW_BUSY=1` の両方**が要る (`RUNNER_GC_FORCE` では代替できない)。
      root を指定するのは「どの install か」の宣言であって「触って安全か」ではない —
      手動実行には `RUNNER_WORKSPACE`/`GITHUB_WORKSPACE` が無く、**実行中ジョブが今書いて
      いる checkout を判別できない** (前回ジョブが retention より前に終わっていれば、
      新しいジョブがビルド中でも回収対象に見える)。
    - **native Windows 側の主犯は `_work/<repo>`** (`_diag` や `_work/_temp` ではない。
      実測 5.1G / うち Rust `target/` 3.7G に対し `_temp` は 12K)。**ディレクトリ mtime で
      期限判定してはいけない** — Windows は入れ子のファイル更新で親ディレクトリの
      `LastWriteTime` を更新しないため、数分前にビルドした checkout が2ヶ月前の日付を
      示す。`.runner-gc-last-used` マーカーを GC 自身が押して、それを基準に aging する。
      加えて `RUNNER_WORKSPACE` / `GITHUB_WORKSPACE` の指す checkout は無条件に除外
      (hook がステップ間で発火しても現行ジョブを消さないため)。
    - **workspace の削除は素の `Remove-Item` では完走しない**。junction (5.1 の
      `-Recurse` はリンクを**貫通して**リンク先を消す)、read-only な `.git/objects`、
      MAX_PATH 超え (`node_modules`) の3つが原因。reparse point を先に非再帰で
      detach → read-only 解除 → 残りは `robocopy /MIR /XJ` で潰す順序が必須。
    - **runner 自己更新の残骸 (`_work/_update`, 旧 `bin.*`/`externals.*`) は 24h の
      別枠 floor** で回収する。2時間枠だと進行中の self-update を巻き込む。旧版削除は
      `bin`/`externals` が **symlink として解決できる時だけ** (plain install では
      `bin.*` が runner 本体そのものなので消すと壊れる)。
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
