# レビュー・検索・置換のCLI

Hunk、ripgrep（`rg`）、fd（`fd`）、sd（`sd`）は、共通のmise設定から導入する。
版の正本は [`config/mise/config.toml`](../config/mise/config.toml) である。
通常のsetupでは、Mac・Linux・WSLの `install.sh` と、Windowsの `bootstrap.ps1` から呼ぶ `just deploy` が導入する。

このcheckoutの4つの道具だけを導入し、実行できることと版を確認するには、次を実行する。
このタスクは、機体のglobalなmise設定を変更しない。

```shell
just cli-tools-install
```

| 環境 | Hunkの対応 |
| --- | --- |
| macOS | arm64、x64 |
| Windows native | x64。mise 2026.8.6以降が必要 |
| Windows WSL | Linux版をWSL内に導入。glibcのあるUbuntuなど、arm64・x64 |
| Linux | glibcのあるUbuntuなど、arm64・x64 |

Hunkの配布物には、Windows arm64版とmusl版はない。
4つともmiseのaqua backendで上流の実行ファイルを取得するため、NodeやOSごとの追加パッケージは要らない。
miseで入れた版の更新はmiseで行う。
sdのv1.1.0は、上流の版番号が未更新のため `sd --version` が `1.0.0` と表示される（[タグ内の設定](https://github.com/chmln/sd/blob/v1.1.0/Cargo.toml)）。

エージェントには、`ROOT_AGENTS.md` のHunkレビュー手順と、検索・置換の使い分けを `just sync-agents` で配る。
引数と既定動作の違いは [`ROOT_AGENTS_docs_agents_cli-tools.md`](../ROOT_AGENTS_docs_agents_cli-tools.md) にまとめている。
`grep`・`find`・`sed` を同名のaliasで上書きせず、既存スクリプトは必要な箇所ごとに動作を確かめて移す。
処理速度は入力と操作によって変わるため、この設定は速度向上を保証しない。

参照: [Hunkの導入条件](https://github.com/modem-dev/hunk/tree/v0.24.1#install)、[miseのregistry](https://mise.jdx.dev/registry.html)。
