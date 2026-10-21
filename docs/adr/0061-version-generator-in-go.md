# 0061. 版本の生成器を Go にする（stdlib のみ、TOML サブセット + Python oracle）

**Date:** 2026-10-21
**Status:** Proposed
**ID:** ADR-0061
**Title:** 版本の生成器を Go にする（stdlib のみ、TOML サブセット + Python oracle）
**Decided-date:** —
**Decision-maker:** Hiroto N.
**Decision-maker-contact:** @hironow
**Author:** Pi（owner session）
**Author-contact:** @hironow
**Supersedes:** [ADR-0060](0060-frozen-image-generation-has-one-source.md) Decision 5、および Decision 2 の writer 実装・パス指定のみ。[ADR-0052](0052-renew-global-agent-instructions.md) Decision 1 のバイナリ配布要件について、本生成器だけ限定例外を提案
**Superseded-by:** none
**Related:** [ADR-0006](0006-mise-version-pinning.md)（画像の版管理）、[ADR-0025](0025-justfile-mise-tool-wrap.md)（mise 経由の実行）、[ADR-0044](0044-python-toolchain-uv-ruff-ty.md)（既存 Python テスト）、[ADR-0050](0050-pin-go-sources-to-lf.md)（Go ソースの改行）、[ADR-0051](0051-adopt-decision-queue-for-new-records.md)（公開 PR の裁定）、[ADR-0052](0052-renew-global-agent-instructions.md)（Go 優先）、[ADR-0060](0060-frozen-image-generation-has-one-source.md)（正本と生成領域）、[計画](../plan/mise-versions-go.md)
**Consultation-trace:** 所有者は本セッションで Go・標準ライブラリのみ・自作 TOML サブセット・Python の独立検証を選択。追加の整合相談で、0060 の正確な置換範囲と本生成器だけの `go run` 限定例外を承認し、今回の PR への代理記録を許可した。公開 PR の記録 URL を追記してから確定する

## やさしい説明

画像に入れる道具の版を、設定ファイルからインストール用スクリプトへ書き出す道具がある。
これまで Python だったこの道具を Go に移す。
版の正本、書き出す場所、版の一致検査は変えない。

Go の標準機能には、この設定形式（TOML）の読み取り機能がない。
外部のライブラリを増やさず、使う構文だけを読む小さな読み取り器を作る。
間違った読み取りを見逃さないよう、Python の標準読み取り器でも結果を検査する。

この道具はリポジトリの中でだけ使う。
端末別の実行ファイルを公開する代わりに、既存の `just` コマンドから `go run` で動かす。
他の Go ツールの配布規則は変えない。

## Context

- ADR-0060 Decision 2 は唯一の writer（生成物を書き換える道具）を `scripts/mise_versions.py` と指定し、Decision 5 は Python の例外を認めた。所有者は、その後この道具の Go 移植を指示した。
- ADR-0052 Decision 1 は新しいツールを Go とし、OS/CPU ごとのバイナリ配布も求める。既存の計画は `go run` を入口とするため、配布要件について本生成器だけの限定例外が必要である。
- Go には標準ライブラリの TOML パーサ（読み取り器）がない。所有者は外部依存を追加せず、必要な構文だけを自作し、残す Python テストを oracle（別実装による正解照合役）にする方式を選んだ。
- 正本は `config/mise/image-tools.toml`。host（ふだん使う端末）の設定は `config/mise/config.toml` の `[tools]` だけを読む。他の設定値は生成器の対象ではない。
- 重複キー、テーブル再定義、不正エスケープなどの構文不正は Python `tomllib` も拒否する。`node = "24"` は有効な TOML だが、完全な版ではないので生成器固有の意味検査で拒否する。両者は別の検査である。

## Decision

（Proposed。確定後にAcceptedのMUST/SHALL、Rejectedの理由、またはDeferredの再検討条件を記述。）

### 提案内容

1. 生成器を `tools/mise-versions/`（Go、標準ライブラリのみ）とする。`sync` / `check` と `--root` を維持する。既定 root はソースファイルの位置から解決し、cwd（起動時のディレクトリ）に依存させない。
2. 必要な TOML サブセットだけを読む。対象はコメント、テーブルヘッダ（表の見出し）、引用符なし・ありのキー、basic string（二重引用符の文字列）とエスケープ（特殊文字の表記）、インラインテーブル（行内の表）、文字列配列。対象内の不正構文と未知の構文を、行番号つきで拒否する。host は `[tools]` の範囲を検査する。
3. Go の単体テストと、CLI を駆動する Python `tomllib` の独立検証を残す。不正構文の試験は、版検査や生成物との差分ではなく、構文エラーによる拒否を確認する。検査・生成準備で失敗した `sync` は両出力を変更しない。ディスク書き込み障害に対する複数ファイルの原子的更新は保証しない。
4. 同一の入力に対する移植前後の生成バイトを比較する。生成ヘッダを据え置いた段階で一致を確認し、その後にコメントだけを Go のパスへ更新する。
5. `lint` と `check` は `just mise-versions-check` を呼ぶ。専用 recipe は `mise exec -- go run tools/mise-versions/main.go check|sync` を使う。本生成器だけは ADR-0052 Decision 1 の端末別バイナリ配布の例外とし、リポジトリ内で実行する。配布済みバイナリからの利用は対象外とする。

