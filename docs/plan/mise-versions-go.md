# 版本の生成器を Python から Go へ移植する（stdlib のみ + Python を oracle に）

**Date:** 2026-10-21
**Status:** Verified（[PR #486](https://github.com/hironow/dotfiles/pull/486)。Go 実装・独立レビュー・ローカル全 gate / sandbox 成功。最終記録の CI 成功後に squash merge）
**Branch:** `refactor/mise-versions-go`
**Related:** [ADR-0060](../adr/0060-frozen-image-generation-has-one-source.md)（Decision 5 と Decision 2 の writer 指定を置換 → ADR-0061）、[ADR-0052](../adr/0052-renew-global-agent-instructions.md)（本生成器だけ go run の配布例外）/ `ROOT_AGENTS_docs_agents_go-tooling.md`（stdlib 優先・サードパーティ module には platform reason）/ `ROOT_AGENTS_docs_agents_dependency-policy.md` / 前段: PR #485（版本の SSOT 化）
**Blocking decisions:** なし（利用者に 2026-10-21 に確認済み: **Go は stdlib のみ**、TOML は**必要な部分だけの自作パーサ**、正しさは**残す Python テストを oracle（`tomllib`）にして独立検証**）
**Graduates to:** ADR-0061（Proposed、利用者の裁定で Accepted）。安定後 done。

## 目的

PR #485 で入れた版本の生成器は `scripts/mise_versions.py`（Python、`tomllib` は標準ライブラリ）。ADR-0060 Decision 5 はこれを「言語規約（新しい tools は Go）の例外」として記録し、所有者は「将来 Go で書き直したい」と述べた。

本件はその移植を行う。**挙動は変えない**（同じ CLI、同じ生成物、同じ検査）。移植の正しさは 2 つで担保する: (a) Go 側の単体テスト、(b) 残す Python テストを **oracle** として、`tomllib` で独立に生成物を検証する。加えて **移植前後で `install.sh` 2 本がバイト一致**することを記録する。

## 確定させた事実（一次情報で確認済み）

- **F1**: 現行の生成器は `scripts/mise_versions.py`（Python、stdlib `tomllib`）。`just lint`（pre-commit）と `just check` / `just ci` から `{{UV_RUN}} scripts/mise_versions.py check` として呼ばれ、`just mise-versions-sync` が `sync` を呼ぶ。生成対象は 5 領域: `/etc/mise/config.toml` heredoc の本体、`UV_VERSION` / `JUST_VERSION` / `SHELDON_VERSION`、root `install.sh` の `_mise_ver` / `_just_ver`。
- **F2**: Go module の規約は `tools/<name>/`（`tools/simple-server/` の前例: `go.mod` + `main.go` + `main_test.go` + `README.md` + 空の `go.sum`）、`module <name>` / `go 1.27`。リポジトリ直下の `.golangci.yaml` を `--config` で共有し、`just go-lint`（`golangci-lint run` + `fmt --diff`）と `just go-test`（`go test -short ./...`）が `*go.mod` を自動で拾う。`.golangci.yaml` は gofumpt のみを formatter にし、gocyclo / gosec / revive 等を有効にする（関数は小さく保つ必要がある）。
- **F3**: `go-tooling` spoke は「標準ライブラリ優先。サードパーティ module は platform reason（Cloud client / プロトコル SDK）が必要」と定める。Go の標準ライブラリに TOML パーサは無いので、**必要なサブセットだけを読む自作パーサ**を書く（利用者の裁定）。未知の構文は**エラーにする**（黙って誤読しない）。
- **F4**: 必要な TOML の形は限られる。`config/mise/image-tools.toml`（自前・小）: コメント、`[settings.npm]`、`[tools]`（文字列と 1 つのインラインテーブル）、`[fetch]`（文字列配列 `mise_tools` と文字列）、`[bootstrap]`。`config/mise/config.toml`（大きく手書き）: `[tools]` の各キーが文字列 or インラインテーブル（`{ version = "...", os = [...], ... }`）。引用符つきキー（`"npm:cf"`）が双方にある。
- **F5**: 現行の検査は 4 種: (a) 生成物とコミット済みファイルの一致（drift）、(b) host 整合（`[tools]` と `[fetch]` の道具が `config/mise/config.toml` にあり、host が exact pin なら値も一致。`[bootstrap].mise` は host に無いので `install.sh` の `_mise_ver` とだけ比較）、(c) 正本の値は full version（`X.Y.Z` + prerelease）のみ、(d) 生成 TOML の round-trip。加えて「同じ版を 2 か所に書かない」構造検査。
- **F6**: 現行テストは `tests/unit/test_mise_versions.py`（16 件）。うち 3 件は drift に依存し、片側変更 4 種（正本だけ / host だけ / 生成領域 / `_mise_ver`）の検出と冪等性を含む。既存の `install.sh` 依存テスト 5 本（26 件。`test_sandbox_check_tools` / `test_go_tooling` / `test_devcontainer_download_retries` / `test_install_mise_bootstrap` / `test_mise_data_dir_relocation`）が heredoc と定数行の形を守っている。
- **F7**: 単一ファイルの Go プログラムは module の外から `go run tools/<name>/main.go ...`（file mode）で走る（`justfile` の `tools/simple-server/main.go` の前例）。複数ファイルにするなら `cd tools/<name> && go run .` が要る。
- **F8**: 移植前の基準バイト（等価性検証に使う）: `.devcontainer/features/dotfiles-tools/install.sh` = `6031f9ae9642955066b95d0d06aa7197b3899ee9`、`install.sh` = `8f89c6d635d956cfab8055e14d665240f5d3908a`（`git hash-object`）。

## 変更内容

### 1. `tools/mise-versions/`（新規 Go module、stdlib のみ）

- `main.go`（単一ファイル。F7 の file mode を保ち、`justfile` から `go run tools/mise-versions/main.go …` で呼べるようにする）:
    - CLI: `mise-versions sync|check [--root DIR]`。**既定 root は現行と同じく「実行されているソースの場所から解決した checkout」**（`runtime.Caller(0)` で `tools/mise-versions/main.go` を知り 2 つ上へ。`--root` が明示されればそちらが勝つ。現行は `Path(__file__).resolve().parents[1]` なので、規則を互換に保つ）。終了コードと出力は現行に合わせる（`check` は drift を報告して非ゼロ、`sync` は書いたファイルを列挙）。
    - TOML サブセットリーダ: コメント / 空行 / テーブルヘッダ / bare・quoted キー / basic string（`\"` `\\` `\n` `\r` `\t` `\uXXXX` のエスケープ解決）/ インラインテーブル / 文字列配列。**未知の構文は行番号つきでエラー**。
    - 生成: 現行と同じ順序・同じエスケープ（キーは必要時のみ引用、値はエスケープ）で heredoc 本体と 5 つの定数を書く。書く前に、生成した TOML を**同じパーサで読み直して正本と一致することを自己検査**する。
    - 検査: F5 の 4 種 + 構造検査。host config の `[tools]` は必要なキーだけを読む（未知の形は F4 の範囲で解釈し、解釈できないキーはエラー）。**全検査を通ってから書く**（失敗した `sync` は 2 ファイルのどちらも書き換えない、を保存）。
- `main_test.go`: パーサの境界（引用符・エスケープ・インラインテーブル・配列・コメント・未知構文の拒否）、生成の round-trip、片側変更 4 種の検出、冪等性、`--root` での一時ツリー。
- `README.md`（`tools/simple-server/README.md` に倣う）: 何をする道具か、`sync` / `check` の使い方、正本は `config/mise/image-tools.toml`、検査は `just lint` / `just check` に入っていること。
- `go.mod`（`module mise-versions` / `go 1.27`）と空の `go.sum`（依存ゼロ）。

### 2. `tests/unit/test_mise_versions.py` — **oracle に書き換え**

生成器の内部を import するのをやめ、**CLI として呼ぶ**。検証は `tomllib` で独立に行う（Go のパーサの正しさを、別実装で確かめる）。

- コミット済み `install.sh` 2 本が `check` で drift なし。
- 生成された heredoc が `tomllib` で読めて、正本の `settings` / `tools` と**完全一致**（＝エスケープと直列化の oracle）。
- 5 つの定数が正本の値と一致。
- host 整合（`[tools]` / `[fetch]` ⊆ host、exact pin の一致、`[bootstrap].mise` は `_mise_ver` とのみ比較）を `tomllib` で独立に計算して一致。
- 片側変更 4 種（一時ツリー）で `check` が非ゼロ。
- 「同じ版を 2 か所に書かない」構造検査。

### 3. `justfile`

- `lint`（今は `{{UV_RUN}} scripts/mise_versions.py check` を直に呼んでいる）と `check` の脚を **`just mise-versions-check` の呼び出しに統一**する（実装は recipe 1 箇所に集約し、削除後に脚が壊れないようにする）。`mise-versions-check` / `mise-versions-sync` の実体を Go に差し替える（`mise exec -- go run tools/mise-versions/main.go check` / `… sync`）。配線先（`lint` と `check`）は変えない。

### 4. `scripts/mise_versions.py` を削除

### 5. `docs/adr/0061-*.md`（Proposed）+ `docs/adr/README.md` + `docs/decision-queue.md`

「生成器は Go（stdlib のみ、TOML は自作サブセット + Python oracle）」。追加整合相談で所有者が承認した範囲は ADR-0060 Decision 5 と Decision 2 の writer 実装・パス指定、および ADR-0052 Decision 1 の本生成器だけの配布例外（`go run`）。公開 PR に裁定を代理記録した後、旧 ADR 2 本の **Status 行だけ**を部分置換に更新する。本文は変えない。

### 6. `docs/plan/mise-versions-go.md`（本ファイル）

## 検証

- **移植の等価性（2 段階で取る。指摘 #4 に対応）**:
    - **段階 A（ヘッダ据え置き）**: Go 版が現行と**同一の生成ヘッダ文字列**を出力する状態で `sync` を走らせ、`install.sh` 2 本が F8 のブロブと**バイト一致**することを記録する（移植が意味を変えていないことの証明）。
    - **段階 B（コメント更新）**: 生成ヘッダと周辺の散文（`install.sh` の `_just_ver` の上の注記、feature の prebuild 説明、生成ヘッダ内の `GENERATED by …`）を Go の道具名（`tools/mise-versions/main.go`）に更新する。差分が**コメント行だけ**であることを diff で示す（生成される TOML と定数の値は不変）。ADR / plan の履歴記述は更新対象にしない（過去の記録）。
- **RED → GREEN**: Go テストを先に書き、未実装で落ちることを記録 → 実装。oracle テストも同様。
- **oracle（Python + `tomllib`）— 受理する構文と拒否の比較（指摘 #2 に対応）**:
    - 生成された heredoc が `tomllib` で読めて、正本の `settings` / `tools` と**完全一致**。
    - 5 つの定数が正本の値と一致。
    - **境界入力（CLI 経由）**: 引用符・バックスラッシュを含む値（例 `rename_exe`）を正本に入れて `sync` → `tomllib` で読み直して正本と一致。インラインテーブルの道具（例 `uv = { version = "0.13.1" }`）→ `UV_VERSION="0.13.1"`。
    - **不正入力は Go も `tomllib` も拒否する**: 重複キー / テーブル再定義 / 不正なエスケープを正本に入れ、`check` が非ゼロで終わること、かつ Python 側で `tomllib` もその入力を拒否することを確認。**失敗した `sync` は 2 ファイルのどちらも書き換えない**（現行の validate-first を保存）。
    - 片側変更 4 種（正本だけ / host だけ / 生成領域 / `_mise_ver`）で `check` が非ゼロ。
    - 「同じ版を 2 か所に書かない」構造検査。
    - **既定 root の互換（指摘 #3 に対応）**: 別ディレクトリ（例 `/tmp`）から起動しても checkout を対象にすること、`--root` が明示されればそちらが優先されること。
- `just go-lint`（`golangci-lint run` + `fmt --diff`）/ `just go-test` / `just ci`（EXIT 0。`lint` と `check` の新しい脚を含む）。`go run` の実行時間も実測して記録する（pre-commit に載るため）。
- 既存の `install.sh` 依存 5 テスト（26 件）が緑のまま。
- 削除後、`scripts/mise_versions.py` を参照する箇所が**実行コードと現行説明に残っていない**（`grep`。ADR / plan の履歴記述は対象外）。

## 対象外（今回やらない）

- 他の Python グルー（`scripts/bump_tool.py`、`scripts/check_*.py`、`scripts/skills_lock.py` など）の Go 化。同じ論点だが本件の対象ではない。
- TOML の全仕様サポート（必要なサブセットのみ。未知はエラーにして、必要になったら足す）。
- `tools/rttm` の ruff 0.17.0 → 0.17.1（別 item）。
- `docs/handover.md` の更新（別 item）。

## リスク / 未検証

- **自作パーサの誤読**が最大のリスク。緩和: (a) 未知の構文は失敗、(b) `tomllib` による oracle テスト（生成物と host 整合を別実装で再計算）、(c) 移植前後のバイト一致。
- `go run` は毎回コンパイルする（ビルドキャッシュで実測 ~0.3s 程度の見込み）。pre-commit の `just lint` に載るので、実測して遅ければビルド済みバイナリの再利用を検討する（本 plan の検証で計測する）。
- Go module が 1 つ増える（`go.sum` は空 = 依存ゼロ）。Dependabot の Go group に面が増えるが、依存が無ければ PR は生まれない見込み。
- Windows native: `go run` のパス区切りと、`--root` の解決を Go 側で `filepath` を使って扱う。実機検証はしない（tests/unit は native Windows でも通る前提を保つ）。

## レビュー

### #1（Codex `codex exec`、2026-10-21）— REVISE → 4 件すべて採用

- **指摘 1（P1、recipe 差し替えだけでは `lint` / `check` が壊れる）**: 現行の `lint` と `check` は `{{UV_RUN}} scripts/mise_versions.py check` を直に呼んでおり（実測: justfile の 4 箇所）、削除後は失敗する。
  → **採用**。「`lint` / `check` の脚を `just mise-versions-check` に統一し、実装を recipe 1 箇所に集約」を変更内容に明記した。
- **指摘 2（P1、oracle の検証対象が不足）**: コミット済みデータの比較だけでは、通常入力しか処理できない実装や、不正入力を受理して drift で落ちる実装を排除できない。
  → **採用**。境界入力（エスケープ / インラインテーブル）を CLI 経由で残し、重複キー / テーブル再定義 / 不正エスケープは Go と `tomllib` の**両方の拒否**を比較、失敗した `sync` が何も書かないことまで検証項目に入れた。
- **指摘 3（P2、既定 root の非互換）**: 現行は `Path(__file__).resolve().parents[1]`（スクリプト所在の checkout）、plan は cwd と書いていた。
  → **採用**。`runtime.Caller(0)` から checkout を解決する互換規則にし、`--root` の優先と「別ディレクトリからの起動」を受入テストに追加した。
- **指摘 4（P2、バイト一致と旧パス除去の両立不能）**: 生成ヘッダ自身が `scripts/mise_versions.py` を含むため、バイト一致を保ったまま旧パスを消せない。
  → **採用**。検証を 2 段階に分けた（段階 A: ヘッダ据え置きでバイト一致 → 段階 B: コメント行のみ更新、diff で明示）。旧パス検索の対象を実行コードと現行説明に限定し、ADR / plan の履歴は除外する。

### #2（Codex `codex exec resume --last`、2026-10-21）— APPROVE

前回の 4 件の解消を現行コードと再照合して確認。追加の修正必須事項なし（計画への承認）。

### 実装と gate（2026-10-21）

- **段階 A（等価性）**: 生成ヘッダを据え置いた Go 版で `check` = `up to date`、`sync` は書き込みなし。`git hash-object` が移植前と一致（`.devcontainer/…/install.sh` = `6031f9ae…`、`install.sh` = `8f89c6d6…`）。
- **段階 B**: ヘッダと散文を Go の道具名（`tools/mise-versions/main.go`）に更新。`sync` 後の差分は**コメント 3 行のみ**（`git diff` で確認。生成される TOML と定数の値は不変）。旧パスは justfile 4 箇所（→ recipe 呼び出しと Go 起動）と散文 2 箇所を更新し、実行コード / 現行説明に残っていない。
- **RED → GREEN**: Go は最初の `go test` が「未実装の参照」でビルド不能（RED）→ 実装後に緑。oracle（Python）は CLI 駆動に書き換えて **17 passed**。
- **lint**: `golangci-lint run` = **0 issues**（gofumpt 整形、および gosec G115 の rune 変換・perfsprint・struct 整形の 3 件を修正）。`go test -short` も緑。
- **速度**: `check` は Python 版 **2.07s** / Go 版 **2.12s**（`mise exec` 込み、warm）。cold ビルドは 1 回 **+9s**（go run）。
- 削除: `scripts/mise_versions.py`（`git rm`）。
- `just ci` 初回: **EXIT 1**（Python oracle テストの整形）。ラッパーが成功終了して通知は exit 0 だったが、内側の EXIT 1 が実結果。整形を修正し、再実行は内側の終了コードをそのまま返す。
- 再実行 `bc90261c6`: **EXIT 0**。修正作業と時間が重なったため、最終版の保証には使わず、修正完了後にもう一度実行する。

### 実装レビュー #1 — REVISE（6 件）

1. Windows の `write_text` が CRLF に変換する → `newline="\n"` を指定し、変更後の LF を byte で検査。実行ファイルの `.exe` 名も明示。native Windows の実機実行は未確認。
2. 配列の空要素・インラインテーブルの不正カンマを受理する → 親が一時コピーで再現（`tomllib` は拒否、Go `sync` は EXIT 0）。空要素を拒否し、配列の末尾カンマだけは許可する。
3. インラインテーブルをヘッダで再定義・拡張できる → 親が再現（同上）。閉じたテーブルとして追記を拒否する。
4. basic string の生制御文字・不正 UTF-8 を受理する → 生 0x01 の受理を親が再現。文字列の制御文字と入力の UTF-8 を検査する。
5. host の `[tools]` 再定義が抽出時に消える → 親が再現（同上）。ヘッダと元の行番号を維持して解析し、重複を拒否する。
6. oracle の不正入力が、後段の版検査や drift で落ちても成功扱いになる → コードで確認。同値の重複キー・版以外のメタデータへの不正 escape に変更。`check` / `sync` の両方で構文エラーの行番号と、2 出力それぞれの byte 不変を要求する。

上記に加え、ヘッダ内の空白正規化と不正ヘッダの拒否を回帰試験にした。新 Go テストは修正前に11構文ケースとhostヘッダ重複で失敗を観測した。

### ADR 整合レビュー #1

Codex は全60件を読み、他59件を5カテゴリで比較。0060 Decision 2 の writer 指定も置換対象であること、0052 の配布要件、関連参照の不足を指摘。親も原文を照合し、所有者は正確な置換範囲と本生成器だけの `go run` 限定例外を承認、今回の PR への代理記録を許可した。

部分バージョンは有効な TOML であることを明記し、構文検査と版の意味検査を分離した。Proposed の形式、反転記録、代案、未裁定の状態を整えた。初回 rubric は R1〜R10 = 1/1/1/2/2/1/1/1/1/0（11/20）。再確認と公開裁定記録の前には確定しない。

### 実装レビュー #2 — REVISE（2 件）

- host の対象外ヘッダ（引用つき・深い表）にもサブセット制限を課していた → 対象の先頭成分が `tools` かの判定と、対象ヘッダの厳密検査を分離した。
- `TrimSpace` が TOML で不正な NBSP / VT / FF も消していた → space / tab だけを取り除く関数へ統一。CRLF は別途正規化し、生の制御文字はコメント内も拒否する。

親の CLI oracle で修正前に **5 failed**（不正空白3件、対象外ヘッダ2件）を観測。修正後 `bd0ba4722` は **EXIT 0**: Go lint **0 issues**、Go テスト成功、oracle33件＋既存install依存26件 = **59 passed**。Windows 実機は未検証。

ADR 再採点は 17/20（1/2/2/2/2/2/1/2/2/1）。不足の日本語説明を追加。公開裁定 URL 待ちの R1/R10 は未確定のまま維持する。

### 最終レビュー・gate

- Codex 実装レビュー #3 (`be886bb5b`): **APPROVE**。残り2指摘の解消と、ADRの正確な限定範囲を静的に確認した。テストを独立実行したという意味ではない。
- コード固定後 `just ci` (`bb427c485`): **EXIT 0、1743 passed / 33 skipped**。新 module の Go lint/test と生成 drift 検査を含む。
- 新 ADR・plan・queue・索引の相対 Markdown リンクを親が実在確認し、0025/0050 の誤パスを修正した。
- `just test` 初回は image build 成功後に40分上限で timeout（テスト29%、assertion failure なし）。最新 commit で再実行 `b03506cfd`: **EXIT 0、126 passed / skipなし、2389.66s**。
- [PR CI](https://github.com/hironow/dotfiles/actions/runs/39590732935) は `bde7401` で全6チェック成功。CI sandbox の実ログも **126 passed / skipなし**。最終記録だけの commit 後、最新 SHA の全 CI をもう一度確認する。
- ADR の filing 再評価（親）: R1〜R10 = 1/2/2/2/2/2/2/2/2/1（18/20）。公開裁定 URL 記録前なので確定しない。
- 所有者の許可に基づく [PR #486 の代理裁定記録](https://github.com/hironow/dotfiles/pull/486#issuecomment-6314535355)を API でも本文・URL 照合した。0061 を Accepted にし、0060/0052 は Status 行だけ更新、queue と索引を同期した。採択時 rubric（親）: R1〜R10 はすべて2（20/20）。根拠は公開裁定、独立レビュー、相互参照と不変性検査。
- 別 follow-up の `tools/rttm` Ruff は 0.17.0 を維持。2026-10-21T12:22:27 UTC に PyPI を再確認し、0.17.1 公開が 2026-10-15T15:22:33.667796 UTC、7日経過は 2026-10-22T15:22:33.667796 UTC と確認。隔離期間を緩めない。
