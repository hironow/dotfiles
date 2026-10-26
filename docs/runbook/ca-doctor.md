# CAの健全性とインシデントの診断

`just doctor` のCA診断は、日常のCA設定の検査と、レビュー済みの事故別ルールによる検査を行う。
確認済みの根拠と未確認の範囲を分け、端末全体が安全だとは判定しない。
証明書、パッケージ、OS設定を変更せず、管理者権限も使わない。

## 実行

初回と診断ソースの変更後は明示的にビルドする。
Go 1.27.3以上のローカルコンパイラとmiseが必要で、コンパイラを自動取得しない。
ビルド後の診断自体はGoを必要としない。

```sh
just ca-doctor-build
just doctor
```

CA診断だけを実行する場合は `just ca-doctor` を使う。
通信を行わない場合は `just ca-doctor --offline` を使う。
`CA_DOCTOR_OFFLINE=1 just doctor` でもCA検査の通信だけを省ける。
PowerShellでは先に `$env:CA_DOCTOR_OFFLINE='1'` を設定する。
通信を省いた結果は `WARN` になる。

バイナリがない場合、`doctor` は `WARN ca-build` とビルド手順を表示する。
Goソース、テスト、事故別JSON、`go.mod` をバイナリに埋め込み、現在のcheckoutのファイル集合とバイト列を照合する。
不一致なら検査結果を受理せず、再ビルドを求める。
この照合は更新漏れを検出するもので、悪意ある実行ファイルの真正性を証明するものではない。

`just ca-doctor-build-all` はLinux、macOS、Windowsの各amd64とarm64向けバイナリを `output/ca-doctor/` に作る。
別の端末へ配る場合は、同じcheckoutと対応するバイナリを使い、`ca-doctor` （Windowsは `ca-doctor.exe`）として同ディレクトリに置く。
WindowsのrecipeはPowerShellからGit Bashを経由して起動する。
`.cmd` と `.bat` のラッパーしか見つからないツールは実行せず、未確認と表示する。
クロスビルドの成功は、各OSでの実行確認とは区別する。

## 共通のCA健全性チェック

- TLS検証を無効にする環境変数と、現在の設定コンテキストのGit `http.sslVerify` を確認する。`GIT_SSL_NO_VERIFY` は値が `0`、`false`、空文字でも、定義されていれば検証を無効にするため `ERR` にする。Gitの確認対象URLは正常系の `https://example.com/` であり、他repoやURLの設定は保証しない。
- 明示指定されたCAファイルの存在、読み取り、PEMとX509の解析、ローカル時計に対する有効期間を確認する。各ファイルの上限は1MiBで、証明書の内容やsubject、設定値は表示しない。
- CAディレクトリは開けることだけを確認し、中身やバックエンドでの有効性は保証しない。Unixの `SSL_CERT_DIR` と `GIT_SSL_CAPATH` はコロン区切り、Windowsはセミコロン区切りとして扱う。空の要素は未確認にする。
- 各TLSクライアントで正常系へのHTTPS接続を試す。curl、Node.jsのTLS API、Pythonの標準ssl、Bunのfetch、診断バイナリ自身のGo HTTPクライアントを別々に観測する。
- 現在のPATHで選ばれるGit、Go、uv、rustup、rustcを含め、ツールとCAパッケージの情報を収集する。macOSではPATHのものと異なる `/usr/bin/curl` と `/usr/bin/python3` も調べる。

CAファイルの対象は `SSL_CERT_FILE`、`CURL_CA_BUNDLE`、`REQUESTS_CA_BUNDLE`、`PIP_CERT`、`GIT_SSL_CAINFO`、`NODE_EXTRA_CA_CERTS` である。
`REQUESTS_CA_BUNDLE` はディレクトリ指定も認める。
Windowsの環境変数名は大文字小文字を区別せず、Unixでは区別する。
CA束を解析できても、その内容が信頼に値することや失効確認の実施までは立証できない。
ルート証明書の期限切れの扱いもTLS実装に依存するため、期限だけで一律に不信頼化しない。

## 通信と実行の制限

リダイレクト先を追わず、curlの設定ファイルも読み込まない。
TLSを無効化するオプションは追加しない。
Node.js、Python、Goは直接接続し、curlとBunはそれぞれのプロキシ設定の影響を受け得る。
正常系の成功は、別のホストへの到達性を保証しない。

