# Windows と WSL の Ollama を一本化する

Windows と WSL が共存する機体では、Scoop の `extras/ollama-full` だけを Ollama 本体として使う（[ADR-0062](../adr/0062-one-windows-ollama-for-wsl.md)）。
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

### 単独インストーラ版を外すときはモデルを先に移す

単独インストーラ版（`%LOCALAPPDATA%\Programs\Ollama`）のアンインストーラは、既定パス `%USERPROFILE%\.ollama\models` のモデルを消す。
既定パスに `models\blobs` があると「Remove models」を既定で選び、`/VERYSILENT` でもそのまま `models\blobs` と `models\manifests` を消す。
`OLLAMA_MODELS` は見ない。
既定パスに別のドライブへのリンク（ジャンクションやシンボリックリンク）があると、リンク先の実体も同じように消える。
ごみ箱は通らない。

アンインストールの前に、次の順で進める。

1. Ollama をすべて終了する。
2. 既定パスのモデルを別のドライブへ写し、各ブロブの SHA-256 がファイル名と一致することを確かめる。
3. User 環境変数 `OLLAMA_MODELS` で写し先を指し、新しく開いた端末で `ollama list` の digest が元と同じことを確かめる。
4. 既定パスにはフォルダもリンクも残さない。見るためのリンクは別の名前で作る。
5. アンインストールした後に、写し先をもう一度照合する。

画面の「Remove models」を外すだけに頼らない。既定のままの実行や `/VERYSILENT` では消える。

## WSL 側の共有

WSL の網の形は、WSL の中で `wslinfo --networking-mode` を読んで決める（WSL 2.0.4 以降）。
`nat` なら、この節のブリッジを置く。
`mirrored` なら、ブリッジを置かない（次の節）。
それ以外か読めない時は、ブリッジを作らずに止まる。`wsl --update` で WSL を新しくする。

NAT の WSL では、`just deploy` が Pi の拡張導入時にユーザーの `ollama-windows-bridge.service` を設定する。
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
Ollama 本体やモデルは持たず、`appendWindowsPath=false` を維持する。
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

## mirrored の WSL（loopback を Windows と共有する）

`.wslconfig` で `networkingMode=mirrored` にした WSL は、`127.0.0.1` を Windows と共有する（[ADR-0064](../adr/0064-mirrored-wsl-uses-the-shared-loopback.md)）。
WSL から `127.0.0.1:11434` に繋ぐと、ブリッジ無しで Windows の本体に届く。
ここにブリッジを置くと、Windows の本体と同じ番号を取り合うので置かない。
dotfiles は `.wslconfig` を変えない。

mirrored の `just deploy` は、CLI の口 `~/.local/bin/ollama` とヘルパーだけを置き、ブリッジの unit は書かない。
ブリッジの unit が有効か動いている、ブリッジのプロセスがいる、WSL に 11434 の待受がある、のどれかなら、何も変えずに止まる。
それらの状態を読めない時も止まる。
NAT から mirrored に変えた機体では、先に古いブリッジを止める。

```bash
systemctl --user disable --now ollama-windows-bridge.service
just deploy
just doctor
```

古いブリッジが手で起こされても、mirrored では待ち受けずに終わる。
CLI の口は、mirrored でも Windows 側の所有を確かめてから Windows の CLI を呼ぶ。

WSL の doctor は、次の順で確かめる。
途中で外れたら、通信を1回もしない。

1. 網の形が mirrored と決まった。
2. WSL の待受の調べが成功し、11434 の待受が無い。
3. Windows で `127.0.0.1:11434` を持つのが正規の本体だと確かめた。
4. WSL から `127.0.0.1:11434/api/version` を1回聞き、Windows と同じ版が返る。

Windows の doctor が WSL の中で走らせる調べは、Windows 側の判定を受け取らないので、通信しない。
HTTP で直接 `localhost:11434` に繋ぐ道具（Pi の web 検索など）は、ブリッジの接続ごとの確認を通らない。
これは mirrored の網の性質で、その代わり doctor が上の順で確かめる。
本体は IPv4 の loopback だけで待ち受けるので、`localhost` を先に `::1` で試す道具は、断られてから `127.0.0.1` に落ちる。

## tailnet の中だけの Tailscale 転送を認める（宣言した機体だけ）

