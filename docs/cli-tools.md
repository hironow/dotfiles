# レビュー、検索、データ抽出、プロセス調査のCLI

Hunk、ripgrep（`rg`）、fd、sd、mq、witr、jq、Mike Farahのyq、fqは、共通のmise設定から導入する。
版の正本は [`config/mise/config.toml`](../config/mise/config.toml) である。
通常のsetupでは、Mac、Linux、WSLの `install.sh` と、Windowsの `bootstrap.ps1` から呼ぶ `just deploy` が導入する。
jqも `aqua:jqlang/jq` の固定版で揃える。
MacのHomebrew復元対象からjqを外し、miseへ揃える。
導入済みのHomebrew版を除去する場合は、mise版が通常のシェルから動くことを先に確認する。
Windowsのmise導入前に使うbootstrap用jqと、既存のaliasは変更しない。

## AWS CLI v2の管理

AWS CLIは `http:aws` の公式配布物をmiseで管理する。
固定版は2.39.6で、2026-11-07の調査時点の公式 `v2/version.txt` と配布物を確認した。
PyPIのAWS CLI v1やHomebrew版への自動フォールバックは行わない。

```shell
env MISE_GLOBAL_CONFIG_FILE="$PWD/config/mise/config.toml" \
  mise -C / install http:aws@2.39.6
just aws-list
```

Mac arm64とx64は同じUniversalパッケージ、Linux/WSLのx64とarm64はglibc用ZIPを選ぶ。
Windowsはこのbackendの対象外とし、既存のstandalone版を使う。
muslや他のCPU、WindowsのMSIについて、この設定での動作確認はしていない。
`aws-list` はPOSIXではcheckoutのmise版を明示して、古いPATHのAWSを実行しない。
Windowsの呼出しは従来どおりである。
いずれもローカルのprofile一覧であり、リモートの権限確認やログインは行わない。

配布物ごとのSHA256をmiseが展開前に照合する。
MacではさらにAppleの信頼検証とDeveloper IDのTeam `94KV3E626L` を確認し、完全なbundled runtimeをmiseの専用ディレクトリへ展開する。
書込み先は環境変数だけで信用せず、実行中のmiseが認可する導入先と物理パスを比較する。
パッケージのinstallerやroot権限は使わず、既存の `/usr/local/aws-cli` と `~/.aws` は変更しない。
mise自体は標準の導入先（`~/.local/bin` など）にあるものを使い、取得したpayload内のプログラムで導入先を調べない。

更新では、版、各URL、全checksum、Mac hook内の版とdigestを一緒に更新する。
MacのApple署名とLinuxのAWS CLI Team署名（fingerprint `FB5DB77FD5C118B80511ADA8A6310ACC4672475C`）を検証してからhashを採用する。
実行前に署名済みpayloadと導入先の全パス、型、内容、実行権限、link先を比較する。
checksum不一致、導入先のすり替え、署名失敗が未完了の導入として拒否され、再試行できることも確認する。
2.39.6のMac payloadにはsymlinkがないため、hookは新たなlinkを拒否する。
配布構造が変わった場合は、単に検査を緩めず構造を再確認する。

このMacでは全8,706エントリの一致とARM64起動を確認した。
Linuxは署名とELFのCPU種別を確認したが、LinuxやIntel Macでの実行を確認したという意味ではない。
miseをactivateする前から動いているプロセスのPATHは自動では変わらない。
新しいmise環境か明示したrecipeを使い、旧root所有のAWSは別途許可なく削除しない。

