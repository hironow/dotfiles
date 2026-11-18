# 対話セッションの scheduled task を、窓を出さずに起こす（第 4 版）

日付：2026-11-18（JST）

所有者の依頼（2026-11-18）：Windows で CI やチェックを回すと、ターミナルが一瞬出る。どれが出しているかを点検し、直す。点検の結果を見た所有者が「はい進めてください」と答えた。この計画は、直し方の 1 番（scheduled task）である。

第 1 版は `conhost.exe --headless` で包む案だった。Codex のレビュー（下の「レビューの記録」）で、exit code が消えて status の FAIL が出なくなることと、走っている古い keepalive を切り替える手順が無いことが分かった。第 2 版は、exit code を返す小さな launcher を Go で作る案に変えた。第 3 版は、2 回目のレビューを受けて、launcher を中身の hash ごとの置き場所にし、機の作業を昇格した terminal で行うことにし、戻し方を新しいコードに頼らない手順にした。第 4 版は、3 回目のレビューを受けて、installer に古い instance を止める処理を足すのをやめ、切り替えも戻し方と同じ、一時の client で distro を保つ手順にした。launcher の確かめは、どの task を消すよりも前に行う。

## 事実（点検と実験で確かめたこと）

- `dotfiles-runner-watchdog` は、5 分ごとと logon のたびに `powershell.exe` を Interactive の principal で起こす（`scripts/runner_watchdog_win.ps1:102-113`）。
    - 窓を隠すものは何も付いていない。
    - この機の `%TEMP%\runner-watchdog-win.log` には、5 分ごとの行がある（04:48、04:53、04:58、05:03）。
    - 所有者の見た「一瞬のターミナル」は、まずこれである。
- `dotfiles-wsl-autostart` は、logon のたびと install の時に `powershell.exe` を起こす（`scripts/install_runner_gc_win.ps1:159-183`）。
    - principal を指定しないので、所有者の session で動く。
    - payload は最後に WSL の keepalive として止まらずに残る（`scripts/wsl_autostart.ps1:139-142`）。そのため窓が開いたままになる。
    - その窓を閉じると keepalive が切れ、WSL は約 1 分で止まる。
    - payload の記録は `Write-Host` だけで、ファイルには残らない（`wsl_autostart.ps1:61-63`）。
- `dotfiles-runner-gc` は、この機では S4U（logon していなくても動く形）で、窓は出ない。UAC を断った時の Interactive の登録（`install_runner_gc_win.ps1:126-131`）では、毎時窓が出る。status はこの task の `LastTaskResult` を読む（`scripts/gc_status.sh:218-222`）。
- status は、autostart の結果が 0 でも 267009（実行中）でもない時に FAIL にする（`gc_status.sh:245-250`）。keepalive が居ないことは WARN にとどまる（`gc_status.sh:183-188`）。つまり、payload の exit code が task の結果に出ることが、失敗を FAIL にする前提である。
- 実験（2026-11-18、この機。Windows 11 26300）：
  1. `conhost.exe` は、`--headless` の有無によらず、子の exit code を返さない（子が 7 で終わっても 0）。Task Scheduler から起こした時も、task の結果は 0 だった。→ conhost の案はやめた。
  2. 窓の無い親から起こされた子は、console はあっても窓を持たない。この shell から起こした `powershell.exe` は `GetConsoleWindow()` が 0 で、そこから `wsl.exe` も普通に動く。Windows の `CREATE_NO_WINDOW`（0x08000000）で子を起こすと、この状態になる（Microsoft の説明では「console の窓を持たない console process」）。所有者の別の repo も、worker をこの flag で起こしている。
- 走っている task の instance は、登録を消しても止まらない（Microsoft の `schtasks /delete` の説明）。今の installer は autostart を登録し直すが、走っている古い instance を止めない。新しい payload は、keepalive がもう居ると「nothing to do」で終わる（`wsl_autostart.ps1:91`）。そのままでは古い窓が残り、切り替わらない。
- Task Scheduler は、task を止める時と時間の上限の時に、task の process の木を止める（installer の前提、`install_runner_gc_win.ps1:164-166` の comment）。機の作業で、切り替えの後に古い keepalive が残っていないことを確かめる。
- dotfiles の CI の Windows の job は、どれも GitHub の `windows-latest` で、この機の desktop には出ない。新しい Go の module は、`windows-go` の job（`just go-test go`、`tools/**/go.mod` を拾う）で自動で試される。

## 設計

