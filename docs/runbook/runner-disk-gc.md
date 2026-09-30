# self-hosted runner のディスク GC

self-hosted runner を載せた機体（native Windows と WSL）のディスクを回収する仕組みと、その変更時に踏みやすい罠をまとめる（ADR 0035）。
`scripts/runner_gc*`、`just runner-gc*`、`just status`、`just disk-gc`、`just wsl-compact` を変える前に読む。

## なぜ回収が要るのか

runner を載せた WSL の `ext4.vhdx` には、docker の image、停止したコンテナ、BuildKit の build cache が上限なく積み上がる（既定では GC の方針がない）。
放置すると C: が尽き、空きがないと vhdx を広げられず WSL 自体が起動しなくなる（`I/O error @util.cpp` から systemd の起動失敗）。
この状態は、容量を空けるための WSL が起動しないので自力では抜けられない。

`just runner-gc-install` は、2 時間より古いものを回収する GC を 3 つの契機で仕掛ける。

- **job-completed hook**：ジョブの終了ごと
- **hourly timer**：1 時間ごと（root で動く）
- **journald の上限**：ログの肥大を止める

状態は `just status` で確かめる。
Windows と WSL の両方について、timer、タスク、hook を一度に表示し、hook が runner に受理される形式か、直近のジョブで拒否されていないかまで見る。

## hook の登録

runner は hook のパスを検証し、拡張子が `.sh`、`.ps1`、`.js` でないものを `ArgumentException: ... is not a valid path to a script` で拒否する。
値はパスでなければならず、`powershell.exe -File <script>` のようなコマンド行も同じ検証で落ちる。
拒否はジョブ自身の Worker ログにしか残らず、journal にもタスクの履歴にも出ないので、`just status` の受理確認に頼る。

## 実行中のジョブの検出

ジョブの検出には `pgrep -x Runner.Worker` を使う。
`pgrep -f` は GC 自身のコマンド行にも一致し、「常にジョブが実行中」と判定して GC を黙って止め続ける。

hook は `Runner.Worker` の内側から呼ばれるので、単純に検出すると、自分を起動したジョブを理由に毎回スキップしてしまう。
プロセスの祖先と突き合わせ、祖先でない worker（同時に走る別のジョブ）がいるときだけ退避する。

## docker の回収

rootless docker の機体では、root の timer が別の daemon を掃除してしまう。
root の context は `/var/run/docker.sock`（rootful）に解決するが、実際の在庫は `/run/user/<uid>/docker.sock`（rootless）にある。
`docker info` は空の rootful でも成功するので、回収ゼロのまま exit 0 で終わる。
そこで GC は、root で実行されたときに runner ディレクトリの所有ユーザで docker の回収をやり直す（`runuser` と `XDG_RUNTIME_DIR`）。
root 自身の回収も残すので、rootful だけの機体には影響しない。

## toolcache の回収

workflow は `go-version: 1.25.x`、`node-version: 22.x`、`python-version: 3.13` のように系列を固定し、`setup-*` は系列の中の最新の patch を使う。
そのため「新しい順に N 世代を残す」回収は、matrix が使う版を消してしまう（1 台の runner で Python の 3 系列が現役ということもある）。
GC は `major.minor` の系列ごとに最新の patch を残し、系列の数を `RUNNER_GC_TOOLCACHE_KEEP`（既定 5）で抑える。

- 並べ替えは `sort -V` で行う。辞書順では `1.25.8` が `1.25.11` より後に来て、最新版を消す。
- 削除は `<version>/` のディレクトリごと行う。内側に `<version>/<arch>.complete` の目印があるので、部分的に消すと「キャッシュ済みなのに実体がない」状態になる。
- 最後に使った時刻は取れないので、時間ではなく系列で判定する（`relatime` のもとでは、`_tool` をたどる処理が atime を書き換え、mtime は導入時刻にすぎない）。
- この回収だけは、`RUNNER_GC_FORCE=1` でもジョブの実行中は行わない（使用中の toolcache を消すとジョブが即座に失敗する）。

## workspace の回収