## Options Considered

| 案 | 利点 | コスト・リスク | 所有者の選択 |
| --- | --- | --- | --- |
| Go + 自作サブセット + Python の独立検証 | 外部依存なしで Go 優先に従える | パーサの保守と独立検証が必要 | 選択済み |
| Go + 外部 TOML ライブラリ | TOML 全仕様をライブラリに任せられる | 依存の例外裁定と更新管理が必要 | 標準ライブラリのみの裁定により不採用 |
| Python のまま | 標準 `tomllib` を使え、移植リスクがない | 言語例外が残る | Go 化の裁定により不採用 |
| Go を OS/CPU 別にビルドして配布 | ADR-0052 の配布規則に従う | 配布基盤と配布後の root 解決方式が必要 | 本生成器だけの `go run` 例外を所有者が選択 |

## Consequences

### Positive

- 生成器の外部依存はゼロで、既存の Go lint/test に入る。
- 自作読み取り器と Python `tomllib` を照合し、読み取りと書き出しの誤りを別実装から検出できる。
- 入口は既存の `just mise-versions-{check,sync}` のままにできる。

### Negative

- 自作パーサを保守する必要がある。構文を追加する際は Python 側の独立試験も追加する。
- 実行端末に Go が必要になる。端末別の実行ファイルは配らない。
- Go のビルドキャッシュがない初回は、コンパイルの待ち時間がある。

### Neutral

- 正本、生成対象、host の版との整合、画像の凍結版という ADR-0060 Decision 1/3/4/6 は維持する。
- ADR-0060 Decision 2 の唯一 writer と生成領域は維持し、実装・パス指定だけを変更する。
- 他の Python スクリプトと Go ツールの配布規則は変更しない。

## 反転記録 (Reversal)

- 旧: ADR-0060 Decision 5 の Python 指定、および Decision 2 の `scripts/mise_versions.py` 指定。
- 新: Go の `tools/mise-versions/` に変更する。唯一 writer、正本、生成領域、整合検査、凍結版の方針は反転しない。
- ADR-0052 Decision 1 の配布要件は本生成器だけ例外にする。他のツールには引き続き適用する。
- 元記録の決裁者・作者の連絡先はいずれも `@hironow`。所有者は本セッションで上記の正確な範囲と限定例外を選択し、今回の PR に代理記録することを許可した。公開 URL の記録前は Proposed を維持する。

## 他の DR との照合

独立 Codex レビューは全60件（0001〜0045、0047〜0061。0046 は存在せず、PDR なし）を読み、他の59件と矛盾・重複・誤読・偽の関連・関係誤認を比較した。
0060 の置換範囲不足、0052 の配布要件、関連参照の不足を検出した。
親も 0060 Decision 2/5 と 0052 Decision 1 の原文を確認し、所有者に追加相談した。
所有者は正確な置換範囲と本生成器だけの例外を承認した。
その他の Decision の衝突は検出していない。
確定前に公開 PR の裁定 URL と、修正後の再確認結果を追記する。

## 検証

- 段階 A: ヘッダ据え置きで既存の2出力の blob が一致（feature = `6031f9ae9642955066b95d0d06aa7197b3899ee9`、root = `8f89c6d635d956cfab8055e14d665240f5d3908a`）。これは既存入力に対する比較であり、全入力の互換性の証明ではない。
- 段階 B: install スクリプト2本の変更はコメント3行のみ。
- 計画レビュー #2 は APPROVE。実装レビュー #1 の6指摘、#2 の2指摘を修正し、親の回帰試験で拒否と受理の両面を確認した。最終再レビュー #3 は APPROVE（静的レビュー。テストは親が実行）。
- 修正後の targeted gate（`bd0ba4722`）は EXIT 0: Go lint 0 issues、Go テスト成功、Python oracle33件＋既存install依存26件 = 59 passed。native Windows 実機は未検証。
- 初回 `just ci` は Python テスト整形で EXIT 1。コード固定後の `just ci`（`bb427c485`）は EXIT 0、1743 passed / 33 skipped。新 Go module の lint/test と生成 drift 検査も含む。Docker sandbox の `just test` は実行中。
- 速度の単発計測: Python 版 2.07s / Go 版 2.12s（`mise exec` 込み、ビルドキャッシュあり）。一般的な性能同等性を保証する計測ではない。

## 決定（記入待ち）

決定者: Hiroto N.（@hironow）。決定日: —。

- [ ] 採択: 提案を確定し、公開裁定 URL を記録する。0060 と 0052 の Status 行だけに限定置換を記す。queue を決定済みへ移し、索引と変更ログを更新する。
- [ ] 差し戻し: 既存 ADR を維持し、指摘に応じて実装・提案を修正する。
- [ ] 却下: 既存実装を維持し、提案を Rejected にして理由と裁定 URL を記録する。
- [ ] 保留: 再検討条件を記録し、提案を Deferred にして裁定 URL を残す。
