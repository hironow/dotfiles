# Windows と WSL の Ollama を一本化する

Windows と WSL が共存する機体では、Scoop の `extras/ollama-full` だけを Ollama 本体として使う。
モデルと認証情報も Windows 側に置く。
Scoop の CLI 版 `main/ollama`、WinGet 版、単独インストーラ版、WSL の Linux 版を併設しない。
WSL のない Linux と macOS の導入方法は変えない。

## Windows 側の準備

`dump/windows/scoop.json` は `ollama-full` を宣言している。
新規セットアップでは `just add-scoop` が復元する。
既存の CLI 版から移す場合は、動作中の Ollama を終了してから次を実行する。
モデルや `~/.ollama` は削除しない。

```powershell
scoop uninstall ollama
scoop install extras/ollama-full
just deploy
just doctor
```

Ollama のフル版アプリケーションが Windows の `127.0.0.1:11434` を所有する構成にする。
`0.0.0.0` や WSL のゲートウェイへ公開せず、ファイアウォールの例外や portproxy は追加しない。

## WSL 側の共有

WSL の `just deploy` は、Pi の拡張導入時にユーザーの `ollama-windows-bridge.service` を設定する。
Windows のフル版と mise 管理の Windows Python が先に必要であり、不足していても WSL に Linux 版を導入しない。
ユーザーの systemd と Windows interop が利用できなければ、不足を表示する。
ヘルパーは `~/.local/lib/dotfiles/ollama_host.py` に管理対象としてコピーし、`/usr/bin/python3` で動かす。
worktree や一時的な venv の存続には依存させない。
既存の無関係なファイル、変更された管理対象、symlink は上書きしない。

```bash
just deploy
systemctl --user status ollama-windows-bridge.service
just doctor
```

ブリッジは WSL の `127.0.0.1:11434` と `[::1]:11434` だけで待ち受ける。
検証した物理パスの Windows Python を `-I -S -B -u` で隔離起動し、Windows の `127.0.0.1:11434` にバイト列を転送する。
転送は両方向とも raw binary の32KiB単位とし、PowerShell のテキスト pipeline は使わない。
Windows の `MISE_DATA_DIR` に対応し、完全なバージョン番号のディレクトリだけを数値順で調べる。
最初の3候補を最大3秒ずつ隔離検証し、Windows 本体の Python であることと venv でないことを確認する。
`~/.local/bin/ollama` は、本体ではなく Windows のフル版 CLI を呼ぶ管理対象の shim とする。
この shim は backend の状態にかかわらず先に配置し、既存の導入処理が停止中の backend を Linux 版の不足と誤認しないようにする。
`serve`、`launch`、未知のコマンドは拒否し、既知の client コマンドだけを正規 backend の稼働確認後に渡す。
Windows に渡す `OLLAMA_HOST` は loopback に固定し、既存の `WSLENV` の他の項目は残す。
Ollama 本体やモデルは持たず、NAT と `appendWindowsPath=false` を維持する。
ユーザーサービス内では、セッションごとの socket を設定に固定せず、利用可能な interop socket を確認する。

接続ごとに Windows の待受 PID と実行ファイルを確認し、`127.0.0.1:11434` を Scoop のフル版が所有している場合だけ接続する。
Windows が `::1:11434` に作る WSL の転送 listener は、Ollama の第2 backend とは数えない。
この例外は、保護された `Program Files/WSL/wslrelay.exe` の正確な配置、symlink でないこと、Microsoft の有効な署名を確認できる場合に限る。
同じ転送 listener が IPv4 の接続先を所有していても正規 backend の代わりにはせず、署名不明や wildcard の待受も認めない。
Windows の localhost 転送が WSL のブリッジへ戻る場合も、正規の Windows 所有者がない接続を拒否する。
同時転送は8接続、接続待ちは2秒とし、終了処理と子プロセスの回収まで接続枠を保持する。
Windows の socket timeout は方向ごとに300秒とする。
アップロードが続いていても、応答が300秒間届かなければ受信側は失敗する。
送信スレッドのエラーも失敗として伝え、stdout は転送データだけに使う。
ポートの競合時に既存のプロセスを停止したり、別のアドレスへ公開したりしない。

## Doctor の検査範囲

`just doctor` は `scripts/ollama_host.py --check` を呼ぶ。
検査は読み取り専用であり、修復やサービス起動は行わない。

- Windows のフル版と Scoop の bucket、既知の重複インストール、動作中の Ollama の実行ファイルを調べる。
- 待受 PID、ポート、アドレスから、本体の所有者と loopback 以外への公開を検査する。
- WSL の native binary、package、process、system/user service、モデル配置を調べる。
- ブリッジの管理対象 unit、実行ファイル、PID、待受 socket、転送後の version 応答を照合する。
- 停止中や接続不能の WSL は起動せず、未検査の WARN とする。プラットフォーム管理の distro も未検査と表示する。
- Windows が届かないだけで unit や socket が正しく管理されているブリッジは、構成違反ではなく通常の停止として WARN にする。identity や version の不一致は ERR のままである。
- WSL2 のカーネルを共有する Docker / Podman コンテナは Windows との相互運用を持たないため、この方針の適用外（該当なし）と判定する。

既知の配置や実行中のプロセスから外れた休眠コピーまで、存在しないと保証する検査ではない。
構成違反は ERR、検査不能や停止中の正規 backend は WARN とし、HTTP 応答だけで正しい所有者とは判定しない。
version 応答は通信の確認であり、Ollama のログイン状態や Pi の web 検索の成功とは別に確認する。

Windows 側を終了すると、WSL の接続は失敗する。
復旧は Windows のフル版を起動してから行い、代わりに WSL の `ollama serve` を起動しない。
