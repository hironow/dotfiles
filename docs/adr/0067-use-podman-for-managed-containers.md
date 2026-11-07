# ADR 0067 — コンテナの実行と導入を Podman に統一する

- **id**: ADR-0067
- **title**: コンテナの実行と導入を Podman に統一する
- **status**: Accepted
- **date**: 2026-11-08
- **decided-date**: 2026-11-08
- **decision-maker**: Hiroto N.
- **decision-maker-contact**: @hironow
- **author**: Pi（owner session）
- **author-contact**: @hironow
- **supersedes**: ADR-0001 の基底画像・Docker feature・CI action の指定、ADR-0005 の Windows 導入規則のうち Podman のみ、ADR-0035 のコンテナ実行系・画像削除・build-cache 自動回収の部分
- **superseded-by**: none
- **related**: [0003](0003-actions-pin-sha.md)、[0006](0006-mise-version-pinning.md)、[0014](0014-vendor-emulator-telemetry-from-submodules.md)、[0015](0015-adopt-portless-for-local-dev-urls.md) と後継 [0054](0054-run-portless-directly.md)、[0016](0016-integrate-emulate-api-emulators-via-npx.md) と後継 [0055](0055-run-emulate-with-bunx.md)、[0018](0018-windows-native-mvp.md)、[0025](0025-justfile-mise-tool-wrap.md)、[0039](0039-windows-bootstrap-ps1.md)、[0044](0044-python-toolchain-uv-ruff-ty.md)、[0045](0045-coder-control-plane-retired.md)、[0047](0047-rtk-mandatory-base-tooling.md)、[0049](0049-headroom-mandatory-base-tooling.md)、[0051](0051-adopt-decision-queue-for-new-records.md)、[0052](0052-renew-global-agent-instructions.md)、[0053](0053-stop-using-flatt-mirrors.md)、[0060](0060-frozen-image-generation-has-one-source.md)、[0061](0061-version-generator-in-go.md)、Proposed の [0065](0065-kernel-cve-is-evidence-only.md)／[0066](0066-doctor-warns-only-what-needs-action.md)
- **consultation-trace**: [公開 PR #565 の相談と所有者裁定](https://github.com/hironow/dotfiles/pull/565)。元作者・決裁者の @hironow が本文への代理掲載を明示許可した

## やさしい説明

このリポジトリがコンテナを動かす道具を、Docker から Podman にそろえる。
導入手順とテストも同じ道具を使い、Podman が使えないときに Docker へ切り替えない。
既存のデータや端末は、この変更だけでは移行・停止・削除しない。

## Context

所有者は 2026-11-08 に、リポジトリが管理するコンテナ実行経路を Podman へ移すよう指示した。
対象には開発用コンテナ、CI（自動検査）、使い捨ての試験環境、エミュレータ、計測環境、runner（検査を実行する機体）の保守を含む。
外部サブモジュールと過去の決定本文は対象外とした。

所有者は、Podman 5 以降、podman-compose を唯一の Compose provider（複数コンテナを起動する実装）とする方式を選んだ。
macOS は Homebrew、Linux は OS のパッケージ、Windows は Podman だけ winget を使う。
開発用コンテナの基底は Microsoft 公式の trixie とする。
古い OS で最低版を満たせないときは、別の配布元や Docker へ黙って切り替えず、エラーにする。

ADR-0001 は bookworm、Docker feature（開発用コンテナに Docker 接続を加える機能）、devcontainers/ci を指定した。
ADR-0005 は Windows の開発用道具を Scoop のみにした。
ADR-0035 は Docker の自動回収で、古い画像とビルドキャッシュの増加を抑えるとした。
これらの指定範囲は今回の選択と両立しない。
元作者・決裁者である @hironow は、承認済み文面で同じ公開 PR に相談と裁定を記録することを認めた。
[PR #565](https://github.com/hironow/dotfiles/pull/565) の相談文と裁定文は、本人が承認した文面とバイト単位で一致することを読み戻して確認した。

Podman の強制画像削除は、その画像を参照するコンテナも削除する。
確認した Podman 6.1.4 の実装では、画像の一括回収の一部が画像の期限判定と別に永続的な作業キャッシュを削除する。
このため Docker の回収コマンドをそのまま置換しない。
根拠は公式の [画像削除の説明](https://docs.podman.io/en/latest/markdown/podman-rmi.1.html)と [6.1.4 の画像回収実装](https://github.com/containers/podman/blob/v6.1.4/pkg/domain/infra/abi/images.go)である。
これは確認した版の根拠であり、全版の安全性を保証するものではない。

## Decision

次の 8 項を必須事項（MUST）として採択する。

1. このリポジトリが管理するコンテナ実行には Podman を使う。CLI（コマンド）と接続先の実行系を別々に確認し、双方が 5 以降であることを求める。Docker への暗黙の切替は設けない。
2. Compose は、mise が管理する podman-compose を明示して使う。Podman とこの provider は常設の必須道具とし、CLI 導入に開発依存の 7 日待機を適用しない。リポジトリの依存パッケージの待機規則は変えない。
3. Podman の導入は OS 標準の経路を使う。Windows の winget は Podman だけの例外で、他の Scoop 運用を変えない。Windows の導入処理は bootstrap.ps1 に置き、ADR-0039 の POSIX installer（Unix 系導入スクリプト）との分離を維持する。利用可能な最低版がなければ明示的に失敗する。仮想環境は導入処理で自動初期化・起動・更新しない。
4. 開発用コンテナは Microsoft 公式 trixie にし、Docker feature を外す。IDE（開発画面）と CI は同じ devcontainer.json を使う。Microsoft とローカル feature の信頼境界、root ユーザー、限定した信頼パスは維持する。選択した Podman の接続先を明示して渡す。
5. Dockerfile、Compose 形式、レジストリ名、API（接続の取り決め）などの互換名称は残せる。既存の Python Docker SDK（接続用ライブラリ）は、Podman と確認した接続先だけに向ける。Docker の既定接続先を継承しない。
6. 画像回収は個別に判断し、削除直前に情報を確認する。情報取得の失敗では削除しない。強制削除と親画像への連鎖削除を使わない。2 時間の保持設定、keep タグの別名を含む保護、実行中の別ジョブの保護、所有者別実行、Windows の制限時間を維持する。永続的な作業キャッシュの自動回収は行わず、従来のキャッシュ増大防止保証は継承しない。
7. 実行確認は使い捨ての構成で行い、その実行が作成した資源だけを片付ける。既存の名前・ポート・ネットワーク・ボリューム・書込み先を使わない。必須の接続やビルドの失敗をテストのスキップで隠さない。
8. この PR は端末への実インストール、machine（macOS／Windows が使う仮想環境）の初期化・起動・更新、既存 Docker やデータの停止・削除、agent home への同期を実行しない。OS 更新も実行しない。

## Options Considered

| 案 | 利点 | コスト・リスク | 裁定 |
| --- | --- | --- | --- |
| A) Podman と podman-compose に統一する | 起動手順と検査の実行系がそろい、Docker への意図しない接続を防げる | OS 別の導入・接続・互換性の試験が必要。証明できないキャッシュ回収を省くため回収量は減る | 所有者が採択 |
| B) Docker を維持する | 既存の起動手順と機能を変えずに済む | 所有者が求めた Podman 統一を実現しない。既存の実行系への依存が続く | Podman へ統一する所有者の指示を満たさないため却下 |
| C) Docker と Podman を自動選択する | 既存環境の一部をそのまま動かせる | 機体ごとに実行系が変わる。別の画像・データへ接続する事故と、両方の保守・試験が必要になる | 所有者が求めた暗黙の切替禁止と両立しないため却下 |

