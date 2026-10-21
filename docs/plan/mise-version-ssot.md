# mise 道具の版本を SSOT 化する（正本 1 つ + 生成 + drift check）

**Date:** 2026-10-21
**Status:** Accepted（2026-10-21、所有者の裁定。PR #485）/ 実装済み
**Branch:** `feat/mise-version-ssot`
**Related:** ADR 0006（mise の pin 戦略。本件はその §3 が約束した build-time check を一般化して実現する）/ ADR 0005（install path）/ ADR 0036・0040（npm backend は bun）/ ADR 0027（bun-only）/ ADR 0044（ruff/ty）/ ADR 0051（決定は queue で追跡）/ 前段: PR #484（playwright-cli）
**Blocking decisions:** なし（利用者に 2026-10-21 に確認済み: 対象は **mise が持つ道具だけ**、画像が検証つき tarball で入れる **uv / just / sheldon の定数も含める**、正本は **新規 1 ファイル**、生成器は **Python（言語規約の例外として plan と ADR に記録。下の「例外裁定」）**）
**Graduates to:** ADR 0060（Proposed、利用者の PR コメントで裁定）+ decision-queue の決裁待ち行。安定後 done。

## 目的

このリポジトリは「2 つの環境が同じ正本から同じ版本の道具を入れる」と README に書いているが、実際には **同じ道具の版が複数の場所に手で書かれ、片方だけが動いても誰も気づかない**。

- 実測（F1〜F3）: `config/mise/config.toml` は 37 道具、devcontainer が bake する `/etc/mise/config.toml` は 18 道具。重複する 18 のうち、値まで一致するのは 3 つ（golangci-lint / quint / cf）だけで、他は「host は `latest`、画像は凍結版」という世代差。さらに **画像は同じ道具を 2 経路で入れていて、uv と just はその 2 経路で値が食い違っている**（tarball の uv 0.12.21 vs mise frozen 0.13.1、just 1.58.0 vs 1.59.0）。PATH は mise の shim が先なので実効版は mise 側で、不一致は黙って残る。
- ADR 0006 §3 は「mise.toml と feature の定数は一致すること。実装 PR が build-time check を足す」と決めているが、**その検査は quint の 1 件（`tests/unit/test_sandbox_check_tools.py`）しか無い**（F6）。

本件は、画像と bootstrap が使う版本を **1 ファイルの正本**に集め、そこから `install.sh` の該当領域を **生成**し、`just check` で「再生成して差分なし」を **検査**する。これで版の事実は道具ごとに 1 か所になり、片側だけの bump は CI で止まる。

## 確定させた事実（一次情報で確認済み）

