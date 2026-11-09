# ADR 0068 — dev container の mise を、署名を確かめた tarball で凍結する

- **id**: ADR-0068
- **title**: dev container の mise を、署名を確かめた tarball で凍結する
- **status**: Proposed
- **date**: 2026-11-09
- **decided-date**: —
- **decision-maker**: Hiroto N.
- **decision-maker-contact**: @hironow
- **author**: Claude Code（owner session、Windows 機）
- **author-contact**: @hironow
- **supersedes**: ADR-0001 の表の mise の行のうち取得元と検証方法、ADR-0060 の Decision 1・2・4 のうち画像の mise に関わる範囲
- **superseded-by**: none
- **related**: [0001](0001-devcontainer-debian-features.md)、[0005](0005-install-path-rationalization.md)、[0006](0006-mise-version-pinning.md)、[0053](0053-stop-using-flatt-mirrors.md)、[0060](0060-frozen-image-generation-has-one-source.md)、[0061](0061-version-generator-in-go.md)、[0067](0067-use-podman-for-managed-containers.md)
- **consultation-trace**: 2026-11-09 の本セッションでの所有者の選択と裁定（下の「相談の記録」）。公開 PR にも同じ文面を残す

## やさしい説明

開発用コンテナ（dev container）を作るとき、道具の版を管理する mise そのものが、毎回その日の最新版になっていた。
ほかの道具は版を固定しているので、mise だけが日によって変わる。
これをやめて、手元の導入手順と同じ版に固定する。
入れ方は、配布元の署名を確かめてから入れる今の安全さを保つ。

## Context

- `.devcontainer/features/dotfiles-tools/install.sh` は、mise を jdx の apt リポジトリ（`https://mise.jdx.dev/deb stable main`、鍵の指紋 `24853EC9F655CE80B48E6C3A8B81C9D17413A06D` を固定）から、版を指定せずに入れていた。
- そのリポジトリの一覧（`dists/stable/main/binary-amd64/Packages`）は、2026-11-09 の確認で最新版 1 件（`2026.11.5`）だけを載せていた。apt のままでは版を固定できない。
- 2026-11-09 の main（ea25cff）の dev container ジョブ（run 42614770632 の 1 回目）のログでは、画像の中の mise は `2026.11.5`（その日のリリース）だった。
- 手元の導入（`install.sh` の `_mise_ver`）と CI の bootstrap（`.devcontainer/ci-bootstrap.sh`）は、`config/mise/image-tools.toml` の `[bootstrap].mise = "2026.10.17"` を使う。画像の mise だけが、同じ固定から外れている。
- ADR-0006 は画像の版を凍結し、ADR-0060・0061 は画像の凍結世代の正本を `image-tools.toml` 1 か所、書き手を生成器 `tools/mise-versions` 1 つにした。ADR-0001 は mise を apt から指紋固定で入れると決めた。
- jdx の GitHub リリースには、同じ鍵で署名した `SHASUMS256.asc` がある。v2026.10.17 で、上の指紋の鍵による署名が正しいこと（GnuPG の `VALIDSIG 24853EC9F655CE80B48E6C3A8B81C9D17413A06D`）を 2026-11-09 に確かめた。
- 同じ tarball と `SHASUMS256.asc` は `https://mise.jdx.dev/v<版>/` にもある。2026-11-09 に github.com の `/releases/download/` が約 1.5 時間 504 を返し、#580 は CI の bootstrap の mise を「mise.jdx.dev を先に、GitHub を後に」取るように変えた。ハッシュの一覧は mise の文書（「Checksums never come from mise.jdx.dev」）に従い GitHub から取っている。
- 画像にはほかにも版を固定していない道具がある（gcloud と claude-code の apt、node feature の `lts`）。ADR-0060 は mise が持つ道具だけを対象にしたので、本 ADR もそれらを扱わない。

## Decision

（Proposed。確定後に MUST 文で記述。）

決定案（A′）:

- D1: 画像は、mise を jdx が配る tarball で入れる。版は `image-tools.toml` の `[bootstrap].mise`。tarball は mise.jdx.dev から、取れなければ GitHub リリースから取る。`SHASUMS256.asc` は GitHub リリースから、取れなければ mise.jdx.dev から取る。どちらのホストから取ったものも、D2 の確認を通ったものだけを使う。
- D2: tarball は、同じリリースの `SHASUMS256.asc` で確かめてから展開する。署名は、ADR-0001 が固定した指紋の鍵によるものでなければならない（GnuPG の `VALIDSIG` の主鍵の指紋で判定）。そのうえで、署名済みの一覧のうち、その tarball の行がちょうど 1 行あり、ハッシュが一致することを確かめる。
- D3: 画像は mise の apt リポジトリと、その鍵の apt 用の登録を使わない。Google Cloud と Claude Code の apt と、指紋を固定する仕組みは変えない。
- D4: feature の install.sh の `MISE_VERSION` は、生成器 `tools/mise-versions` が `[bootstrap].mise` から書く。`just mise-versions-check` が食い違いを検出する。

## Options Considered

