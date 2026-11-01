# ty 0.0.90 と cf beta.20 の宣言を揃える

**Date:** 2026-10-21
**Status:** done。[#487](https://github.com/hironow/dotfiles/pull/487) で merge（main `9508e5c3`）。版を上げただけで、移す説明はない（cf の固定の方針は `config/mise/config.toml` のコメント）
**Scope:** dotfiles のみ。Go 移植 PR #486 の後に別 worktree と別 PR で実施する。

## 所有者の依頼と現状

所有者は main の未コミット変更（ty 0.0.90 と cf 1.0.0-beta.20）も採用対象とし、changelog を読むよう指示した。
main は常に main のままにする。
現在の main 差分は `config/mise/config.toml` の2行だけで、`/tmp/dotfiles-live-ty-cf-2026-10-21.patch` に退避済み。
リポジトリでは、ty の root/emulator 宣言と lock はまだ0.0.89、image の cf はまだbeta.18である。
既存 Python 生成器の check も cf の host/image 不一致で EXIT 1 になる。

## 公式 changelog と影響

### ty 0.0.90

[公式 release](https://github.com/astral-sh/ty/releases/tag/0.0.90)（公開2026-10-20）。
[release API](https://api.github.com/repos/astral-sh/ty/releases/tags/0.0.90)の本文を取得して確認した。

- 再帰 alias の否定による crash と、再帰 descriptor setter の stack overflow を修正。
- hashability 復元、constructor 型変数の default、bound receiver、dynamic attribute の読み取り型を修正。
- non-protocol への runtime_checkable と TypeAliasType の keyword を検査する。
- TypedDict の read-only key の削除、pop、setdefault を報告する。
- LSP の return-type inlay hint を追加し、stub-only 型の hint 挿入を避ける。
- uv の nested module ownership metadata に対応し、macOS の署名識別子を安定化する。

この repo では新診断が出ないか root/emulator の `ty check` を含む gate で確認する。
既存の `exclude-newer-package = { ruff = false, ty = false }` により ty は7日待機の対象外である。
隔離設定自体は変更しない。

### cf 1.0.0-beta.18 → beta.20

[公式 CHANGELOG](https://github.com/cloudflare/cf/blob/main/packages/cli/CHANGELOG.md)のbeta.19とbeta.20を確認した。
取得時のblobは `fcdcde11d4f068ec1c8e4d3f3bbc1165ed4f1222`。
[npm公式metadata](https://registry.npmjs.org/cf)でもversion、公開日時、enginesとrepositoryを確認した。

- beta.19: OAuthのkeyring保存設定を永続化するflagsを追加。composed scalar、nested object array、bodyless raw-responseのheader flagsなどの生成を修正。
- beta.20: 手書きのauth/telemetry/migrateコマンドのnotice、warning、successをstderrへ移す（breaking change）。stdoutをparseする外部利用者には影響がある。
- beta.20: Node.js要件を `^22.23.0 || ^24.22.0 || ^26.12.0` に限定する（breaking change）。host実測とimage pinはともに24.22.0なので要件を満たす。
- beta.20: `--temporary-account`を追加。help、auth check、dry runではaccountを作らないと記載。今回これらのaccount機能は使わない。
- Workers SDK由来の依存と生成コマンド群も更新する。
- npm `latest` は取得時点でbeta.20。既存コメントの「latestはbeta.10」は古い。ただし今回の作業では固定beta pinという既存方針を維持し、`latest`への切替はしない。

repoのscripts/tools/workflows/testsを調べた範囲ではcfコマンドのstdoutをparseする実行箇所は見つからず、見つかったのは旧生成器の説明のみだった。
確認範囲外の外部repoの利用は未検証とする。

## 変更

1. #486を最新SHAの全CI成功後にsquash mergeする。mainの2行は保持したまま進め、別worktreeを更新後のorigin/mainから作る。
2. 新worktreeのclean baselineでGo checkがEXIT0であることを確認する。退避した2行patchを `git apply --check` 後に適用し、Go checkがcfのbeta.18/beta.20不一致という診断でEXIT1になることを確認する。単なる非ゼロはREDの証拠にしない。その後 `just bump-tool ty 0.0.90` を使い、host/root/emulatorの3宣言と2 lockを揃える。lock差分を検査し、ty以外が動いたら原因を確認して対象外の更新を分離する。
3. hostのcf pinと `config/mise/image-tools.toml` のcf pinをbeta.20にし、Go生成器の `just mise-versions-sync` でheredocを再生成する。generated blockを手で編集しない。hostコメントは古いdist-tag説明を外し、固定beta pinの維持と正本の場所を記す。
4. drift検査は clean EXIT0 → 退避2行を適用してcf不一致のEXIT1 → 残りの宣言とlock更新と生成でEXIT0 の順にする。既存pin/bump/oracle/install依存テストを使う。今回のfixtureに旧cf versionを仮定する箇所があれば、新しい宣言値からの確認へ直すが、検査は弱めない。
5. `just ci`（Go lint/test、root/emulator tyを含む）を実行する。install scriptのgenerated値が変わるため `just test` も実行する。予算は初回imagebuild+126testsの実測を踏まえ90分にする。
6. Codexの独立差分レビュー、署名commit、非draft PR、全CI成功後にsquash mergeする。
7. PR merge後のmain取り込みは、次の限定手順で行う。生きたty/cfの値を旧版へ一時的にも戻さず、stash/resetは使わない。
    - PRの採用先SHAをAPIで取得し、fetch後のorigin/mainに含まれること、mainが分岐していないことを確認する。
    - mainのstaged差分が空で、未コミット差分が退避patchの2行とbyte単位で同じであることを確認する。増減があれば停止する。
    - 採用先のconfig blobがレビュー済みPRのconfig blobと完全一致し、ty/cf以外の設定値が変わっていないことを独立にtomllibで比較する。コメントはPRで承認した修正だけとする。
    - 現在のmainのconfigを別途退避してhash確認後、採用先のconfig blobをそのファイルだけへ反映する。ty/cfの値は既に同じなので旧版への切替は起きない。直前に現差分を再確認し、不一致なら書かない。
    - そのファイルだけ `git add -- config/mise/config.toml` し、index blobが採用先blobに一致し、他のstaged差分が無いことを確認して `git merge --ff-only origin/main` を行う。HEADとindexとworking fileが一致し、退避2行が取り込まれたことを確認する。
    - 拒否されたら停止し、追加のreset/restoreを行わない。退避は保持する。
8. mainのGo drift check、tyのpin/lock整合、cfとNodeのversion/helpだけのsmokeを行う。必要なinstallは承認済みversionだけをmise経由で行い、認証、account作成、deploy、公開は行わない。
9. scoped handoverを更新する（元ファイル退避と範囲は既に所有者承認済み）。

## 対象外と停止条件

- Ruff 0.17.1のrttm採用は2026-10-22T15:22:33.667796 UTCまで待機。規則の変更はしない。
- 他repo、skills、既存ADR本文、miseの隔離設定、cfの自動追従方針は変更しない。
- 新tyが既存コードに診断を出した場合、まず内容を報告する。ruleの無効化で通さない。
- cfを使う認証やネットワーク変更の試験はしない。smokeはversion/helpに限定する。
- mainの2行以外に変更があれば退避と作業範囲を再確認する。

## 計画レビュー #1 の確認

- mainの未コミット差分を残したままffすると失敗するという指摘を採用。親が一時Git repoで再現し、working fileを採用先と同一にしただけでもEXIT1と確認した。indexも同一blobにすると `git merge --ff-only` がEXIT0で完了し、working file不変、status cleanになることを確認した。したがって取り込みはPRで採用済みの1ファイルだけをindexへ揃える手順とし、生きたpinを旧版へ戻す操作を避ける。
- 新worktreeにはdirty差分が移らないという指摘を採用。生成器は同じworktreeのhost configを読むので、clean baselineのEXIT0、patch適用後のcf診断EXIT1、全更新後のEXIT0の三段階に修正した。

## 計画レビュー #2

Codex `bdeee4ab5` は2指摘の解消を実ファイルと再照合して APPROVE。
親は新worktreeで clean check EXIT0 → patch適用後のcf beta.18/beta.20不一致診断 EXIT1 を実行して確認した。

## 実装と検証

- `just bump-tool ty 0.0.90` で3宣言と2 lockを更新し、Go syncでcfのheredocを再生成した。生成後 check はEXIT0。
- targeted tests `b5432698b` はEXIT0、69 passed（bump10、oracle33、既存install依存26）。
- lockをTOMLとして旧版と比較し、tyの版、成果物、要求specifier以外の依存が不変であることを確認した。emulatorのlock schema revisionだけはuvによって3→5へ更新された（rootは5のまま）。手で古いschemaに戻さない。
- mainの元2行は保持したまま。Go移植#486は `b59476e` でmerge済み、Go作業用worktreeとbranchは削除した。
- `just ci` (`b2e85038f`) はEXIT0、1743 passed / 33 skipped。rootとemulatorのty検査も成功し、両環境の実行版が0.0.90であることを確認した。
- artifact検査 (`b0b018f7e`) はEXIT0。両lockのty全18 artifactのhash/sizeをPyPIと照合し、macOS ARM64 wheelの実ダウンロードSHA-256も一致。cf beta.20 tarballの実SHA-512もnpm dist.integrityと一致した。その他platformの実ダウンロード試験は行っていない。
- 独立差分レビュー (`bd6420f66`) はAPPROVE。CodexはBun TOMLによる別実装の構造比較でも、tyとlock schema以外の依存不変、heredocと正本の一致を確認した。
- merge前にはlocal sandbox `just test` の成否と最新SHAの全PR CIを確認し、結果をPR本文へ記録する。localログは `/tmp/ty-cf-sandbox.log`。
