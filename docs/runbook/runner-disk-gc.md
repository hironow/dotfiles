# self-hosted runner のディスク GC

self-hosted runner を載せた機体（native Windows と WSL）のディスクを回収する仕組みと、その変更時に踏みやすい罠をまとめる（ADR 0035）。
`scripts/runner_gc*`、`just runner-gc*`、`just status`、`just disk-gc`、`just wsl-compact` を変える前に読む。

## なぜ回収が要るのか

runner を載せた WSL の `ext4.vhdx` には、コンテナの画像、停止したコンテナ、ビルドキャッシュが積み上がる。管理する実行系は Podman 5 以降に限定する（ADR 0067）。既存 Docker の在庫は操作しない。
放置すると C: が尽き、空きがないと vhdx を広げられず WSL 自体が起動しなくなる（`I/O error @util.cpp` から systemd の起動失敗）。
この状態は、容量を空けるための WSL が起動しないので自力では抜けられない。

`just runner-gc-install` は、`RUNNER_GC_RETENTION`（既定 2 時間）を保持期間とする GC を、次のとおり仕掛ける。コンテナと画像は作成時刻、workspace は後述の利用記録で判定する。ビルド・mount キャッシュは自動回収しない。従来のキャッシュ増大防止保証は継承しないので、容量監視は引き続き必要である。

- **job-completed hook**：ジョブの終了ごと
- **hourly timer**：1 時間ごと（root で動く）
- **journald の上限**：ログの肥大を止める（`RUNNER_GC_JOURNAL_MAX`、既定 `200M`）
- **`dotfiles-wsl-autostart`**（Windows のログオン時のタスク）：再起動のあと、distro の systemd（runner と GC の timer）を起こし直す

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

## Podman の回収

GC は Podman CLI と選択先の実行系を別々に調べ、両方が 5 以降であることを求める。Unix は `jq` も必要である。利用不可・版や情報の不明な場合は Podman の在庫を残してログに記録する。Docker への切替、socket の推測、machine の初期化・起動・更新はしない。`podman info --format json` の `version.Version` は選択先の版であり、CLI の版ではない。`host.serviceIsRemote=false` のローカル実行も有効である。

rootful と rootless の在庫は所有者ごとに異なる。root の timer は root の回収に加え、runner ディレクトリの所有ユーザーとして回収し直す（`runuser`、`HOME`、`XDG_RUNTIME_DIR`）。親からの `CONTAINER_HOST` と `CONTAINER_CONNECTION` は引き継がず、そのユーザーの接続設定を使う。rootless の再実行は Podman 部分だけで、workspace や apt の回収を繰り返さない。

### 削除条件

保持期間は非負の十進整数と `s`／`m`／`h`／`d`（省略時は秒）を受け付ける。先頭のゼロは八進数にせず、`08h` も有効である。明示的な `0` は従来どおり保持時間ゼロを指定する。時計の取得失敗・不正値・Unix の符号付き整数範囲外、または Unix epoch より前まで遡る過大な保持期間では、コンテナと画像をどちらも残して診断を出す。Unix の `invalid or excessive retention`／`invalid clock`／`clock query failed`／`clock outside signed range` が出たら設定と時計を確認する。積を計算する前に上限を調べ、桁あふれで保持時間を短くしない。この検証は Podman 部分のもので、workspace 等の既存方針は変えない。

画像 ID は小文字の完全な 64 桁の十六進数か、`sha256:` をその前に付けた形だけを受け付ける。列挙結果・画像の検査結果・コンテナの画像参照を同じ形に正規化して比べる。短縮 ID や不明な形式は削除に使わない。コンテナ自身の ID は別に一致を確認する。