- **F1**（2026-10-21 実測、`tomllib` + 正規表現で両ファイルを解析）: `config/mise/config.toml` は 37 道具、`.devcontainer/features/dotfiles-tools/install.sh` の `/etc/mise` heredoc は 18 道具。重複 18、完全一致ピンは `aqua:golangci/golangci-lint` 2.15.0 / `npm:@informalsystems/quint` 0.33.0 / `npm:cf` 1.0.0-beta.18 の 3 つ。他 15 は host が `latest`（`node` は `lts`）、画像が凍結版。
- **F2**: `install.sh`（root、bootstrap）の固定は `_mise_ver="2026.9.0"`（L172）と `_just_ver="1.58.0"`（L252）。後者は `config/mise/config.toml` の `just = "latest"` が今日解決する 1.59.0 と既に食い違う。
- **F3**: 画像は同じ道具を 2 経路で入れる。`.devcontainer/features/dotfiles-tools/install.sh` が検証つき tarball を `/usr/local/bin` に置き（`UV_VERSION="0.12.21"` L102、`JUST_VERSION="1.58.0"` L140、`SHELDON_VERSION="0.8.5"` L156）、`/etc/mise/config.toml` が mise で入れる（`uv = "0.13.1"`、`just = "1.59.0"`）。`devcontainer.json` の PATH は `/root/.local/bin:/opt/mise/shims:/usr/local/bin:...`（L77）なので **shim が勝つ**。uv と just の値はこの 2 経路で食い違い、sheldon は tarball 側にしか無い（`/etc/mise` には bake しない）。
- **F4**: 統合先の値は上流に存在する（`curl -o /dev/null -w %{http_code}` で確認）: uv 0.13.1 の `uv-x86_64-unknown-linux-gnu.tar.gz.sha256` = 200、just 1.59.0 の `SHA256SUMS` = 200、sheldon 0.8.5 の tarball = 200。
- **F5**: `config/mise/config.toml` の sheldon は `aqua:rossmacarthur/sheldon = "0.8.5"`（画像の tarball と一致）。rust（host `1.99.1` + rust-analyzer）と、画像が evaluator ビルドに使う `RUSTUP_VERSION="1.29.1"` / `RUST_TOOLCHAIN="1.99.0"` は別の役割。
- **F6**: ADR 0006 §3（`docs/adr/0006-mise-tool-version-pinning.md` L165, L191）は「feature の hardcoded 定数と mise.toml の一致を build-time check で落とす」と書くが、存在するのは `test_quint_is_baked_at_the_same_pin_as_the_workstation` の 1 件だけ。
- **F7**: mise は repo の `config/mise/config.toml` を project config として読まない（`/tmp` で `mise config ls` を実測）。画像が見るのは baked の `/etc/mise/config.toml` だけ（`post-create.sh` も同じ）。よって「画像の道具一覧」は生成対象の正本から一意に決まる必要がある。
- **F8**: `install.sh` の文字列を読む既存テストは 5 本（`test_sandbox_check_tools.py`（heredoc → `tomllib`）、`test_go_tooling.py`、`test_devcontainer_download_retries.py`（論理行単位）、`test_install_mise_bootstrap.py`、`test_mise_data_dir_relocation.py`）。生成する領域はこれらの解釈を壊さない形を保つ必要がある。
- **F9**: prek の gate は段で分かれる。**pre-commit が呼ぶのは `just fmt` と `just lint`**（`.pre-commit-config.yaml` の `just-fmt` / `just-lint`）で、**`just check` は pre-push 専用**（同 `just-check`、`stages: [pre-push]`）。しかも pre-push は既定のインストール対象外（同ファイル冒頭の注記。pre-push shim は git-lfs のもの）。`just ci` は `check` を依存に含む。コミット時に止めたい検査は `lint` に置くのが既存の流儀（例: `scripts/check_uv_exclude_newer.py`、`scripts/check_mcp_node_runner.py` は `lint` と `check` の両方にある）。
- **F10**: 生成器の流儀は既にある（`scripts/sync_agents.py` の managed block + `--preview`、`scripts/skills_lock.py` の `dump/restore/place/check`、`scripts/bump_tool.py` の「全宣言を一括書換え + 拒否条件」）。新しい ADR は `docs/decision-queue.md`（ADR 0051）の決裁待ち行として追跡し、所有者の PR コメントで Accepted にする。
- **F11**: ruff / ty は 3 か所（root / emulator の pyproject、`config/mise/config.toml`）に固定されているが、`just bump-tool` が 1 コマンドで全宣言を書き換える（利用者の裁定により本件の対象外）。

## 変更内容

### 1. `config/mise/image-tools.toml`（新規、正本）

画像（devcontainer）と、mise が無い機体の bootstrap が使う **凍結世代**。**版は道具ごとに 1 回だけ書く**。

```toml
[settings.npm]
package_manager = "bun"

[tools]              # → /etc/mise/config.toml に bake する（18 道具）
bun = "1.4.3"
just = "1.59.0"      # tarball 経路（/usr/local/bin）もこの値を使う
uv = "0.13.1"        # 同
... (残り 16)

[fetch]              # → SHA/attestation 検証つき tarball（/usr/local/bin）
mise_tools = ["uv", "just"]   # 版は [tools] から取る（ここには書かない）
"aqua:rossmacarthur/sheldon" = "0.8.5"   # mise 道具ではないのでここに書く

[bootstrap]          # → install.sh（mise がまだ無い Linux 機体）
mise = "2026.9.0"    # just は [tools].just をそのまま使う
```

