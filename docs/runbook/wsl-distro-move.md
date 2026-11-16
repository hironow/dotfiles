# WSL の distro を別のボリュームへ移す

self-hosted runner が動く WSL の distro の vhdx を、`wsl --manage <distro> --move` で別のボリュームへ移す手順。
C: が足りなくなったときに使う。
WSL 3.0.5（2026-11-03 の stable）で、Ubuntu の vhdx（論理 227 GB）を NVMe の C: から HDD の D: へ移したときの手順と、そこで分かったことをまとめる。

## 前に知っておくこと

- **sparse が外れる。** 別のボリュームへの move は、vhdx の sparse の属性を保たなかった。
  移動前は実占有 97 GB だったが、移動後は論理サイズと同じ 227 GB を占めた。移動先には論理サイズ分の空きが要る。
  外れた後に C: へ戻すと、C: にも論理サイズ分が要る。
- **移動先の ACL を継承する。** D:\ の既定の ACL は `Authenticated Users:(M)` と `Users:(GR,GE)` を子に継承させる。
  そのまま移すと、vhdx（distro 全体で、runner の認証情報を含む）を他のローカル利用者（たとえば Codex の sandbox の利用者）が開ける。
  移動先のフォルダーを先に作り、継承を切っておく。
- **export は distro に停止を求めてから書き出す。** 3.0.5 の `wsl --export` は、client が残っていても distro に停止を求め、最大 60 秒待つ。
  止まらなければ "Continuing without confirming that the distribution has stopped." と警告して、そのまま書き出す。
  runner を止めて `wsl --shutdown` を済ませておけば、この経路には入らない。
- **move の間は wsl.exe を呼ばない。** move はサービスの中でファイルを移す間、利用者ごとの instance lock を握る。
  その間の wsl.exe の呼び出し（`--list` や起動も含む）はすべて待たされる。固まったと誤解して `--shutdown --force` を打たない。
- **HDD でも CI は遅くならなかった。** 移動後の `pool-infra gate` は 25〜33 分で、移動前の SSD（34〜41 分）より短かった。
  ただし、計測は 1 晩分の job だけである。

## 手順

PowerShell（昇格しない）で実行する。Git Bash から `icacls` や `reg` を呼ぶと、`/inheritance:r` などの引数が Windows のパスに書き換えられる。

1. 移動先のフォルダーを作り、継承を切る。`<dest>` はたとえば `D:\wsl`。

    ```powershell
    New-Item -ItemType Directory D:\wsl, D:\wsl\backup
    $me = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    icacls D:\wsl /inheritance:r /grant:r "*${me}:(OI)(CI)F" "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F"
    icacls D:\wsl
    ```

    `"$env:USERDOMAIN\$env:USERNAME:(OI)(CI)F"` とは書かない。PowerShell は `$env:USERNAME:` までを 1 つの変数として読み、利用者名が空になる（`DESK\(OI)(CI)F`）。
    最後の `icacls D:\wsl` に、自分・SYSTEM・Administrators の 3 つだけが出て、`(I)`（継承）が 1 つも無いことを確かめてから先へ進む。
    `D:\wsl\<distro>` は作らない。move が作り、`D:\wsl` から継承する。

2. 戻すための材料を取る。Lxss のレジストリの、その distro の key を書き出す。

    ```powershell
    reg export "HKCU\Software\Microsoft\Windows\CurrentVersion\Lxss\{<distro の GUID>}" D:\wsl\backup\lxss-pre-move.reg
    ```

3. 実行中の job が無いことを確かめ、runner を止める（`pgrep -x Runner.Worker` が空になるのを待ってから `systemctl stop 'actions.runner.*'`）。
   GitHub の runner 一覧で offline になったことを確かめる。

4. keepalive のタスクを止め、WSL を止める。

    ```powershell
    Stop-ScheduledTask dotfiles-wsl-autostart
    wsl --shutdown
    ```