所有者が、Tailscale の TCP 転送で 11434 を tailnet に出すと決めた機体がある（例: `tailscale serve --bg --tcp=11434 tcp://localhost:11434`）。
その機体では、ユーザーの宣言ファイルを置くと、転送を2つ目の本体とも公開とも数えない（[ADR-0063](../adr/0063-declared-tailnet-forward-of-ollama.md)）。

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.config\dotfiles" | Out-Null
Set-Content -NoNewline "$env:USERPROFILE\.config\dotfiles\ollama-tailnet-forward" '11434'
```

宣言はユーザー単位の設定の選択で、本人に対する認可の境界ではない。
ファイルを消せば、元の判定（転送の待受は ERR）に戻る。
宣言の無い機体では、Tailscale のコマンドを1回も実行しない。
dotfiles は Tailscale の設定を作りも消しもしない。

宣言があっても、次をすべて満たす待受だけを認める。
1つでも読めない・調べられない時は認めない。

- ポートが 11434。
- 待受のプロセスが、動いている Tailscale サービスそのものか、その直接の子の `tailscaled.exe`。子の時は、親の作成時刻が子より前。確かめた後でサービスの pid を読み直し、変わっていない。
- サービスの実行ファイルが `%ProgramFiles%\Tailscale\tailscaled.exe` で、そのファイルと親フォルダがリンクでなく、Tailscale Inc. の有効な署名がある。CLI の `tailscale.exe` も同じ検証の後で使う。
- 待受のアドレスが、`tailscale ip` が返すこの機体のアドレスで、`100.64.0.0/10` か `fd7a:115c:a1e0::/48` に入る。
- serve の設定のどこにも（foreground のセッションを含む）有効な Funnel（`AllowFunnel`）が無い。
- 11434 の転送先が `127.0.0.1:11434`、または `[::1]:11434` に待受が無い時の `localhost:11434`。11434 を別の handler（foreground、Tailscale Services、web、Tun）が持たず、ほかの転送や web の proxy が 11434 を指さない。

認めた転送は、doctor に `OK ollama-tailnet-forward` と出る。
宣言があるのに認めなかった待受は、`ERR ollama-tailnet-forward` に理由が出て、公開の ERR も残る。
tailnet の ACL（`tofu/tailnet/acl.hujson`）は、どの機体にも Funnel を許していない。

## Doctor の検査範囲

`just doctor` は `scripts/ollama_host.py --check` を呼ぶ。
検査は読み取り専用であり、修復やサービス起動は行わない。
Windows の調べのスクリプトは、Windows のコマンド行の長さの上限（32,767 文字）を超えるので、標準入力で PowerShell に渡す。

- Windows のフル版と Scoop の bucket、既知の重複インストール、動作中の Ollama の実行ファイルを調べる。
- 待受 PID、ポート、アドレスから、本体の所有者と loopback 以外への公開を検査する。宣言した機体では、tailnet の中だけの Tailscale 転送を確かめ、認めた物は公開と数えない。
- WSL の native binary、package、process、system/user service、モデル配置を調べる。
- NAT の WSL では、ブリッジの管理対象 unit、実行ファイル、PID、待受 socket、転送後の version 応答を照合する。mirrored の WSL では、上の順で共有の loopback を確かめる。網の形が分からない WSL は WARN にする。
- 停止中や接続不能の WSL は起動せず、未検査の WARN とする。プラットフォーム管理の distro も未検査と表示する。
- Windows が届かないだけで unit や socket が正しく管理されているブリッジは、構成違反ではなく通常の停止として WARN にする。identity や version の不一致は ERR のままである。
- WSL2 のカーネルを共有する Docker / Podman コンテナは Windows との相互運用を持たないため、この方針の適用外（該当なし）と判定する。

既知の配置や実行中のプロセスから外れた休眠コピーまで、存在しないと保証する検査ではない。
構成違反は ERR、検査不能や停止中の正規 backend は WARN とし、HTTP 応答だけで正しい所有者とは判定しない。
version 応答は通信の確認であり、Ollama のログイン状態や Pi の web 検索の成功とは別に確認する。

Windows 側を終了すると、WSL の接続は失敗する。
復旧は Windows のフル版を起動してから行い、代わりに WSL の `ollama serve` を起動しない。