- どの経路に配るかは生成器 `scripts/mise_versions.py` が持つ（`[tools]` の全件 → heredoc、`[tools].uv/just` + `[fetch]` の他 → tarball 定数、`[bootstrap]` → root `install.sh`）。この対応は生成器のコメントと plan に明記する。
- 今の heredoc にある説明コメント（npm backend の理由、quint のゲート、ADR 0040 の注記など）は、このファイルの該当箇所へ移す。

### 2. `scripts/mise_versions.py`（新規、生成器）

- `sync`: 1 の値から、次の領域を書き換えて commit 可能なテキストを出力する。
    - `.devcontainer/features/dotfiles-tools/install.sh` の `/etc/mise/config.toml` heredoc（**既存の `cat > … <<'EOF'` 〜 `EOF` の本体**を置き換える。新しい marker は発明しない。中身は生成ヘッダ + `[settings.npm]` + `[tools]` の有効な TOML）
    - 同 `UV_VERSION` / `JUST_VERSION` / `SHELDON_VERSION`（1 行ずつの置換）
    - `install.sh`（root）の `_mise_ver` / `_just_ver`（1 行ずつの置換）
- `--check`: 再生成して差分があれば非ゼロで終了（`--quiet` なしの既定で、どのファイルのどの領域がずれたかを出す）。
- 付随して **一覧と値の整合**を検査する（比較先を分ける。独立レビュー #1・#2）:
    - `[tools]` と **`[fetch]` の mise 道具**（`uv` / `just` / `aqua:rossmacarthur/sheldon`）の全キーが `config/mise/config.toml` に存在すること。`config/mise` が exact pin の道具は値も一致すること（今日の quint / golangci-lint / cf / sheldon がこの規則で守られる）。`sheldon` は host がインラインテーブル（`config/mise/config.toml:91`）なので `version` を取り出して比較する。
    - **`[bootstrap]` は host と比較しない**。`mise` は `config/mise/config.toml` の `[tools]` に無い（mise 自身は mise では入らない）ので、host への包含検査に含めると**正常な初期状態で落ちる**。`[bootstrap].mise` の比較先は root `install.sh` の `_mise_ver` だけにする。
- ネットワークは使わない。sheldon の per-arch SHA256 は **ハッシュであって版ではない**ので生成しない（新しい release に上げるときは、正本の版と一緒に install.sh の 2 行を更新する。この手順を正本のコメントに書く）。

#### 例外裁定: 生成器は Python

`ROOT_AGENTS.md` は「新しい services / CLIs / tools は Go」と定める。本件の生成器はこれに文字どおりは当たらないと判断し、**利用者の裁定（2026-10-21）を得て Python で書く**。理由:

- repo の中のファイルを書き換える**グルー**であって、配布する実行可能ツールではない（配布物ではないので「1 OS 1 バイナリ」の根拠が働かない）。`scripts/` の同類は既に Python で、`just` 経由で `uv run` する（`scripts/bump_tool.py` = 「全宣言を一括書換え + 拒否条件」は本件と同型）。
- TOML の読み書きが **標準ライブラリ（`tomllib`）**で済む。Go では TOML パーサの新規依存が必要で、「標準ライブラリ優先」の規約と衝突する。
- テストは既存の pytest 単位スイート（`tests/unit/`）に乗り、`just lint` / `just ci` の既存の Python 脚（ruff / ty）で検査される。

この裁定を ADR 0060 にも記録する。

### 3. `.devcontainer/features/dotfiles-tools/install.sh`

- heredoc の本体が生成物になり、先頭に「生成物。`just mise-versions-sync` が書く」のヘッダが入る。今 block 内にある説明コメントは正本 `config/mise/image-tools.toml` へ移す。
- 前後の散文も正本と検査を指すよう直す（feature の「この prebuild block が唯一の pin 記録。config/mise/config.toml と bump せよ／project config が優先し consistency test が守る」、root の `_just_ver` の「config/mise/config.toml の just と一緒に上げよ」）。後者の「project config が優先」は実測と違う（repo 内の `config/mise/config.toml` は project config として読まれない）ので、あわせて事実に合わせる。
- `UV_VERSION` / `JUST_VERSION` / `SHELDON_VERSION` の 3 行が生成物になる。
- **挙動の変更**: `UV_VERSION` 0.12.21 → 0.13.1、`JUST_VERSION` 1.58.0 → 1.59.0（mise 側の凍結版に合わせる）。実効版は PATH 順で元から mise 側だったため、画像の中身は「重複が一致する」方向に変わる（F3）。sheldon は 0.8.5 のまま。
- 検証付き取得の構造（sha256 sidecar / `gh attestation verify` / `SHA256SUMS` の grep）は変えない（F4 で新バージョンの URL が生きていることを確認済み）。