診断処理のコンテキストは全体30秒、外部コマンドは各4秒を上限とする。
同時接続数は全クライアント合計12本までに制限する。
標準出力と標準エラーは各4096バイトまで保持し、超過は未確認にする。
外部コマンドには `GOTOOLCHAIN=local`、`MISE_AUTO_INSTALL=false`、`RUSTUP_AUTO_INSTALL=0` を渡し、Go、mise、rustupのツールチェーン自動取得を抑止する。
必要なツールがなければ、診断のために導入せず未確認とする。
コマンドのキャンセル時には子プロセスの終了も試み、出力パイプ待ちにも期限を設ける。
Windowsの子孫プロセス終了はSystem32のtaskkillによるbest effortであり、権限やshimの構成に依存する。
taskkillの場所はWindowsのAPIが返すsystemディレクトリから決め、環境変数`SystemRoot`には頼らない。
PATH検索やファイル読み取りなど、OSのI/O全般を厳密な実時間で制限するものではない。

## 結果と限界

| 表示 | 意味 |
| --- | --- |
| `OK ca-file-*` | 指定ファイルを解析できた。信頼性や失効状態の保証ではない |
| `OK ca-https-*` | 当該クライアントが正常系へのTLS接続を受け入れた。その接続だけの観測 |
| `OK ca-version-*` | 事故別の修正版下限を満たす。実効CA束まで安全だという意味ではない |
| `ERR ca-version-*` | 既知の対象系列で修正版より古い |
| `ERR ca-live-*` / `ERR ca-chain-*` | 事故のテストホストへのTLS接続を受け入れた。CA束とTLS中継の有無を調べる |
| `WARN` と `certificate-rejected` | 証明書を拒否したが、当該CAの不信頼化が理由とは立証できない |
| `WARN` と `unknown` | 通信、実行、解析などに失敗した。安全とは判定しない |
| `WARN ca-policy-*` | レビュー期限を過ぎた。公開元の告知に照らしてルールを見直す |

HTTP 4xx、5xx、リダイレクトでもTLS接続を受け入れた事実は変わらない。
反対に、証明書エラーだけでは事故への対策済みとしない。
期限切れ、ホスト名不一致、プロキシ証明書の異常でも同じ種類のエラーになるためである。
TLS中継がある場合、接続成功だけで漏洩した証明書自体を受け入れたと断定しない。

単体コマンドの終了コードは、`0` が警告なし、`1` が未確認を含む、`2` が `ERR` を含む。
`doctor` は結果と終了コードの整合性を確かめて集計し、`ERR` があれば既存仕様どおり終了コード1を返す。
通常は確認範囲の限界を示す `WARN ca-coverage` が残る。
警告を消すために未確認項目を合格にしない。

WSLではLinux側だけを調べる。
Windows本体での実行はWSL内を保証しない。
macOSのKeychainの失効情報とPEM束も別物である。
ブラウザやOSの失効リスト配信状態、他のPATH上のコピー、別の仮想環境、pip内部のvendored CA束、Electron、コンテナ、既存の静的Go/Rustバイナリは保証しない。
OSのパッケージ情報は収集するが、異なるディストリビューションの版を単純比較しない。

## OS別の確認と修復

同じOSでも、PATHで選ぶ実行ファイル、仮想環境、明示されたCAファイルによって結果は変わる。
まず `ca-tool-*` の実行ファイルと `ca-env` を確認し、正常系が成功したかと、事故テスト先ごとの結果を記録する。
`unknown` が残る検査は完了扱いにしない。
`ca-remediation` はOS別の確認先を案内するだけで、更新や信頼ストアの変更を行わない。
社内CAやTLS中継を使う端末では、CA束を置き換える前に管理者と確認する。

