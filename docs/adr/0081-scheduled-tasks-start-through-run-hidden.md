# ADR 0081 — dotfiles の Windows の scheduled task は run-hidden を通して起こす

- **id**: ADR-0081
- **title**: dotfiles の Windows の scheduled task は run-hidden を通して起こす
- **status**: Accepted
- **date**: 2026-11-18
- **decided-date**: 2026-11-18
- **decision-maker**: Hiroto N.
- **decision-maker-contact**: @hironow
- **author**: Claude Code（owner session）
- **author-contact**: @hironow
- **supersedes**: none
- **superseded-by**: none
- **related**: [0035](0035-runner-disk-gc.md)、[0042](0042-interactive-runner-watchdog.md)、[0066](0066-doctor-warns-only-what-needs-action.md)
- **consultation-trace**: 2026-11-18 の本セッションでの所有者の依頼と承認（下の「相談の記録」）。計画は `docs/plan/windows-headless-tasks.md`。[公開 PR #644 の所有者の裁定](https://github.com/hironow/dotfiles/pull/644#issuecomment-6977468442)

## やさしい説明

Windows の機で、5 分ごとにターミナルの窓が一瞬出ていた。
dotfiles が登録した scheduled task が、`powershell.exe` を窓付きで起こしていたためである。
task は、窓を持たない小さな launcher（`run-hidden`）を起こし、その launcher が `powershell.exe` を窓無しで起こす形にする。
launcher は `powershell.exe` の終わり方（exit code）をそのまま返すので、task が失敗したかどうかは今までどおり分かる。

## Context

- 2026-11-18、所有者が「Windows で CI やチェックを回すと、ターミナルが一瞬出る」と伝え、点検を依頼した。
- 点検で見つかった原因：
    - `dotfiles-runner-watchdog`（ADR 0042）は、5 分ごとと logon のたびに、所有者の logon session（Interactive の principal）で `powershell.exe` を直に起こす。log（`%TEMP%\runner-watchdog-win.log`）には 5 分ごとの行がある。
    - `dotfiles-wsl-autostart`（ADR 0035 の一族）は、logon のたびに `powershell.exe` を起こし、その窓は WSL の keepalive として session の間ずっと開いたままになる。
    - `dotfiles-runner-gc` は、この機では S4U で窓は出ない。UAC を断った時の Interactive の登録では、毎時窓が出る。
- Task Scheduler が console の program を直に起こすと、program は新しい console を受け取り、その窓が出る。
- `just status` は、GC と autostart の task の結果（`LastTaskResult`）が 0 でない時に FAIL にする（`scripts/gc_status.sh`）。ADR 0042 は、watchdog が起きられなかった時の手がかりを task の結果（`0xFFFD0000`）に頼る。つまり、task の結果が payload の exit code であることが前提である。
- この機での実験（2026-11-18）：
    - `conhost.exe` は、`--headless` の有無によらず、子の exit code を返さない（子が 7 で終わっても 0）。
    - `CREATE_NO_WINDOW` で起こした子は、console を持つが窓を持たない。その子から `wsl.exe` も動く。
    - Windows の GUI subsystem で build した Go の launcher を、本物の scheduled task（Interactive）から起こした。子は session 1 で窓を持たずに 15 秒動き、子の `exit 7` が task の結果に `7` と出た。

## Decision

A 案の次の 6 項を、必須事項（MUST）として採択する。

- D1: dotfiles が登録する Windows の scheduled task は、console の program を直に起こしてはならない。task の action は `run-hidden.exe` を起こし、その引数の先頭に program の path、続けて元の引数を置かなければならない。対象は今は `dotfiles-runner-watchdog`、`dotfiles-wsl-autostart`、`dotfiles-runner-gc` の 3 つである。`dotfiles-runner-interactive`（runner の本体の `run.cmd`）は対象の外とする。CI の job の子が、その窓の console を受け継ぐためである。
- D2: `run-hidden`（`tools/run-hidden`、Go の標準ライブラリだけ）は、Windows の GUI subsystem で build し（`-ldflags=-H=windowsgui`）、子を `CREATE_NO_WINDOW` で起こし、子の exit code をそのまま自分の exit code にしなければならない。引数が無い時と Windows 以外では 2、子を起こせない時は 1 で終わる。
- D3: installer は、`run-hidden.exe` の写しを、中身の SHA-256 の先頭 16 桁の名前の dir（`%LOCALAPPDATA%\dotfiles\run-hidden\<hash16>\`）に置き、task はその写しを起こさなければならない。同じ中身は写し直さず、中身が変われば別の dir に写す。古い dir は installer が消さない。写しは、どの task を消すよりも前に済ませる。
- D4: installer は、走っている task の instance を止めてはならない。走っている WSL autostart を新しい action に切り替える時（戻す時も）は、一時の client で distro を保ってから止める手順（`docs/runbook/windows-host.md`）で行う。
- D5: 窓が無くなる payload は、自分の記録をファイルに残さなければならない（watchdog は今の `%TEMP%\runner-watchdog-win.log`、autostart は `%TEMP%\wsl-autostart.log`）。
- D6: `just status` は、D1 の 3 つの task のうち `run-hidden.exe` を起こしていないものに WARN を出す（登録し直すという、手を動かすべきことがあるので WARN にする。ADR 0066）。

## Options Considered

| 案 | 利点 | コスト・リスク | 裁定 |
| --- | --- | --- | --- |
| A) GUI subsystem の launcher（run-hidden）を通す（本案） | 窓が出ない。exit code が task の結果に残るので、status と ADR 0042 の判定が変わらない。task の principal と trigger は変えない | 小さな Go の module が 1 つ増える。写しの版の管理が要る（D3） | 本案 |
| B) `powershell.exe -WindowStyle Hidden` | 変更が引数だけ | console ができてから隠すので、窓が一瞬出る。窓を出す原因そのものが残る | 却下: 一瞬の窓が残る |
| C) `conhost.exe --headless` で包む | Windows に入っている。窓が出ない | 子の exit code を返さない（実験で確認）。task がいつも成功になり、status の FAIL が出なくなる | 却下: 失敗が見えなくなる |
| D) 3 つとも S4U（logon していなくても動く形）にする | session に desktop が無いので窓が出ない | 登録に昇格が要る。S4U の session から `wsl.exe` の keepalive と watchdog の `Start-ScheduledTask` が動くかは確かめていない | 却下: 確かめていない前提に頼る |
| E) VBScript（`wscript.exe`）で隠して起こす | 昔からある形 | Windows が VBScript を廃止に向けている | 却下: 使えなくなる道具に頼る |

## Consequences

- **Positive**: 所有者の画面に、dotfiles の task の窓が出なくなる。task の結果は今までどおり payload の exit code なので、`just status` の判定と ADR 0042 の手がかりは変わらない。
- **Negative**:
    - 窓で見えていた autostart の記録は、log を開かないと読めない。
    - `run-hidden.exe` の古い写しが `%LOCALAPPDATA%\dotfiles\run-hidden\` に溜まる。消すのは人である。
    - task を登録し直すには、昇格した terminal が要る（この機の task は昇格して登録されている）。切り替えの手順は人が行う。
- **Neutral**: payload、引数、trigger、principal、settings は変えない。dotfiles の CI の Windows の job は GitHub の `windows-latest` で、この ADR とは関係しない。

## 反転記録 (Reversal)

none

## 他の DR との照合

0001〜0080 の題名と状態を走査し、scheduled task、Task Scheduler、ScheduledTask、窓、window、WindowStyle、powershell、autostart、S4U、Interactive で全文を検索した。当たった 0007、0035、0042 と、WARN の規則を決めた 0066 を読んだ。PDR は無い。

- **矛盾**: 見つからなかった。0042 の Decision 1 は「task は `%LOCALAPPDATA%\dotfiles\runner_watchdog_win.ps1` の写しを起こす」で、本案もその写しを `-File` に渡す。起こす exe が `powershell.exe` から `run-hidden.exe` に変わるだけで、0042 の Consequences の「起きられない tick は task の結果（`0xFFFD0000`）だけに残る」は、run-hidden が 2^31 を超える exit code もそのまま返すので保たれる（`tools/run-hidden/run_windows_test.go`）。
- **重複**: 番号 0081 は未使用。同じ決定の記録は無い。
- **誤読**: 0035 の「GC の task は S4U、断られたら Interactive」は principal の決定で、本案は principal を変えない。
- **偽の関連**: 0007 の scheduled task は coder の版の比較の例で、dotfiles が登録する task ではない。
- **関係誤認**: 0066 は「WARN は手を動かすべきことだけ」と決めている。D6 の WARN は、登録し直すという手を動かすべきことを示す。

## 相談の記録

- 2026-11-18、本セッションで所有者（@hironow）が、Windows で一瞬出るターミナルの点検を依頼した。所有者の別の repo で、窓の扱いに苦労したことを参考にするよう指示した。
- Claude が点検の結果（窓を出す task 3 つと、直し方の案 4 つ）を示し、「1 から順に、計画・独立レビュー・PR で進めてよいか」と尋ねた。所有者は「はい進めてください」と答えた。
- 計画は Codex が独立に 4 回レビューした。1〜3 回目は REVISE（P1 が 2 件、3 件、1 件）で、全件を確かめて取り込んだ。conhost の案から run-hidden の案に変えたのは、1 回目の指摘（exit code が消える）を実験で確かめた結果である。4 回目は APPROVE。記録は計画の「レビューの記録」にある。
- 実装は PR #644 で main に入った（6355482）。2026-11-18 19:09 に、所有者の承認（UAC）で、この機の 3 つの task を昇格して登録し直した。keepalive は `run-hidden → powershell → wsl` の鎖でつながり、watchdog は 5 分ごとに結果 0 だった。
- 2026-11-18、所有者は、採択するかという問いに「A 案で Accepted」を選んだ。これを A 案の採択とし、PR に記録した（[裁定](https://github.com/hironow/dotfiles/pull/644#issuecomment-6977468442)）。

## 決定（2026-11-18）

- [x] A 案で Accepted（D1〜D6 のとおり）
- [ ] 修正のうえ Accepted（修正点: ____）
- [ ] Rejected / Deferred（理由: ____）

決定者: Hiroto N.（@hironow）　決定日: 2026-11-18（所有者の裁定により代理記入）

- Accepted のとき: Decision を確定し、索引、変更ログ、queue の決定済みログを更新する。merge の後、所有者の承認で、runbook の手順で 3 つの task を登録し直す。
- 修正のとき: 指摘の点を Decision、コード、テストに反映し、同じ PR で確定する。
- Rejected / Deferred のとき: PR を閉じ、queue に理由を残す。