### 4. `install.sh`（root）

- `_mise_ver` / `_just_ver` が生成物になる。**挙動の変更**: `_just_ver` 1.58.0 → 1.59.0（bare Linux で just を先に入れる経路。F2 の不一致を消す）。

### 5. `justfile`

- `mise-versions-sync`（生成器の `sync`）と `mise-versions-check`（`--check`）を追加し、**`lint` と `check` の両方の脚に `mise-versions-check` を配線**する（F9。pre-commit は `lint`、`just check` / pre-push と `just ci` は `check` を通る。既存の `check_uv_exclude_newer.py` と同じ置き方）。

### 6. `tests/unit/test_mise_versions.py`（新規）

決定的・オフラインの検査。RED を先に取る。

- コミット済みの install.sh（2 ファイル）が生成器の出力と一致する（＝ drift が無い）。
- 生成器は **ずれを検出して非ゼロで終わる**（一時コピーを 1 文字変えて確認。検査器自身の検証）。
- `[tools]` と `[fetch]` の道具 ⊆ `config/mise/config.toml`、かつ `config/mise` の exact pin と値が一致する（インラインテーブルの `version` も取り出す）。
- **正常系**: host の `[tools]` に `mise` が無くても検査は通る（`[bootstrap].mise` の比較先は root `install.sh` の `_mise_ver` だけ）。
- 負例（検査器自身の検証）: (a) 正本の sheldon だけを変える、(b) `config/mise` の sheldon だけを変える、(c) install.sh の生成領域を 1 文字変える、(d) root `install.sh` の `_mise_ver` だけを変える — のそれぞれで `mise-versions-check` が非ゼロで終わること。
- 正本の中で **同じ道具の版が 2 回書かれていない**（`[tools]` と `[fetch]` / `[bootstrap]` の重複を許さない。これが「1 か所」の不変条件）。
- root `install.sh` / feature `install.sh` の定数が正本の値と一致する。
- 既存 5 テスト（F8）が読む形（heredoc が `tomllib` で読める、定数行が論理行として残る）が保たれている。

### 7. `docs/adr/0060-*.md`（裁定後 Accepted）と `docs/decision-queue.md`（裁定後は決定済みログ）、ADR 0006 の Status

ADR 0060 に、**維持する事項**と**置き換える事項**を明示する（独立レビュー #1 の指摘 4）。

- **維持する**: 画像は検証つき取得（SHA + attestation）を通す（ADR 0006 Decision 3 の前半）/ mise.lock を採らない（同 Strategy B の却下）/ `MISE_DATA_DIR=/opt/mise` の移設（同 Decision 4）/ 画像の `MISE_OFFLINE=1`（同 Decision 5）/ `config/mise/config.toml` が全 OS 共通の host 宣言であること / 生成器を Python にする例外裁定（上記）。
- **置き換える（すでに現行コードがそうなっている事実も含む。ADR 0006 の該当箇所を部分的に supersede する）**:
    - **Decision 1「`= "latest"` を全部 concrete pin にする」** → 実際の host は、ゲートと再現性が要る道具は exact、それ以外は `latest` / `lts` で真の最新を追う（この運用は 0006 の文面より後から定着した）。ADR 0060 はこの用途別方針を決定として書き、host と画像の世代差を別チャネルとして扱う。
    - **Decision 3「画像は `mise use --system` で検証済みバイナリを再利用する」** → 実際の画像は `/opt/mise` に**通常の `mise install` で別コピーを入れ、検証つき tarball と併存**する（`.devcontainer/features/dotfiles-tools/install.sh` に `mise use --system` は無い）。ADR 0060 はこの併存（version は生成で一致させる）を決定として書く。
    - **Decision 3 の「build-time check で image build を落とす」** → 実現の形を変える。正本からの**生成**で不一致をそもそも作れなくし、**コミット時（`just lint`）と CI（`just ci`）の drift 検査**で止める（画像ビルドまで待たない）。
    - 「3 OS で同一 pin」は **host の宣言についての主張**として維持し、画像の凍結世代は `config/mise/image-tools.toml` に記録する（同じ道具では値の一致を検査が強制する）。