- **`tools/run-hidden`**（Go、標準ライブラリだけ）：`run-hidden.exe <program> [args...]`。
    - Windows の GUI subsystem で build する（`-ldflags=-H=windowsgui`）。自分は console を持たないので、Task Scheduler から起こしても窓が出ない。
    - 子を `CREATE_NO_WINDOW` で起こし、終わるのを待ち、子の exit code をそのまま自分の exit code にする（Task Scheduler の結果にそのまま出る）。
    - 子の標準入出力は NUL につなぐ（今も task の窓は誰も読んでいない）。
    - 引数が無ければ exit 2、子を起こせなければ exit 1（どちらも task の結果に出る）。
    - Windows 以外では何もせず exit 2 で断る（使う所が無い）。
    - 名前の `hidden` は Windows の用語（`SW_HIDE`、`-WindowStyle Hidden`）に合わせた。
- **build と置き場所**：
    - recipe `run-hidden-build` が `output/run-hidden/run-hidden.exe` に build する（ほかの道具と同じ `CGO_ENABLED=0 GOTOOLCHAIN=local mise exec -- go build -trimpath`）。Windows 以外では何もしない。
    - installer は、それを `%LOCALAPPDATA%\dotfiles\run-hidden\<SHA-256 の先頭 16 桁>\run-hidden.exe` に写し、task はその写しを起こす。
        - 作業ツリーの branch に依らない（watchdog の写しと同じ理由、ADR 0042）。
        - 置き場所が中身で決まるので、走っている exe（autostart の launcher は keepalive を待って動き続ける）を上書きしない。同じ中身なら写さずにその path を使い、中身が変われば新しい dir に写して、task の action をそこへ切り替える。古い dir は消さない（所有者の片付け）。
        - 写す時は一時の名前に写し、hash を確かめてから正しい名前にする。dir の名前と中身の hash が合わない写しがあれば、install を止める。
    - 写す処理は `scripts/run_hidden_win.ps1` の関数 1 つにし、2 つの installer が dot-source する。
    - 写す元が無ければ、install を止めて `just run-hidden-build` を案内する。
- **3 つの task の action**：`dotfiles-runner-watchdog`、`dotfiles-wsl-autostart`、`dotfiles-runner-gc` の action を、`-Execute <run-hidden の写し> -Argument '"<powershell.exe>" <今と同じ引数>'` にする。payload、引数、trigger、principal、settings は変えない。GC も包む。S4U では今も窓は出ないが、UAC を断った時の Interactive の登録でも窓が出なくなり、exit code は今までどおり task の結果に出る。
- **autostart の切り替え**：installer には、走っている instance を止める処理を足さない。
    - 止めた後に登録や起動が失敗すると、distro が最後の client を失って止まり、走っている runner の job を巻き込む。installer の中でそれを戻す処理は重い。
    - run-hidden に替えた後は、古い instance が走り続けても窓は無く、害も無い（新しい payload は keepalive を見て終わる。今と同じ）。
    - すぐに切り替えたい時（今回の移行と、launcher の版が変わった時）は、下の「機の作業」の手順で、一時の client で distro を保ってから止める。戻し方も同じ手順である。この手順は runbook に書く。
- **確かめの順番**：installer は、launcher の写しと hash の確かめ、payload の有無を、どの task を消すよりも前に行う。今の GC の installer は先に task を消すので（`install_runner_gc_win.ps1:51-61`）、写しが失敗すると task が消えたままになる。
- **autostart の log**：`wsl_autostart.ps1` の `Write-Log` は、`Write-Host` に加えて `%TEMP%\wsl-autostart.log` にも書く。watchdog の `Write-WdLog` と同じく、1 MB を超えたら末尾の 200 行に切り詰める。
- **status**：3 つの task のどれかの action が `run-hidden.exe` を起こしていなければ、WARN を出す（「起こすたびに console の窓が出る。昇格して install し直す」）。手を動かすべきことなので WARN にする（ADR 0066）。今の FAIL の判定は変えない（exit code が task の結果に出続けるので）。
- **ADR**：新しい ADR（Proposed）に、「dotfiles が登録する Windows の scheduled task は、run-hidden を通して起こす」を書く。却下した案と理由：
    - `-WindowStyle Hidden`：console ができてから隠すので一瞬出る。
    - `conhost --headless`：exit code が消える。
    - 全部 S4U：登録に昇格が要る。S4U の session から `wsl.exe` の keepalive が動くかは確かめていない。
    - VBScript：Windows が廃止に向けている。
    - `docs/decision-queue.md` に行を足す。決めるのは所有者。

## 進め方（TDD）