## Consequences

- **Positive**: 管理下のコンテナ実行経路を一つにそろえる。接続先、必須版、Compose の実装を明示し、別実行系への接続をエラーにできる。
- **Negative**: 古い Linux 配布版では導入できない場合がある。macOS と Windows は仮想環境を別途準備する必要がある。CLI と API の互換性には実行試験が要る。安全な期限を確認できないキャッシュは残り、ディスクの増大を防ぐ従来の保証はなくなる。画像削除の最終確認後に第三者がタグを付け替える競合まで、原子的に防げるとは保証しない。
- **Neutral**: コンテナ形式、レジストリ、HTTP UI の URL と通常運用のポートは変えない。画像内の道具の版は ADR-0060／0061 の正本と唯一の生成器で管理する。既存 Docker 環境を操作する危険な入力へのガードは残す。

## 反転記録 (Reversal)

- ADR-0001 の bookworm／Docker feature／devcontainers/ci の指定を、公式 trixie／明示的 Podman 接続／host CLI（機体上のコマンド）に置き換える。単一の設定、feature の信頼境界、root ユーザーは反転しない。
- ADR-0005 の Windows は Scoop のみという規則を、Podman の winget 導入だけ例外にする。ADR-0039 の Windows bootstrap と POSIX installer の分離は反転しない。
- ADR-0035 のコンテナ実行系・画像削除を置き換え、証明できないビルドキャッシュの自動回収を省く。2 時間の保持設定と保護条件は維持するが、キャッシュ増大防止保証は継承しない。
- 元作者・決裁者の @hironow が 2026-11-08 にこの限定範囲を承認した。[公開 PR #565](https://github.com/hironow/dotfiles/pull/565) に承認済みの相談文と本人裁定を代理記録した。
- 旧 ADR は決定本文を変更せず、状態・後継リンクのメタデータだけで部分置換を示す。

## 他の DR との照合

起票前に既存 65 ADR の題名・状態・後継関係を走査した。PDR はなかった。
キーワードの一致だけで判断せず、候補・関連記録 27 件（0001、0003、0005、0006、0014、0015、0016、0018、0025、0028、0030、0034、0035、0039、0044、0045、0047、0049、0051、0052、0053、0054、0055、0060、0061、0065、0066）の全文を読んで比較した。

- **矛盾**: 0001／0005／0035 の上記限定範囲を検出した。元作者・決裁者の @hironow が相談に参加し、同じ公開 PR で限定的な部分置換を承認した。他の決定は維持する。
- **重複**: 番号 0067 は未使用だった。同じ Podman 統一を定めた既存記録はなかった。データベース選定の個別指針を、このコンテナ実行系の決定には混ぜない。
- **誤読**: 0015／0016 は後継 0054／0055 と併読する。HTTP UI だけに portless を直接使い、emulate は host の bunx のままとする。0034 は 0045 で役割を終えており、廃止した Coder 構成を復活させない。
- **偽の関連**: 0025 の mise 経由実行、0039 の導入境界、0047／0049 の常設道具の扱い、0051 の公開 queue、0052 の Go 優先、0060／0061 の正本・生成器を維持する。0044 の Python 品質検査、0053 の project 依存の待機規則は変えない。0065／0066 は未決のままとし、カーネルを更新せず、doctor の ERR と終了コードの契約を変えない。
- **関係誤認**: 旧 3 件を丸ごと失効させない。起票時は旧記録の状態を維持した。採択時に各旧記録の状態行だけに限定範囲の後継リンクを加え、索引・queue の決定済みログと同時に更新する。

[相談・本人裁定](https://github.com/hironow/dotfiles/pull/565)を参照する。実行検証の成功を、この決定記録の状態から推定しない。

## 決定（2026-11-08）

- **A 案を Accepted**。決定者: Hiroto N.（@hironow）。元 3 ADR の作者・決裁者でもある本人が、[PR #565 の相談・裁定](https://github.com/hironow/dotfiles/pull/565)の代理掲載を明示許可した。
- B 案は Podman 統一を満たさないため却下、C 案は暗黙の切替禁止を満たさないため却下する。
- Proposed の起票には独立した Codex の整合レビューを行い、APPROVE、R1–R7・R9–R10 は各 2、R8 は採択時の逆参照待ちの 1 だった。採択時に旧 3 件の状態行・索引・変更ログ・queue の決定済み行を揃え、実ファイルで逆参照と旧本文の不変を検査した。R8 は 2 に上がり、採択時の R1–R10 はすべて 2 となった。
- 後続: Podman 移行を実装・検証し、同じ draft PR に追加する。端末への導入、既存データの移行、agent home 同期、merge はこの承認に含めない。