- 裁定後、`docs-discipline.md` の規約どおり **ADR 0006 の Status 行だけ**を編集して部分置換を示す（既存の書き方: `Accepted; partly superseded by [0060](0060-...md) (Decision 1 の「全 concrete pin」と Decision 3 の system backend / build-time check の形)`）。本文は変えない。

利用者の PR コメントで裁定を受けて Accepted へ。

decision-queue の「決裁待ち」行（ADR 0051 の形式: ID / 何を決める / 種別 / 作者 / 決める人 / 期限 = 公開 PR）を 1 行追加し、裁定後に「決定済みログ」へ移す。

### 8. `README.md`

「構成」の正本の説明（`config/mise/config.toml (pins)`）を、host 用と画像用の 2 役に直す。

### 9. `docs/plan/mise-version-ssot.md`（本ファイル）

## 検証

- RED: 先に 6 のテストを走らせ、落ちることを失敗メッセージごと記録する（正本が無い / install.sh が生成物と違う）。
- GREEN: `just mise-versions-check` が緑、`just ci`（`check` を含む）が緑。
- 意味の等価: 生成後の heredoc を今日のものと比較し、**道具の集合と値が同じ**であることを記録する（変わるのは uv / just の 2 値と、コメント・markers）。
  併せて `tests/unit/test_sandbox_check_tools.py`・`test_go_tooling.py`・`test_devcontainer_download_retries.py`・`test_install_mise_bootstrap.py`・`test_mise_data_dir_relocation.py` が緑（`just ci` 内）。
- 負例: 正本の値を 1 つ変えて `just mise-versions-check` が落ちること、install.sh の定数を 1 つ変えても落ちることを記録する。加えて **pre-commit 段で止まること**を実測する: 生成領域を 1 文字変えた状態で `just lint`（pre-commit が呼ぶ実体）と `just check` の両方が非ゼロになることを記録する。
- 画像の実検証: 生成された tarball 定数（uv 0.13.1 / just 1.59.0）は画像ビルドで初めて実際に取得される。CI の `Run just tests in dev container` leg が唯一の実証なので、**PR の CI で緑を確認する**（ローカルに Docker があれば `just test`）。
- merge 後: host 側の設定は変わらないので `mise -C / install` は不要（宣言の集合も値も同じ）。必要なら `just doctor`。

## 対象外（今回やらない）

- ruff / ty（3 か所だが `just bump-tool` が一括で動かす既存機構がある。F11）。
- 画像が evaluator をビルドするための rustup 1.29.1 / rust 1.99.0 と quint evaluator v0.7.0（quint の release に従う build-time の道具で、host の rust とは役割が違う）。
- apt で入れる mise 本体（apt repo の現行版。固定は apt の pinning の話で、本件の正本は「mise が入れる道具」の版）。scoop / brew / GitHub Actions / plugin / skill の ref（lifecycle が違い、`dump` や Dependabot が動かす）。
- `dump/macbook/Brewfile` と `dump/harness/*.json`（実機の記録・別の lock 機構）。
- （前 PR から繰り越し）global gitignore への `.playwright-cli/` 追加。
- **生成器の Go 書き直し** — 所有者の希望（2026-10-21。「それは先の話」）。今回は repo のグルーとして Python + 例外で入れた（ADR 0060 の Neutral にも記録）。書き直すときは `scripts/mise_versions.py` を Go のツールに置き換え、`just lint` / `just check` の配線とテスト（現在は pytest）を移す。

## リスク / 未検証

