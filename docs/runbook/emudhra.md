# eMudhra中間CA漏洩の診断

CA doctorの事故別ルール `emudhra-2026` は、[公開診断サイト](https://emudhra.we-have-a-problem.com/)の2026-10-23時点の情報を固定して検査する。
ビルド方法、共通のCA健全性チェック、結果の読み方と限界は [CA doctor](ca-doctor.md) にある。

## チェーンの実接続検査

公開診断サイトを正常系とし、同サイトが掲示する全14ホストを検査する。
DV、OV、EVそれぞれのG3B/G3Cについて、直接チェーンとAAAクロス署名チェーンの12本を区別する。
これに、Certificate Transparency（CT）に記録されていない証明書を提示する `dv-g3b-noct` と `dv-g3b-aaa-noct` の2ホストを加える（ドメインの後半は `-emudhra.we-have-a-problem.com`）。
CTを強制するクライアントは、CAを信頼したままでも未記録の証明書を拒否し得るため、通常の12本とは区別する。
14本はチェーンの提示方法の数であり、漏洩した秘密鍵の数ではない。
タイムアウトやDNS失敗は未確認であり、安全とは判定しない。
証明書を拒否した場合も、不信頼化されたCAが原因だと立証できないため `WARN` にする。

## 修正版の下限

| 対象 | 修正版の下限 |
| --- | --- |
| Go | 1.27.3 / 1.26.10 |
| Node.js | 22.23.4 / 24.22.1 / 26.12.1 |
| uv | 0.13.5 |
| mise | 2026.10.17 |
| certifi | 2026.10.19 |
| pip | 26.2.2 |
| rustup | 1.29.2 |
| Bun | 1.4.4（1.4系列） |

正本は `tools/ca-doctor/incidents/emudhra-2026.json` で、見直し期限も同ファイルに記録する。
GoとNode.jsは表に示す系列だけを比較する。
他のツールの対象系列もJSONの `branch` に明示し、未登録の系列を版番号の大小だけで合格にしない。
Bunのcanary版も安定版の下限からは判定しない。

## SSOTの固定版

画像用の固定版は `config/mise/image-tools.toml` で管理し、`just mise-versions-sync` で導入スクリプトへ反映する。
Go、Node.js、uv、Bunと、Linux初期導入用miseの版は、事故ルールの下限以上にする。
画像内の一時ビルドに使うrustupはfeatureの手書き領域にあり、版とCPU別の検証済みSHA-256を一緒に更新する。
数値の修正版下限は事故別JSONだけに置き、`tests/unit/test_ca_version_pins.py` がSSOTと手書き導入版を照合する（`just test-unit` と `just ci` の対象）。
必要な宣言や下限が欠けた場合、未登録の系列やプレリリースを固定した場合も検査を失敗させる。

ホスト用 `config/mise/config.toml` の `latest` と `lts` は、固定版や最低版の指定ではない。
これらは維持し、既存端末の導入済みツールは更新後に `just ca-doctor` で別途確認する。
SSOTの更新だけでは、起動中のプロセスや既存画像は更新されない。

## OSごとの修復

Mac、native Windows、WSL、Linuxでは、OSの信頼ストアと各ランタイムのCA束を別々に確認する。
[CA doctorのOS別手順](ca-doctor.md#os別の確認と修復)に従い、同じ端末と起動環境で診断を再実行する。
native WindowsのCPythonは、Windowsが拒否するAAA経由の7本を受け入れる。CPythonの修正版が出るまでの扱いは[WindowsのPython](ca-doctor.md#windowsのpython)にある。
[公式のrustup 1.29.2告知](https://blog.rust-lang.org/2026/10/20/Rustup-1.29.2/)は `rustup self update` を案内しているが、古い更新クライアント自身の取得経路も確認する。
CA環境変数を設定しただけで、静的に組み込まれたrustlsの信頼設定まで変わるとは判断しない。

Rustコンパイラの更新だけでは、アプリのrustls/webpki依存は更新されない。
各アプリのCargo.lockで、rustls-webpki 0.103.16、webpki-rootsとwebpki-root-certs 1.0.10の修正や適切なバックポートを別途確認する。
macOSのOS側の失効情報だけで `/etc/ssl/cert.pem` などのPEM束まで修正済みとは判定しない。
この診断は対策の自動適用や、全アプリの対策完了の保証を行わない。