`_work/<repo>` の checkout は、Windows でも WSL でも toolcache より大きく育つので、両方で回収する。
期限は、GC 自身が押す `.runner-gc-last-used` の目印で判定する。
ディレクトリの mtime は、深い階層での再ビルドを反映しない（Linux は直下の増減しか追わず、Windows は入れ子のファイル更新で親の `LastWriteTime` を更新しない）ので使わない。

- runner が所有するディレクトリは名前で列挙して除外する（`_` で始まるかで判定すると、`_foo` という名前の実リポジトリを永久に残してしまう）。
- `RUNNER_WORKSPACE` と `GITHUB_WORKSPACE` が指す checkout は、無条件に残す（hook がステップの間に動いても、実行中のジョブを消さない）。
- `RUNNER_GC_ROOT` で 1 つの install だけを対象にできる（忙しい runner は空き時間が来ないので、破壊的な経路を合成した root で検証するため）。
- ジョブの実行中に走らせるには、`RUNNER_GC_ROOT` と `RUNNER_GC_ALLOW_BUSY=1` の両方が要る（`RUNNER_GC_FORCE` では代わらない）。root の指定は「どの install か」の宣言であって、「触ってよい」の保証ではない。手動実行には `RUNNER_WORKSPACE` がなく、実行中のジョブがいま書いている checkout を見分けられないからである。

native Windows で workspace を消すには、素の `Remove-Item` では足りない。
junction（PowerShell 5.1 の `-Recurse` はリンクをたどってリンク先まで消す）、読み取り専用の `.git/objects`、MAX_PATH を超えるパス（`node_modules`）があるためである。
reparse point を先に再帰なしで外し、読み取り専用を解除し、残りを `robocopy /MIR /XJ` で消す、という順に行う。

## runner の自己更新の残骸

`_work/_update` と、古い `bin.*`、`externals.*` は、24 時間の別枠で回収する（2 時間では進行中の自己更新を巻き込む）。
古い版を消すのは、`bin` と `externals` が symlink として解決できるときだけである。
通常の install では `bin.*` が runner の本体なので、消すと壊れる。

## vhdx から C: への返却

WSL の中で消しても、C: の空きは増えない。
vhdx は解放済みの ext4 のブロックを Windows 側で抱えたままなので、返却するのは `fstrim` である。
WSL の vhdx は通常 sparse なので、`fstrim /` で穴をあければ、止めずに管理者権限なしで返せる。
GC は root での回収の最後に `fstrim` を実行する。

vhdx が sparse でない機体では、`fstrim` は C: に何も返さない。
その場合の返却には、管理者権限と `wsl --shutdown`（runner の停止）が要るので、`just wsl-compact` は計測と手順の表示にとどめる。
`wsl --manage --set-sparse` は自分では有効にしない（Microsoft がデータ破損の危険から無効にしており、`--allow-unsafe` が要る）。
すでに sparse な vhdx で `fstrim` を使うのは別の話で、こちらは安全である。

余り（slack）は実際の占有量（`du -B1`）で測る。
`stat -c %s` は論理サイズ（最高水位で、減らない）なので、「論理サイズ - 使用量」はすでに返した分まで余りに数えてしまう。
`just wsl-compact` は sparse の状態（`fsutil sparse queryflag`）も表示する。

## 開発用キャッシュ

実際に大きく育つのは docker よりも開発用のキャッシュである（`~/.cache/uv` だけで数十 GB になる）。
`just disk-gc` は、WSL の runner ユーザの HOME まで掃除する（`DISK_GC_NO_WSL=1` で止める）。
対話作業と共有する場所なので、hourly timer には載せない。
`~/.cache/huggingface` は既定では対象外である（`DISK_GC_HUGGINGFACE=1` で含める。1 つのモデルで数十 GB あり、取り直しの重さが wheel とは違う）。

## Windows から WSL へのコマンドの渡し方

Windows から WSL の GC を呼ぶときは、`MSYS_NO_PATHCONV=1` と `MSYS2_ARG_CONV_EXCL='*'` を付ける。
付けないと、Git Bash が `/usr/local/bin/...`、`/mnt/c/...`、素の `/` まで Windows のパスに書き換えてから `wsl.exe` に渡す。