- コンテナと画像は別々に列挙する。列挙失敗では該当する回収を中止する。コンテナの参照情報が欠けた場合も画像を残す。
- コンテナは停止状態かつ作成時刻が保持期間より古いものだけを、強制せず `podman rm <ID>` で削除する。確認後に起動したコンテナは実行系が削除を拒む。volume は削除しない。
- 画像は作成時刻、全 `RepoTags`、コンテナ参照を調べる。情報の取得・解析に失敗した画像は残す。削除直前に画像の情報をもう一度読む。
- 作成時刻 `Created` は Podman が書いた文字列のまま読む。文字列でない値は年齢不明として残す。Windows で GC を動かすのは Windows PowerShell 5.1 で、5.1 は JSON の日付を文字列のまま返す。PowerShell 7.5 以降でも `ConvertFrom-Json -DateKind String` で同じく文字列として読む。7.0〜7.4 は対象外である。日付と読めた `Created` を `DateTime` に変えるので、その項目は残す（安全側に倒れる）。日付と読めない形（ナノ秒付きなど）は文字列のまま通常の検査を通る。
- `RUNNER_GC_KEEP_TAG_PREFIX`（既定 `keep/`）に一致する別名が一つでもあれば、画像全体を残す。`keep/model:latest` と `localhost/keep/model:latest` は同じ保護対象になる。任意の prefix と、レジストリを含む名前も指定できる。
- 削除は個別の `podman rmi --no-prune <ID>` だけで行う。強制削除も親画像への連鎖削除もしない。新しいコンテナ参照や複数タグを理由に削除を拒まれた画像は、そのまま残す。

保護用のタグは `podman tag <image> keep/<name>` で付ける。最後の確認後に第三者がタグを付け替える競合を、原子的に防ぐ保証はない。新しいコンテナ参照を非強制削除が拒むことと、タグの競合は別の保証である。ジョブ検出も観測時点の判定であり、全プロセスを排他する lock ではない。

`system`／`builder`／`buildx` の prune、画像の一括 prune、mount キャッシュの掃除は呼び出さない。確認した Podman 6.1.4 では `image prune --all` または `--build-cache` が画像の期限とは別に永続キャッシュを削除するため、安全な期限付き回収に置き換えたとは言わない。

### 制限付き実行と検証

Unix の `RUNNER_GC_PODMAN_ONLY=1` は Podman 部分だけを実行する。`RUNNER_GC_DRY_RUN=1` はこの制限を有効にし、削除せず候補を表示する。他の janitor の dry-run ではない。Windows は `-PodmanOnly`、`-SkipPodman`、`-DryRun`、`-PodmanTimeoutSec`（既定 300 秒）を使う。全 CLI 呼出しに watchdog を適用し、期限切れではプロセスツリーを終了させる。

旧名 `RUNNER_GC_DOCKER_ONLY=1`、`-SkipDocker`、`-DockerTimeoutSec` は、削除範囲を広げない互換指定として残す。Docker を使う指定ではない。旧 ONLY と新 ONLY のどちらかが `1` なら制限を維持する。

モデル、実装との対応、偽 I/O による seed 再生は [Podman GC の検証範囲](../plan/podman-gc.md) を参照する。テストは本物のエンジンや在庫に接続しない。

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

vhdx が sparse でない機体では、`fstrim` は C: に何も返さない（実例は memory `project_this_host_vhdx_non_sparse`）。
その場合の返却には、管理者権限と `wsl --shutdown`（runner の停止）が要るので、`just wsl-compact` は計測と手順の表示にとどめる。
`wsl --manage --set-sparse` は自分では有効にしない（Microsoft がデータ破損の危険から無効にしており、`--allow-unsafe` が要る）。
すでに sparse な vhdx で `fstrim` を使うのは別の話で、こちらは安全である。

余り（slack）は実際の占有量（`du -B1`）で測る。
`stat -c %s` は論理サイズ（最高水位で、減らない）なので、「論理サイズ - 使用量」はすでに返した分まで余りに数えてしまう。
`just wsl-compact` は sparse の状態（`fsutil sparse queryflag`）も表示する。

## 開発用キャッシュ

コンテナ以外にも大きく育つのは開発用のキャッシュである（`~/.cache/uv` だけで数十 GB になる）。
`just disk-gc` は、WSL の runner ユーザの HOME まで掃除する（`DISK_GC_NO_WSL=1` で止める）。
対話作業と共有する場所なので、hourly timer には載せない。
`~/.cache/huggingface` は既定では対象外である（`DISK_GC_HUGGINGFACE=1` で含める。1 つのモデルで数十 GB あり、取り直しの重さが wheel とは違う）。

## Windows から WSL へのコマンドの渡し方

Windows から WSL の GC を呼ぶときは、`MSYS_NO_PATHCONV=1` と `MSYS2_ARG_CONV_EXCL='*'` を付ける（対象の distro は `RUNNER_GC_WSL_DISTRO`、既定 `Ubuntu`）。
付けないと、Git Bash が `/usr/local/bin/...`、`/mnt/c/...`、素の `/` まで Windows のパスに書き換えてから `wsl.exe` に渡す。