5. 退避の export を取る。数十分かかるので、呼び出し元のタイムアウトから切り離して実行し、終了コードをファイルに残す。
   PowerShell 5.1 の `Start-Process -PassThru` は、`-Wait` も handle の保持も無いと `ExitCode` が空になる。呼び出し演算子と `$LASTEXITCODE` を使う。

    ```powershell
    & wsl.exe --export <distro> D:\wsl\backup\<distro>-pre-move.tar *> export.log; $LASTEXITCODE | Set-Content export.rc
    ```

   `export.log` に `Timed out waiting` や `Continuing without confirming` があれば、失敗として扱う。
   tar は最後まで読めることを確かめる。Windows の `tar.exe` は、Unicode の名前の項目（Go の toolcache のテスト用ファイルなど）を読めずに rc=1 を返すことがある。
   その場合は Git Bash の GNU tar（`tar --warning=no-unknown-keyword -tf`）で数え直す。socket は tar に入らない（export のログに警告が出るが、問題ない）。

6. 門: distro が止まっていることを確かめる。`wsl --list --running --quiet` の出力は UTF-16 なので、`$env:WSL_UTF8='1'` を付け、NUL を除いて比べる。
   手順の前、distro が動いている間に、この比べ方で distro が見つかることを先に確かめておく。

7. 移す。手順 5 と同じく切り離して実行し、終了コードをファイルに残す。終わるまで wsl.exe を呼ばない。

    ```powershell
    & wsl.exe --manage <distro> --move D:\wsl\<distro> *> move.log; $LASTEXITCODE | Set-Content move.rc
    ```

8. 結果を確かめる。
    - レジストリの `BasePath` が新しい場所を指し、新しい vhdx があり、古い vhdx が無い。
    - C: の空きが、移す前の空き + 移した vhdx の実占有 くらいに増えた。
    - 新しい vhdx の ACL に `Users` や `Authenticated Users` が無い。sparse の状態と実占有を記録する。`just wsl-compact` がこの 2 つを表示する。

9. keepalive のタスクで distro を起こす（`Start-ScheduledTask dotfiles-wsl-autostart`）。
   次の項目で確かめる。古い起動の journal で合格しないよう、`journalctl -b` で今の起動に絞る。
    - `systemctl is-system-running` が running。
    - `systemctl --failed` が移す前と同じ。
    - runner のサービスの journal に `Connected to GitHub` と `Listening for Jobs`。
    - GitHub で online。
    - `just status` がすべて OK。
    - 既定の利用者と `df /` が移す前と同じ。
    - 最初の job が `Succeeded`。

## 戻し方

再試行を重ねない。出力を残し、まず読み取りで状態を確かめる。

- **move が失敗し、ファイルも `BasePath` も元のまま。** 何も変わっていない。移動先に残ったものを片付け、手順 9 から起こす。
- **move の処理が終わっていて、ファイルは新しい場所、`BasePath` は元の場所。** move はコピーの後にレジストリへの書き込みに失敗すると、ファイルを戻そうとする。
  sparse が外れて元のボリュームに入らなければ、戻しに失敗してこの状態になる。`BasePath` を新しい場所に書き換えて、手順 9 から起こす。
- **待ち役が生きていて、終了コードのファイルが無い。** move がまだ動いている。待つ。ファイルのサイズでは判断しない。
- **終了コードが 0 で、`BasePath` が新しい場所、元の vhdx も残っている。** コピーは済み、元の削除だけが失敗した（MoveFileEx の仕様）。
  手順 9 の確認が通ってから、元の vhdx を消す。
- **vhdx が壊れて起動しない。** このときに初めて、手順 5 の tar から `wsl --import` する（unregister を伴う）。
  `.wslconfig` に sparseVhd が無ければ、import した vhdx は sparse にならない。既定の利用者は `/etc/wsl.conf` の `[user] default=` で戻る。

## 片付け

- 退避の tar は、新しい場所で 1 週間ほど問題なく動いてから消す。
- スタートメニューの distro のアイコンは、元の場所の `shortcut.ico` を参照し続ける。元のフォルダーは、その 1 ファイルのために残る。
- 移動の後、`%TEMP%\<VM の GUID>\swap.vhdx` に古い VM の swap が残ることがある。動いている VM の GUID（`wslhost.exe --vm-id`）以外のものは消してよい。