| 案 | 利点 | コスト・リスク |
| --- | --- | --- |
| A′) tarball + 署名付き SHASUMS256.asc（同じ指紋） | 版が固定され、手元と CI と画像が同じ版になる。信頼の根拠は今と同じ「固定した指紋の GPG 署名」 | 署名の検証を feature に書く必要がある。arm64 はリリースにあるが、CI は x64 だけで確かめる |
| A) tarball + SHASUMS256.txt の照合だけ（手元の bootstrap と同じ） | 実装が最小 | GPG 署名の確認を失う。ADR-0001 の指紋固定と、ADR-0006 が後退と呼んだ形になる |
| B) apt の最新のまま、意図した例外として記録する | 変更が最小 | 版が日によって変わり、ADR-0006・0060 の凍結の方針と食い違ったまま |
| C) 保留 | 何もしない | B と同じ食い違いが残る |

## Consequences

- **Positive**: 画像の mise が、手元と CI の bootstrap と同じ版になる。ビルドの日によって mise が変わらない。apt と同じ指紋の署名を確かめるので、信頼の水準は下がらない。どちらか一方のホストが止まっても画像を作れる。署名で確かめるので、ハッシュの一覧が mise.jdx.dev から来ても偽物は止まる。
- **Negative**: 画像の mise は 2026.11.5 から 2026.10.17 に戻る。画像に焼いた mise の設定がこの版で入るかは、CI の dev container ジョブでしか確かめられない。mise の更新は `[bootstrap].mise` を上げる作業になる。tarball 版の mise は self-update を持つが、画像では呼ばない。arm64 の画像は CI で確かめていない。
- **Neutral**: 画像の mise の場所は `/usr/bin/mise`（apt）から `/usr/local/bin/mise` に変わる。`/opt/mise` のデータの場所と shim の PATH は変えない。`.cursor/install.sh` は今までどおり apt の mise を入れる（本 ADR の対象外）。

## 反転記録 (Reversal)

- ADR-0001 の表の mise の行の「取得元 `mise.jdx.dev/deb`」を、jdx の GitHub リリースの tarball に置き換える。検証は「指紋を固定した GPG 鍵」のまま、対象を apt の署名から `SHASUMS256.asc` の署名に移す。ADR-0001 の他の決定（gcloud の apt、指紋固定の仕組み、uv・just・sheldon、単一設定、feature の信頼境界）は反転しない。
- ADR-0060 の Decision 1 の `[bootstrap]` を「mise の無い Linux 機体」に加えて画像の mise にも使う。Decision 2 の生成領域に feature の `MISE_VERSION` を加える。Decision 4 の比較先を `_mise_ver` と `MISE_VERSION` にする。正本 1 ファイル、唯一の書き手、host との整合、凍結は反転しない。
- 旧 ADR は決定本文を変えず、Status 行で部分置換を示す。

## 他の DR との照合

全 67 件の ADR の題名・状態・置換関係を走査し、画像・mise・版の固定・導入経路・apt と GPG の信頼・取得元に触れる記録の全文を読んだ（0001、0005、0006、0018、0023、0025、0028、0036、0040、0053、0060、0061、0067 ほか）。PDR はない。

- **矛盾**: 0001（mise の取得元）と 0060（Decision 1・2・4）。所有者が 2026-11-09 に、この範囲だけの部分置換を承認した（下の「相談の記録」）。A 案は 0001 と 0006 の GPG の水準を下げるため、A′ を選んで矛盾を避けた。
- **重複**: 番号 0068 は未使用。同じ決定の記録はない。
- **誤読**: 0005 の 32 行目と 202 行目の表は、当時の監査の記録で決定ではない。本 ADR で注記は不要。
- **偽の関連**: 0053（公式の取得元に戻す）は GitHub リリースを公式の取得元として扱い、7 日待ちはパッケージにだけ適用するので、衝突しない。0061 の決定は生成器の実装についてで、変えない。0023・0025・0036・0040 は影響を受けない。
- **関係誤認**: 0001 と 0060 を丸ごと失効させない。両者の Status 行に範囲を限った部分置換を書く。

## 相談の記録

- 2026-11-09、本セッションで所有者（@hironow、0001・0006・0060・0061 の決定者）が、次を選んだ。
    - mise の固定の方法: 「tarball で固定する」（apt の最新のまま・保留ではなく）。
    - 検証: 「A′ 署名付き SHASUMS」（A の SHA-256 だけではなく）。
    - 0001 に加えて 0060 の Decision 1・2・4 の部分置換: 「部分置換を承認」。

## 決定（記入待ち）

- [ ] A′ を Accepted（D1〜D4 を MUST 文で確定し、0001・0060 の Status 行、索引、変更ログ、queue を更新する）
- [ ] A を Accepted（D2 を SHA-256 の照合だけにし、0006 の後退として記録する）
- [ ] B を Accepted（apt の最新を意図した例外として `image-tools.toml` に記録し、実装を戻す）
- [ ] Rejected / Deferred（実装を戻し、queue に理由を残す）

決定者: ＿＿＿　決定日: ＿＿＿
