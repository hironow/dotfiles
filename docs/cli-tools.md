# レビュー、検索、データ抽出、プロセス調査のCLI

Hunk、ripgrep（`rg`）、fd、sd、mq、witr、jq、Mike Farahのyq、fqは、共通のmise設定から導入する。
版の正本は [`config/mise/config.toml`](../config/mise/config.toml) である。
通常のsetupでは、Mac、Linux、WSLの `install.sh` と、Windowsの `bootstrap.ps1` から呼ぶ `just deploy` が導入する。
jqも `aqua:jqlang/jq` の固定版で揃える。
MacのHomebrew復元対象からjqを外し、miseへ揃える。
導入済みのHomebrew版を除去する場合は、mise版が通常のシェルから動くことを先に確認する。
Windowsのmise導入前に使うbootstrap用jqと、既存のaliasは変更しない。

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