参照：[AWSの導入手順](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)、[公式の現在版](https://awscli.amazonaws.com/v2/version.txt)、[mise HTTP backend](https://mise.jdx.dev/dev-tools/backends/http.html)。

## 常設CLIと7日の待機

待機の例外は、dotfilesで常設する主CLIと、そのCLI専用の導入環境内の依存パッケージに限定する。
方針の正本は [`ROOT_AGENTS_docs_agents_dependency-policy.md`](../ROOT_AGENTS_docs_agents_dependency-policy.md) である。
固定版やLTS、betaの選択は維持し、この変更で既存CLIをまとめて更新しない。

| 導入対象 | 現在の設定と境界 |
| --- | --- |
| hostのmise管理CLI、just、uv | `minimum_release_age = "0d"`。mise自体のbootstrapにも7日判定を追加しない |
| 常設npm CLI | 13宣言の `bun_args = "--minimum-release-age=0"`。各CLIの専用環境の依存も対象 |
| headroom | 専用uv tool環境の `--exclude-newer 0d`。Python 3.13、extras、固定版は維持 |
| Homebrew、Scoop、検証付きbootstrap | このrepoの7日判定はない。配布元のcatalog更新時期や固定版とは別の話 |
| npmとuvの機体設定 | 既存の `min-release-age=7` と `exclude-newer = "7 days"` を維持 |
| repoのPython依存 | 各projectの7日を維持。ruff/tyの既存例外はそのまま |
| LSP/MCP、単発uvx/bunx、CI専用、marketplace/plugin | 現状維持。新しい例外は個別判断 |
| devcontainerの凍結世代 | 既存の版と生成器を維持。この変更で再生成や一括更新を行わない |

npm設定があるだけでBunの待機が働くとは判断しない。
Bun 1.4.4の隔離したglobal導入試験では、npmrcの7日指定だけでは新しい依存を拒否しなかった。
明示したBunの7日引数とuvの7日設定では新しい依存を拒否し、CLI専用の0日指定では本体と依存を導入できた。
本体だけの例外、0日指定の除去、依存の公開日時だけを古くする対照も試験する。
全体のnpm/uv設定を0日にしたり、repo依存の判断をこのCLI例外で置き換えたりしない。

## このcheckoutから導入する

次のrecipeは、このcheckoutの9つの道具を選択して導入し、それぞれの版を確認する。
機体のglobalなmise設定は変更しない。

```shell
just cli-tools-install
```

古いシェルのPATHが別のjqを指していても、checkoutのルートから次のように固定版を確認できる。

```shell
env MISE_GLOBAL_CONFIG_FILE="$PWD/config/mise/config.toml" \
  mise -C / exec aqua:jqlang/jq -- jq --version
```

| 道具 | macOS | Linux / WSL | Windows native |
| --- | --- | --- | --- |
| Hunk | arm64、x64 | glibc、arm64、x64 | x64、mise 2026.8.6以降 |
| rg、fd | arm64、x64 | arm64、x64 | arm64、x64 |
| sd | arm64、x64 | arm64、x64 | x64のみ |
| mq | arm64のみ | GNU/glibc版、arm64、x64 | arm64、x64 |
| witr、fq | arm64、x64 | arm64、x64 | arm64、x64 |
| jq | arm64、x64 | arm64、x64 | x64（arm64ではx64版を選択） |
| mikefarah/yq | arm64、x64 | arm64、x64 | このaqua backendではx64のみ |

表は上流の配布物と選択したbackendの対応を示し、すべての環境での実機検証を意味しない。
9つすべてを導入できる共通範囲は、Mac arm64、glibc Linux/WSLのarm64とx64、Windows native x64である。
Intel Macでは、共通設定の `mise install` もこのrecipeもmqをスキップし、他の8つを導入する。
recipeはmqが利用できない旨を表示する。
Windows arm64ではHunk、sd、yqのbackendが共通範囲に入らず、musl LinuxではHunkとこのmq設定を利用できない。
ソースビルドへの自動フォールバックは行わない。

mq以外はmiseのaqua backendで上流の実行ファイルを取得する。
yqは `aqua:mikefarah/yq`、fqは `aqua:wader/fq` を明示し、Python版yqや同名の別ツールとの混同を避ける。
mqはGitHub backendで本体のraw binaryだけを選び、`mq`（Windowsでは `mq.exe`）として導入する。
同じreleaseにある補助CLIやdeb/rpmは選ばない。
NodeやRustのビルド環境は追加しない。

mqは対応する5環境ごとにSHA256を固定し、miseが実行前に照合する。
更新時は版と全環境のchecksumをセットで更新し、release APIのdigest、上流の `checksums.txt`、取得した実物のハッシュを照合する。
同一配布元のchecksumは改変検出の材料であり、発行者のprovenanceを保証するものではない。
他の道具はaqua registryのchecksum検証を使う。

miseで入れた版の更新はmiseで行う。
sdのv1.1.0は、上流の版番号が未更新のため `sd --version` が `1.0.0` と表示される（[タグ内の設定](https://github.com/chmln/sd/blob/v1.1.0/Cargo.toml)）。

## エージェントが必要部分を抽出する

JSONは `jq`、YAMLは `yq`、バイナリ構造は `fq`、Markdownは `mq`、プロセスの起動元は `witr` を使い分ける。
対象を絞って抽出してからモデルへ渡すことで、ファイル全体やプロセス一覧を読む必要を減らす。
処理時間やトークン削減率は入力と操作に依存するため、一定の改善は保証しない。

コマンド例、既定動作、witrの終了コードは [`ROOT_AGENTS_docs_agents_cli-tools.md`](../ROOT_AGENTS_docs_agents_cli-tools.md) にまとめる。
エージェント向けの正本は `ROOT_AGENTS.md` とこのspokeであり、配布先を直接編集しない。
配布は [`docs/agent-sync.md`](agent-sync.md) に従い、`just sync-agents-preview` で対象homeの差分を確認してから行う。
既存の `grep`、`find`、`sed` を同名のaliasで上書きせず、スクリプトの移行は必要な箇所ごとに動作を確かめる。

参照: [Hunkの導入条件](https://github.com/modem-dev/hunk/tree/v0.24.1#install)、[mise GitHub backend](https://mise.jdx.dev/dev-tools/backends/github.html)、[mise registry](https://mise.jdx.dev/registry.html)。
