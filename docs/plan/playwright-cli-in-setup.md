# playwright-cli を初期設定（mise の宣言）に入れる

**Date:** 2026-10-21
**Status:** Proposed（独立レビュー #1・#2 済み: #1 の 2 件を反映し、#2 で APPROVE。利用者の裁定待ち）
**Branch:** `feat/playwright-cli-mise`
**Related:** ADR 0006（mise の pin 戦略）/ ADR 0023（activate-only）/ ADR 0017（pnpm global の退役 → global CLI は mise の `npm:` バックエンド）/ ADR 0027・0036・0040（Node は bun、npm backend は bun、bun は `bun_args`）/ hironow/skills の `playwright-cli` skill（`dump/harness/skill-lock.json` で宣言）
**Blocking decisions:** なし（利用者に 2026-10-21 に確認済み: 版は `latest` / 同梱ブラウザは入れない / 範囲は `config/mise/config.toml` だけ）
**Graduates to:** 安定後 done。新しい decision は無いので ADR は起こさない（不採用の代替案の理由はこの plan に残す）

## 目的

hironow/skills の `playwright-cli` skill は `playwright-cli` が PATH にある前提で書かれている（F1）。ところが CLI 本体はどの機体の初期設定にも宣言が無く、skill のフォールバック `bunx --package @playwright/mcp playwright-cli` も成立しない（F2）。`config/mise/config.toml` に 1 行足して、`install.sh` → `mise install`（Mac / Linux / WSL の初期設定）で PATH に載るようにする。変更範囲はこれだけにする（F8 の global gitignore は今回触らない。理由は「対象外」）。

## 確定させた事実（一次情報で確認済み）

- **F1**: `playwright-cli` はこの Mac に入っていない（`command -v playwright-cli` は空、`mise ls --current` にも無い）。skill だけが `~/.agents/skills/playwright-cli` にあり、`~/.claude/skills` と `~/.codex/skills` へ symlink されている。
- **F2**: skill のフォールバックは成立しない。npm registry の `@playwright/mcp` の `bin` は `playwright-mcp` だけで、直近 14 版すべて同じ（`playwright-cli` という bin を持つ版は無い）。`playwright-cli` を提供するのは `@playwright/cli`（`bin: {playwright-cli: ...}`）。
- **F3**: 専用の `MISE_DATA_DIR` で `"npm:@playwright/cli" = "0.1.22"` を `mise install` すると、その下の `installs/npm-playwright-cli/0.1.22/bin/playwright-cli` に入り、`mise which playwright-cli` もそこを返す（`--version` は `0.1.22`）。**ただし `MISE_DATA_DIR`（とスクラッチ `HOME`）を分けても宣言集合は隔離されない**: この機体では mise が利用者の global config も読むため、`mise install` は 36 道具（4.1GB）を入れた（2026-10-21 実測）。隔離できると言えるのは道具の配置先だけ。
- **F4**: ブラウザの実体は落ちない。`PLAYWRIGHT_BROWSERS_PATH` を空の専用 dir にして `latest`（→ 0.1.22）を入れ、インストール後も `open --browser=chrome` → `close` の後も、その専用 dir は空（0 件）だった。既存の `~/Library/Caches/ms-playwright/chromium-*` も増えていない（2026-10-21 実測）。ただし CLI は既定の `~/Library/Caches/ms-playwright/` に小さなメタデータ（`b/browser@<hash>` 1.1KB × n と `cli-update-check.json`）は書く。
- **F5**: この Mac の Chrome で実走できた。`playwright-cli open --browser=chrome https://example.com` が headless で開き、`close` も通った（同梱ブラウザ無しで動く）。出力は実行ディレクトリの `.playwright-cli/` に落ちた。
- **F6**: `@playwright/cli` の `latest` は `0.1.22`（2026-09-28 公開）。`next` は `0.1.18-alpha-...`。`0.1.22` の依存は `playwright` / `playwright-core` の `1.64.0-alpha-...`（パッケージ側が固定する）。
- **F7**: mise は `config/mise/config.toml` を project config として読まない（`/tmp` に `config/mise/config.toml` を置いた dir で `mise config ls` → 解決は `~/.config/mise/config.toml` だけ）。devcontainer の `post-create.sh` が読むのは baked の `/etc/mise/config.toml`。よってこの追加はイメージとサンドボックスの道具一覧に現れない。
- **F8**: `playwright-cli` は既定で cwd に `.playwright-cli/` を作る（F5 の実測）。`dump/gitignore-global`（`just deploy` が `~/.config/git/ignore` に置く）には `.cursor/`・`.cline/`・`.copilot/`・`.indexing/` はあるが、`.playwright-cli/` は無い。
- **F9**: Homebrew にも `playwright-cli` 0.1.22 がある。依存は brew の `node`（mise の node とは別に、brew が node を引く）。
- **F10**: `just bump-tool` は ruff / ty 専用（`scripts/bump_tool.py` の `TOOLS`）。`npm:` の道具（portless / quint / cf など）は同じく手で行を動かす。
- **F11**: `latest` の解決結果は **0.1.22**（`mise install` の行 `mise ✓ npm:@playwright/cli@0.1.22` と `installs/npm-playwright-cli/` の dir 名）。`--version` は `0.1.22`、`open --browser=chrome https://example.com` は `Page Title: Example Domain` を返し、`close` も成功した。実走は repo の外（`/tmp/pwiso`）で行っており、repo に `.playwright-cli/` は作っていない。