1. **Red**（落ちることを確かめてから Green へ）：
   - Go（`tools/run-hidden`、windows の build tag）：
     - `cmd.exe /c exit 7` を起こすと 7 を返す。
     - 子（test binary 自身を helper として起こす）の `GetConsoleWindow()` が 0 か、`IsWindowVisible` が false。
     - 引数なしは 2。
     - 無い program は 1。
     - Windows 以外では 2。
   - `tests/unit/test_run_hidden_install.py`（pwsh で `scripts/run_hidden_win.ps1` の関数を動かす。置き場所の root は `tmp_path`）：
     - `<root>\<hash16>\run-hidden.exe` に写して、その path を返す。
     - 同じ中身でもう一度呼ぶと、同じ path を返し、写し直さない（更新時刻が変わらない）。
     - 中身が違えば、新しい dir に写し、古い dir の写しはそのまま残る。
     - 元が無ければ、`just run-hidden-build` を含む誤りで止まる。
     - dir の名前と中身の hash が合わない写しがあれば止まる。
   - `tests/unit/test_runner_mode_win.py`：
     - watchdog の action が、その関数の返す path を起こし、`-Argument` の先頭が powershell のパスで、残りは今と同じ（installed copy の `-File`）。
   - `tests/unit/test_wsl_autostart.py`：
     - autostart と GC の action も同じ形。
     - 2 つの installer で、launcher を写す関数の呼び出しが、最初の `Unregister-ScheduledTask` より前にある。
     - installer は `Stop-ScheduledTask` を呼ばない（切り替えは手順で行う）。
     - pwsh で payload を動かすテストで、`TEMP` を `tmp_path` にし、`%TEMP%\wsl-autostart.log` に `Write-Log` の行が残る。既存の `_run_payload` も `TEMP` と `TMP` を `tmp_path` にして、本物の `%TEMP%` に書かない。
   - `tests/unit/`：
     - recipe `run-hidden-build` が `-H=windowsgui` で build する。
     - `runner-watchdog-install`、`runner-mode-interactive`、`runner-gc-install` がそれを先に呼ぶ。
     - status が 3 つの task の action を見て WARN を出す。
2. **Green**：上の設計のとおりに書く。
3. **文書**：
   - `docs/runbook/windows-host.md` に「対話セッションで動く scheduled task」の節を足す（なぜ run-hidden か、却下した案、登録し直しに昇格が要ること）。
   - `docs/runbook/runner-disk-gc.md` の autostart の行に log の場所を足す。
   - ADR と decision queue。
4. 確かめ：
   - `just ci` と `just check`（この機）。
   - PR の CI（`windows-go` が run-hidden の Go のテストを Windows で回す）。
5. 機の作業（merge の後。所有者の承認が要る。どちらも**所有者が開いた、昇格した terminal** で行う）：
   - この機の 3 つの task は昇格した context で登録されている。unelevated の installer は消せないので「keeping it as-is」で残し、GC の UAC の経路にも進まない（`install_runner_gc_win.ps1:51-61,84`）。そのため、unelevated の実行では切り替わらない。
   1. watchdog：昇格した terminal で `just runner-watchdog-install`（runner の listener は起こし直さない）。watchdog は数秒で終わる task なので、止める手順は要らない。
   2. autostart と GC（切り替えの手順。戻し方と同じ形）：
      1. 別の terminal で、一時の client を起こして distro を保つ：`wsl.exe -d Ubuntu-26.04 -e sleep 900`。
      2. autostart が Running なら `Stop-ScheduledTask dotfiles-wsl-autostart` を実行する。`Get-CimInstance Win32_Process` で、古い powershell と、`dotfiles-wsl-keepalive` を含む `wsl.exe` が無いことを確かめる（一時の client は別の command line なので区別できる）。
      3. 昇格した terminal で `just runner-gc-install` を実行する。登録の後に installer が autostart を起こし、新しい keepalive がつながる。
      4. 失敗した時は、一時の client を残したまま、原因を直してもう一度 3 を行うか、「失敗したとき」の手順で戻す。一時の client は 15 分で終わるので、長くかかる時は起こし直す。
   3. 確かめる：
      - `Get-ScheduledTask dotfiles-runner-watchdog, dotfiles-wsl-autostart, dotfiles-runner-gc | % Actions` が `run-hidden.exe` を指す。
      - `wsl.exe` の keepalive（command line に `dotfiles-wsl-keepalive`）の親が powershell、その親が `run-hidden.exe` で、古い keepalive が残っていない（`Get-CimInstance Win32_Process`）。
      - watchdog の log に 5 分ごとの行が続く。
      - `just status` が OK で、新しい WARN が出ない。
      - 所有者が 10 分ほど見て、窓が出ないこと。
      - 次に logon した時に、autostart が run-hidden から起き、keepalive がつながること（`just status`）。
   4. 確かめが済んだら、一時の client を終える。