- 生成器が 2 つの shell script に書き込む。生成領域を壊すと画像ビルドが落ちる（緩和: F8 の既存テスト + CI の devcontainer leg + `just check` の drift 検査）。
- `UV_VERSION` / `JUST_VERSION` の bump は、画像の `/usr/local/bin` の中身を変える。実効版は shim が勝つため変わらない見込みだが、**attestation / SHA 検証つき取得の新バージョンでの動作は画像ビルドでしか実証できない**（F4 は URL の存在確認まで）。
- 生成物であることを忘れて人が heredoc を直接編集すると、次の `just check` が落ちる（意図した挙動。block 内のコメントと plan に明記）。
- sheldon の SHA256 はオフラインで生成できないので、sheldon を上げるときは正本 1 行 + install.sh 2 行の更新になる（「版は 1 か所、ハッシュは取得の隣」という切り分け。正本のコメントに手順を書く）。
- Windows native / 他機体は未検証（本件は repo 内のファイルと生成器の話で、実行時に効くのは install.sh 経由のみ）。

## 裁定（2026-10-21）

所有者が本セッションで Accepted（「okです」）。Go への書き直しは将来の作業として「対象外」に記録した。ADR-0060 を Accepted に、decision-queue の行を決定済みログへ移し、ADR-0006 の Status 行だけを部分置換に更新した。

## レビュー

### #1（Codex `codex exec`、2026-10-21）— REVISE → 4 件すべて採用/裁定

- **指摘 1（P2、sheldon の片側 bump を検出できない）**: `[fetch]` の道具を整合検査の対象外にしていたので、host（`config/mise/config.toml:91` の aqua sheldon 0.8.5）だけを上げても素通りする。
  → **採用**。`[fetch]` / `[bootstrap]` も検査対象にし、インラインテーブルの `version` を取り出す。負例 (a)(b) をテストに追加。
- **指摘 2（P2、`check` 配線だけでは pre-commit で止まらない）**: pre-commit が呼ぶのは `just fmt` / `just lint` で、`just check` は pre-push 専用（かつ pre-push は既定で未インストール）。
  → **採用**。plan の F9 と配線先を実測で書き直し、`lint` と `check` の両方に配線する。**前 PR（#484）で「各 commit は `just check` 通過」と報告したのは誤りで、実際は `just lint`**。計画文書の誤りもここで訂正する。
- **指摘 3（P2、新規 Python 生成器は言語規約に反する）**: `ROOT_AGENTS.md` は新規 services / CLIs / tools を Go とする。
  → **利用者の裁定を得て Python + 例外記録**（上の「例外裁定」）。指摘が示した「実装前に明示的な例外裁定を plan に記録する」という道筋に従った。反論の根拠（標準ライブラリの TOML で済む、配布物ではない、既存グルーと同型、既存 pytest に乗る）は plan に残す。
- **指摘 4（P2、ADR 0006 の「履行」と「変更」の混同）**: 0006:170 の「3 OS で同一 pin」、同:180 の system backend と、本件の世代分離・二重取得の維持は同じではない。「§3 を果たす / 0006 は変えない」は不正確。
  → **採用**。ADR 0060 に「維持する事項 / 置き換える事項」を書き、裁定後は `docs-discipline.md` の規約どおり 0006 の Status 行だけを編集して後継を示す（部分置換の既存の書き方に合わせる）。

### #2（Codex `codex exec resume --last`、2026-10-21）— REVISE（残 2 件）→ 全件採用

- **指摘 1 の残件（`[bootstrap].mise` に比較できない host 条件を課していた）**: `config/mise/config.toml` の `[tools]` に `mise` は無い（実測: `^mise\b` の一致 0 件）ので、host 包含検査に含めると正常系で落ちる。
  → **採用**。比較先を分けた（`[tools]`+`[fetch]` → host、`[bootstrap].mise` → root `install.sh` の `_mise_ver`）。正常系（host に `mise` が無い）と負例 (d)（`_mise_ver` だけ変える）を追加。