## 変更内容

### 1. `config/mise/config.toml` — `"npm:@playwright/cli" = "latest"`

"AI agent CLIs" ブロック（`npm:@openai/codex` …）に置く。コメントに次を残す。

- hironow/skills の `playwright-cli` skill が PATH 前提にする CLI（skill のフォールバックは壊れている）。
- ゲートではないので、他の agent CLI と同じ `latest`。
- `npm:` は `[settings.npm] package_manager = "bun"` で解決する（ADR 0036 / 0040）。npm / yarn / pnpm の起動ではないので bun-only（ADR 0027）に触れない。
- 同梱ブラウザは入れない（`--browser=chrome` か、必要時に `playwright-cli install-browser`）。
- `playwright-cli install --skills` は走らせない（skill は hironow/skills と `just skills-place` が持つ）。

### 2. `tests/unit/test_mise_playwright_cli.py`（新規）

宣言の番人。RED を先に取る。検査は決定的（ネットワークを使わない）。

- `config/mise/config.toml` の `[tools]` に `npm:@playwright/cli` があること。
- キーが `playwright`（テストランナー本体）や registry エイリアスでないこと（`npm:playwright` は別物）。
- 値が `latest` か exact semver であること（空・範囲・`^` 表記を弾く）。

### 3. `docs/plan/playwright-cli-in-setup.md`（本ファイル）

## 検証

- RED: 変更 1 の前にテストを実行し、落ちることを失敗メッセージごと記録する。
- GREEN: `just ci`（unit を含む）が緑。`[tools]` のキーを全数で列挙するテストは無い（`tests/unit/` の config/mise 読み取りは rtk / headroom / quint / ruff / ty を名指しする）ので、他の gate へは波及しない。
- 隔離した実機確認（`latest` の解決とブラウザ非同梱を同時に取る。独立レビュー #1 の指摘 2）:
    - 専用の `MISE_DATA_DIR` とスクラッチ `HOME` に config を置き、**`PLAYWRIGHT_BROWSERS_PATH` も空の専用 dir** にする。cwd は repo の外にする（`.playwright-cli/` を repo に作らせない）。宣言集合は隔離されないので、入った道具の一覧と大きさも記録する（F3）。
    - `"npm:@playwright/cli" = "latest"` で `mise install` し、**解決された実バージョン**（`installs/npm-playwright-cli/` の dir 名）を記録する（F11）。
    - インストール直後と、`--version` / `open --browser=chrome` → `close` の後で、`PLAYWRIGHT_BROWSERS_PATH` が空であること。既定の `~/Library/Caches/ms-playwright` にもブラウザ実体が増えていないこと（CLI 自身のメタデータは書かれる。F4）。
- merge 後の main: `mise -C / install` → `just deploy` → `just doctor`（ok / warn / err の数を記録）→ mise activate 済みのシェルで `playwright-cli --version`。
- devcontainer 無影響: F7 の確認と、`just test`（Docker がある機体で）。