## 範囲の外（点検で見つかり、別に扱う）

- rtk の hook と test の helper の spawn に `CREATE_NO_WINDOW` を足すこと（直し方の 2 番）。
- `rtk-hook-claude.sh` の Store の `python3` の stub（3 番）。
- `j-cc` の resume で agent の定義が消えること（4 番）。
- runner の本体の `dotfiles-runner-interactive`（`run.cmd`）の窓は、設計どおり常に出ている。CI の job の子はその console を受け継ぐ。これは変えない。

## 失敗したとき

戻し方は、新しい installer の停止の処理に頼らない（revert するとその処理も消えるため）。所有者の承認で、昇格した terminal で次を順に行う。

1. PR を revert して main を取り込む。
2. 一時の client で distro を保つ：別の terminal で `wsl.exe -d Ubuntu-26.04 -e sleep 900` を起こしておく。
3. `Stop-ScheduledTask dotfiles-wsl-autostart` を実行する。`Get-CimInstance Win32_Process` で、`run-hidden.exe` の子の powershell と、`dotfiles-wsl-keepalive` を含む `wsl.exe` が無いことを確かめる。
4. `just runner-watchdog-install` と `just runner-gc-install` を実行する（元の、powershell.exe を直に起こす action に戻る）。
5. `just status` で keepalive が OK で、autostart の task が Running であることを確かめる。
6. 2 の一時の client を終える。

`%LOCALAPPDATA%\dotfiles\run-hidden\` と probe の task `dotfiles-headless-probe` は、どの task も使っていないことを確かめてから、所有者の片付けで消す（所有者の指示 2026-11-18）。

## レビューの記録

### Codex 1 回目（第 1 版、2026-11-18）

| # | 指摘 | 判断 | 確かめたこと |
|---|---|---|---|
| 1 | 走っている古い keepalive を切り替える手順が無い（P1） | 採用 | installer は登録し直すだけで止めない（`install_runner_gc_win.ps1:147-183`）。新しい payload は keepalive が居ると終わる（`wsl_autostart.ps1:91`）。Running なら止めてから登録し直す形にし、機の作業に親子の確かめを足した |
| 2 | exit code が消え、FAIL が出なくなる（P1） | 採用（案を変えた） | conhost が exit code を返さないことは実験で確かめた。status は autostart の結果で FAIL にする（`gc_status.sh:245-250`）。status に代わりの判定を足すのではなく、exit code を返す launcher に変えて、今の判定をそのまま使う |

### Codex 2 回目（第 2 版、2026-11-18）

| # | 指摘 | 判断 | 確かめたこと |
|---|---|---|---|
| 1 | 書いた手順では、この機で UAC が出ず切り替わらない（P1） | 採用 | 既存の S4U の task を unelevated で消せないと `keepGcTask` になり、UAC は `if (-not $keepGcTask)` の内側にある（`install_runner_gc_win.ps1:51-61,84`）。機の作業を、所有者の開いた昇格した terminal で行う手順にした |
| 2 | 走っている共有の `run-hidden.exe` は上書きできない（P1） | 採用 | autostart の launcher は keepalive を待って動き続けるので、その exe は使用中のままになる。中身の hash ごとの置き場所にし、同じ中身なら写さない形にした。その振る舞いを pwsh のテストで固定する |
| 3 | revert すると停止の処理も消え、戻し方が成り立たない（P1） | 採用 | revert 後の installer は登録し直すだけになる。一時の client で distro を保ち、明示的に止めて確かめてから元の installer を動かす手順にした |

### Codex 3 回目（第 3 版、2026-11-18）

| # | 指摘 | 判断 | 確かめたこと |
|---|---|---|---|
| 1 | 通常の切り替えにも一時の client と失敗時の戻しが要る。事前の確かめは止める前に。登録や起動の失敗を偽の task 操作で試す（P1） | 採用（形を変えた） | 止めた後に登録が失敗すると distro が止まるのは確か。installer に止める処理と戻す処理を足す代わりに、止める処理そのものを installer から外し、切り替えを戻し方と同じ手順にした。そのため、偽の task 操作のテストは要らない（installer は失敗の後に何もしない）。事前の確かめは採用し、launcher の写しを最初の `Unregister-ScheduledTask` より前に置く（今の GC の installer は先に消す、`install_runner_gc_win.ps1:51-61`） |

### Codex 4 回目（第 4 版、2026-11-18）

APPROVE。追加の指摘は無かった。