- **指摘 4 の残件（ADR の置換対象に `system` backend と Decision 1 の全体 pin が抜けていた）**: ADR 0006 Decision 1 は「`= "latest"` を全部 concrete pin に」、Decision 3 は「`mise use --system` で検証済みバイナリを再利用」。現行の host は用途別方針で、画像は `mise use --system` を使っていない（実測: install.sh に一致 0 件、通常の `mise install` で `/opt/mise` に別コピー）。
  → **採用**。ADR 0060 の「置き換える」に、Decision 1 の全体 pin、Decision 3 の system backend、build-time check の形（生成 + コミット時/CI 検査に置換）を明記した。これらは**本件が導入する変更ではなく既にそうなっている事実**で、ADR 0060 が決定として記録する。

### #3（Codex `codex exec resume --last`、2026-10-21）— APPROVE

前回の残り 2 件（比較先の分離、ADR の置換範囲）の解消を確認。追加の修正必須事項なし（実装・テスト結果の承認は含まない、との留保つき）。

### 実装と gate（2026-10-21）

- RED → GREEN: `tests/unit/test_mise_versions.py` は sync 前に **3 failed / 9 passed**（drift 依存の 3 件だけ）、sync 後に **12 passed**。既存の install.sh 依存 5 テスト（26 tests）も緑（heredoc の形と定数行を壊していない = F8）。
- 生成の差分: `UV_VERSION` 0.12.21 → 0.13.1、`JUST_VERSION` 1.58.0 → 1.59.0、`_just_ver` 1.58.0 → 1.59.0。heredoc は道具の集合と値が同一（コメントが正本へ移り、生成ヘッダが付く）。
- `just lint`（pre-commit が呼ぶ実体）と `just ci` が緑（最終: `just ci` EXIT 0、unit 1726 passed / 33 skipped）。実装差分の独立レビューは #3 で APPROVE（それまでの指摘 4 件は全件採用、下記）。
- **自分の誤り 2 件（記録）**: (a) テストの `tmp_path / <絶対パス>` は pathlib の仕様で絶対パスのままになり、負例テストが**実ファイル（config/mise/config.toml・install.sh 2 本・正本）を書き換えた**（`git checkout` と正本の手修正で復旧）。原因の class を潰すため、テスト側に「相対パスだけ」「checkout の外へ出ない」「`str.replace` が空振りしたら失敗」の 3 assert を入れた（`tree()` / `mutate()`）。(b) 前 PR（#484）で「各 commit は `just check` 通過」と報告したのは誤り — pre-commit が呼ぶのは `just lint`。F9 とレビュー #2 に訂正済み。
- **差分レビュー #1（Codex）＝ REVISE（P2 ×2）→ 全件採用**（再現確認つき）:
    - 正本側に `latest` を書いても整合検査を通っていた（host が pin のまま画像だけ最新を取得できる）→ 正本の値は具体版のみ許可、host が pin なら厳密一致を要求。負例（quint を `latest`）を追加。
    - TOML の文字列をエスケープせず、引用符 / バックスラッシュを含む合法な入力から壊れた出力を作っていた（`rename_exe` に引用符を入れて再現）→ キーと値のエスケープを実装し、**書き込み前に生成 TOML を `tomllib` で読み直して正本と一致することを自己検査**。境界入力のテストを追加。
- **差分レビュー #2（Codex）＝ REVISE（P2 ×2）→ 全件採用**（再現確認つき）:
    - 「具体版」の判定が緩く、正本に `24` / `prefix:24` / 空文字を書いても通った（mise の request syntax は部分版を動く対象に解決する）→ full version（`X.Y.Z` + prerelease）だけを許可し、`[bootstrap]` にも適用。負例を追加。
    - インラインテーブル（例 `uv = { version = "0.13.1" }`）をシェル定数に辞書のまま書き出し、取得 URL が壊れた（`UV_VERSION="{'version': '0.13.1'}"` を再現）→ `concrete()` で version を取り出す形にし、テストを追加。
- **repo 自身の検査が捕まえた不備**: 初回の `just ci` は `tests/unit/test_text_io_encoding.py` で赤（`subprocess.run(text=True)` に `encoding=` を要求。1 failed / 1721 passed）。修正後に再実行。