## 対象外（今回やらない）

- 同梱ブラウザの導入（`install.sh` に `install-browser` を足す）— 利用者判断で却下。Chrome で足りる（F5）。
- devcontainer image の `/etc/mise` への bake — サンドボックスは `just check` 用で、ブラウザも無い（F7）。
- `dump/macbook/Brewfile` への `brew "playwright-cli"`（F9）— Mac 専用になり、brew の node を引き、global CLI は mise の `npm:` という方針（ADR 0017、`install.sh` の corepack 節のコメント）に反する。
- skill 本文のフォールバック行の修正 — hironow/skills 側。PR 本文に follow-up として書く。
- global gitignore への `.playwright-cli/` の追加（F8）— 全 repo の未追跡ファイル表示に効く独立の設定変更なので、この PR には入れない（独立レビュー #1 の指摘 1。利用者に確認済みの範囲「`config/mise/config.toml` だけ」とも一致）。CLI を使う repo に `.playwright-cli/` が残って邪魔になったら、別の PR として提案する。
- `scripts/ai_tools_check.py` / doctor への追加検査 — 宣言の存在は変更 2 のテストが押さえる。doctor に足すのは別件。

## リスク / 未検証

- Windows native: `install.sh` は Windows で `mise install` を skip し、`bootstrap.ps1` 経由で mise が入る。`npm:` + bun の Windows 経路はこの plan では実機検証していない（他の `npm:` ツールと同じ経路）。
- `latest` なので CLI のコマンド体系は動きうる。skill は hironow/skills 側で upstream commit（`metadata.upstream: microsoft/playwright-cli@655530f`）に固定されている。実害が出たら pin に切り替える（F10 の手動 bump）。
- CLI は起動時に `~/Library/Caches/ms-playwright/cli-update-check.json` を書く（F4）。更新確認 / テレメトリの停止は今回扱わない（ADR 0047 の rtk / headroom とは別レイヤ）。
- F5 の実走は main の作業ツリーで行い、`.playwright-cli/` を作った（削除済み、main は clean）。

## レビュー

### #1（Codex `codex exec`、2026-10-21）— REVISE → 全件採用

- **指摘 1（P2、範囲の食い違い）**: `Blocking decisions` の「範囲は `config/mise/config.toml` だけ」に対し、global gitignore の変更と対応テストを同じ PR に入れていた。独立した設定変更なので分けるべき。
  → **採用**。gitignore の変更とテストを外し、「対象外」に follow-up として移した。全 repo の未追跡表示に効く変更を、CLI 宣言の検証と同じ commit に混ぜないのは妥当。
- **指摘 2（P2、ブラウザ非同梱の検証欠落）**: `MISE_DATA_DIR` を分けてもブラウザキャッシュは隔離されず、固定版 0.1.22 の F4 だけでは `latest` の解決結果に一般化できない。
  → **採用**。`PLAYWRIGHT_BROWSERS_PATH` を空の専用 dir にし、インストール後と Chrome 実走後の両方でブラウザ実体が無いことを確かめる手順を「検証」に足し、実行した（F4、F11: `latest` → 0.1.22、専用 dir は前後とも 0 件、Chrome 実走成功）。この過程で、以前の「隔離した」という書き方が誤りだったことも分かった（`MISE_DATA_DIR` を分けても宣言集合は隔離されない。F3 に実測を書き直した）。

### #2（Codex `codex exec resume --last`、2026-10-21）— APPROVE

- 指摘 1・2 の解消を確認。「追加で修正必須の指摘はありません」。実測はこちらの報告として受理（再実行はしていない）。新しい宣言は既存の経路（global mise config を置いて `mise -C / install`）に乗り、`just ci` が unit test と `just check` を含むので、この規模で追加の仕組みは要らない、と判断。

### 実装後の gate

- `just ci`（worktree `feat/playwright-cli-mise`）: exit 0（fast gate passed。markdownlint 0 issues、semgrep 0 findings、forbidden-token branch/tree clean を含む）。
- RED → GREEN: `tests/unit/test_mise_playwright_cli.py` は宣言前に 2 failed / 1 passed、宣言後に 3 passed。