| 環境 | 確認と修復 | 別途確認する範囲 |
| --- | --- | --- |
| macOS | OS更新に加え、Homebrewの `ca-certificates` と実際に使うPEM束を確認する | Keychain、`/etc/ssl/cert.pem`、Pythonの既定CAは同一ではない |
| native Windows | Windows Updateと組織の証明書配信状態を確認する | Schannelは、OSストアとMicrosoftの拒否リスト（CTL）を使う。CPythonの標準sslは、OSストアのルートだけを使う（[WindowsのPython](#windowsのpython)）。Node.jsなどの独立したPEM束は別々に更新する |
| WSL | 各ディストリビューションの `ca-certificates` をその環境内で更新する | Windows本体の更新や別のWSLディストリビューションには反映されない |
| Linux | ディストリビューションの公式パッケージ更新でCA束を更新する | コンテナ、仮想環境、静的バイナリ、独立したCA束は別々に確認する |

LinuxとWSLでは、端末の管理方針に従い、Debian/Ubuntuなら `apt`、Fedora系なら `dnf`、Alpineなら `apk` でCAパッケージを更新する。
バックポートがあるため、異なるディストリビューションの版番号を単純比較しない。
Windowsの診断はWSL経由で代用せず、Windows本体でビルドしたバイナリをPowerShellから `just ca-doctor` で実行する（recipeはGit Bashを経由する）。
ツールの更新後は、新しいプロセスから同じ診断を実行する。
Windows、WSL、Linuxの実行結果は、それぞれの実機で確認する必要がある。
Macでの成功やクロスビルドの成功を、他OSでの修復確認とはしない。

### Macでユーザー領域のCA束を選ぶ

HomebrewのCAパッケージを更新したうえで、実ファイルと実接続を確認する。
Apple Siliconでは通常 `/opt/homebrew/etc/ca-certificates/cert.pem`、Intel Macでは通常 `/usr/local/etc/ca-certificates/cert.pem` だが、配置は端末ごとに確認する。
既存のCA環境変数がある場合は、追加の変数で優先順位を変えず、その設定の管理者と調整する。

既存のCA指定がない端末では、更新済みCA束を `SSL_CERT_FILE`（対応するPythonの標準ssl）、`CURL_CA_BUNDLE`（curl）、`REQUESTS_CA_BUNDLE`（Requests）、`PIP_CERT`（pip）としてユーザーのシェル設定で指定する方法がある。
これは各クライアント向けの指定であり、OSの信頼ストアを修復する操作ではない。
環境変数を設定したシェルから新しく起動するプロセスにだけ反映され、起動済みのエディタ、GUI、サービスには遡って反映されない。

Apple付属のPython/LibreSSLでは、`SSL_CERT_FILE` が表示上の既定パスに反映されても、TLSの既定CA読み込みに使われない場合がある。
MacのPython 3.9.6／LibreSSL 2.8.3でこの挙動を実測したため、変数の表示だけで修復済みと判断しない。
その場合は、修正済みの管理下Pythonを使うか、アプリが提供するCA指定を使う。
Pythonの標準sslを使うアプリなら `ssl.create_default_context(cafile="更新済みCA束の絶対パス")` を明示して検証できるが、他のHTTPライブラリへ自動適用されるものではない。
システムPythonを使い続けて接続受理が残る場合は、`ERR` を残す。
診断コードを変えてその接続だけ別のCA束に切り替えたり、警告を消すために `sitecustomize.py` を追加したりしない。
OS管理ファイルやKeychainの修復は、ユーザー環境変数の変更と分け、管理者の承認を得て行う。

### WindowsのPython

WindowsのCPythonの標準sslは、WindowsのROOTストアとCAストアにある証明書を、信頼の起点として読み込む。
Microsoftが自動更新で配る拒否リスト（CTL）とDisallowedストアは見ない。
そのため、Windowsが拒否する中間CAでも、ROOTストアのルートまで辿れれば、Pythonは接続を受け入れる。
eMudhraの事故では、AAA Certificate Servicesが署名した中間CA（`-aaa-` の7本）がこれに当たる。
Windows自身はこの7本を拒否するので、Windowsの検証器を使うGoなどの結果から、Pythonの結果を推測しない。

CPythonの修正（gh-160040、CVE-2026-115557）は、漏れた鍵を含むチェーンを拒否する。
修正版が出たら、PATHのPythonと、uvなどが管理する各Pythonを更新し、`just ca-doctor` を実行し直す。
EOLの系列には修正が出ない。

修正版が出るまで、OSストアのAAA Certificate Servicesの用途（EKUの属性）を変える方法は使わない。
2026-10-26の実測では、次の2つが起きた。

- Windowsのルートの自動更新が、約30分で属性を元に戻した。
- 変えている間、AAAが相互証明書を出している別のルート（SSL.comなど）のチェーンが、Windowsの検証器でもPythonでも失敗した。このルート本体がOSストアに無い端末では、`https://example.com/` も失敗した。

自動更新を止めると、拒否リストの配布も止まるので、これもしない。
診断のPythonだけを別のCA束に切り替えたり、`sitecustomize.py` で警告を消したりはしない。
修正版が出るまで、`ERR` は残す。

## 事故別ルールの追加と更新

正本は `tools/ca-doctor/incidents/*.json` である。
実行時に外部から判定ルールを取得しない。
JSONにはID、検査種別、根拠URL、確認日、見直し期限、正常系URL、事故のテストホスト、ツール別の修正版下限、未修正ツール、確認上の注意を記録する。

現在の検査種別は `tls-endpoint-and-version` だけであり、対象ホストへの接続受理と既知の修正版下限を検査する。
それ以外の種類の事故にはコードとテストの追加が必要で、JSONだけで任意の診断やコマンドを実行できるものではない。
バージョンを収集できないツールの下限を追加すると、manifest検証で拒否する。
未登録のリリース系列、開発版、解釈できない版は `WARN` にする。

ルールを変更するときは公開元の修正告知と根拠URLを確かめ、テストと事故別の説明を更新してレビューする。
見直し期限切れは警告し、古いルールを使って機械全体を安全とは判定しない。
追加、削除、変更のいずれも再ビルドが必要になる。

収録済みの事故は [eMudhra中間CA漏洩](emudhra.md) を参照する。
