# RTTMのPython検査を既存の規約に揃える

**Date:** 2026-10-22
**Status:** Implemented; local gates passed; PR CI pending
**Branch:** `chore/rttm-python-tooling`
**Related:** ADR 0044 / `ROOT_AGENTS_docs_agents_python-tooling.md`
**Blocking decisions:** なし。所有者はsession `01a159fd`でlint group・正確なpin・tyまで揃える方針を承認し、session `01a15f0e`で復帰を選択した。
**Graduates to:** `tools/rttm/README.md` と既存tooling文書。

## 現状と範囲

`tools/rttm` は既存Pythonで、Ruffが通常依存の範囲指定、tyが未導入、7日待機の例外もない。
root/emulatorはRuff 0.17.1とty 0.0.90を正確にpinし、両ツールを待機対象外にしている。
機能の追加・全面リファクタ・他依存の一括更新は行わない。
rootのRuff規則はrepo側例外のdefault + W605 + PTHを維持し、canonical selectへの変更は行わない。

## 実装と検証

1. rootのunit testでRTTMのlint group、rootと同一の正確なpin、待機例外、rootのjust経由の実検査への配線を固定する。`test_bump_tool.py`も4宣言/3 lock対応を検証し、先にREDを確認する。
2. RTTMのRuffを通常依存からlint groupへ移し、tyを同groupへ追加する。版は既存rootの0.17.1 / 0.0.90と揃える。pytestの配置やアプリ依存は変えない。`exclude-newer-package = { ruff = false, ty = false }` を追加し、他依存の7日待機は維持する。
3. `uv lock --project tools/rttm --upgrade-package ruff --upgrade-package ty` でlockを生成し、前後のpackage構造を比較する。他のpackageの非意図的な更新は戻して原因を調べ、lockを手で偽装しない。
4. RTTM固有の `[tool.ty.src] include` / `environment.extra-paths` / `terminal.error-on-warning` を定義し、親のscripts/tests限定設定を継承して検査対象が空になる問題を防ぐ。rootのjustfileにRTTMのfmt/lint/typecheck/checkを配線し、RTTM directoryをcwdとしてfrozenのlint groupのRuffと、通常依存も見えるgroup lintのtyを使う。checkにはRTTMの既存pytestも含め、root `just check`から実行する。RTTM側の行動テストで隔離projectへ同じjustfileとlockをコピーし、exactなtypecheck taskが正常な依存importを解決し、RTTM内の型エラーを拒否することを確認する。サブjustfileは作らない。
5. `scripts/bump_tool.py`と既存testsを4宣言/3 lockへ拡張し、将来のpin更新でRTTMが漏れるクラスの問題を防ぐ。更新前の全宣言読取り・異常時無書込みの契約を維持する。DependabotのRTTM entryもroot/emulatorと同じくRuff/tyをignoreし、独立bot更新によるpin分離を防ぐ。全同期projectで両toolのignoreがあることをunit testで確認する。
6. tyの診断は実コードか正確な型付けを直し、未解決importや診断を一律に無効化しない。必要な型依存が見つかったら標準/既存packageを先に調べ、追加の必要性を記録する。RTTMの既存機能は回帰testsで保つ。
7. RTTM READMEの開発手順とbump関連文書の宣言数を更新する。unit、RTTM検査、`just check` / `just ci`と独立差分レビューを行う。justfile配線変更のsandboxは対象headのfull CIをgateとし、所有者裁定どおり重いローカル実行は重複しない。
8. 署名commit、draft PR作成、ready化、対象headの全関連CI成功を確認後にsquash mergeし、mainをff-only更新する。mainは常にmainのまま、未保存の他者変更は保護する。

## 独立レビュー

Codex計画レビュー #1 はNEEDS_FIX（session `01a15f0e` の `rttm-plan-review.txt`）。2指摘を検証して採用した。

- P1: cwd変更だけではtyが親のroot設定を選んでRTTMを検査しない。親のty 0.0.90をRTTM cwdで実行し、rootの164 filesを調べてEXIT0になることを再現。step 4へlocal設定とexact taskの型エラー拒否テストを追加。
- P2: RTTMのDependabot entryだけRuff/ty ignoreがない。現行 `.github/dependabot.yaml` のroot/emulator/RTTM entryを照合して確認。step 5へ同期対象全件のbot更新抑止とunit invariantを追加。

独立Codex差分レビューはAPPROVE（session `01a15f0e` の `rttm-diff-review.txt`）。両指摘の修正、4宣言/3 lock、Windowsのpath引用を確認した。review sandboxでuvのcache lockが作れず、pytest成功はreviewer自身は主張していない。

## 実装結果

- 先に追加unit testsの10 failed / 7 passedを確認し、修正後は17 passed。RTTMはRuff/tyと7 testsが成功し、隔離projectでexactなroot taskが依存importを解決し、RTTM内の型エラーを拒否した。
- root `just ci` はEXIT0。root unit 1760 passed / 33 skipped、Tofu 4 passed、Semgrep fixturesなどが成功。RTTMもroot check経由で実行した。
- tyの初回実行で不要な既存 `type: ignore` を検出したため、そのコメントだけ削除した。新unit testのOptional regex matchの型エラーも、match存在のassertを追加して解消した。
- lock前後のpackage recordsはRTTM metadata、Ruff 0.17.0→0.17.1、ty 0.0.90追加だけが変化。他packageは完全一致。lock revision 3→5と両toolの待機例外はuv生成。Ruff/tyの全archive URL/hash/sizeは採用済みroot lockと一致。
- Windowsの実機実行は未確認。justfile配線を含む最終headのsandbox CIをmerge gateにし、ローカルDockerの重複実行はしない。
- 最終local gateとreview後の追加差分は、この結果と既存文書の宣言数コメント訂正だけ。
