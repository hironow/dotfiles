# 0077. 止めて残すと宣言した WSL の distro と、machine の無い native Windows の Podman CLI は、doctor で INFO にする

**Date:** 2026-11-14
**Status:** Proposed（決裁待ち。[decision-queue](../decision-queue.md) で追跡する）
**ID:** ADR-0077
**Title:** 止めて残すと宣言した WSL の distro と、machine の無い native Windows の Podman CLI は、doctor で INFO にする
**Decided-date:** （未決）
**Decision-maker:** Hiroto N.
**Decision-maker-contact:** @hironow
**Author:** Claude Code（owner session、GPU の Windows 機）
**Author-contact:** @hironow
**Supersedes:** none
**Superseded-by:** none
**Related:** [ADR-0066](0066-doctor-warns-only-what-needs-action.md)（Decision 1 と 2: WARN は手を動かすべきことだけ、事実は INFO）、[ADR-0062](0062-one-windows-ollama-for-wsl.md)（Decision 4: Ollama の判定は `ollama_host.py --check`）、[ADR-0063](0063-declared-tailnet-forward-of-ollama.md)（機体ごとの宣言ファイルの先例）、[ADR-0067](0067-use-podman-for-managed-containers.md)（Decision 1: CLI とエンジンの版、Decision 3: machine を自動で起こさない）、[Ollama runbook](../runbook/ollama-windows-wsl.md)
**Consultation-trace:** 2026-11-13 23:22 JST、GPU の Windows 機のセッションで、所有者が別の repo の移行計画を承認した。その計画は、WSL の作業環境を新しい distro に移し、古い distro を戻し先として止めて残す。宣言の場所と形はこの ADR で決めるとした。同じ日に所有者は、Windows の Podman CLI を machine なしで残し、その行を INFO にする案を選んだ。2026-11-14 に所有者が「はい、進めてください。」と答え、この段に入った。実装は独立レビュー（サブエージェント）が REVISE とし、P1 1 件（UTF-8 で読めない宣言が、動いている distro の検査を止める）、P2 1 件、P3 6 件をすべて反映した（machine の有無を見る A 案への修正を含む）。決裁は PR で記録する

## やさしい説明

`just doctor` は、Windows から WSL の distro（Linux の環境 1 つ分）を見て、Ollama の決まりを守っているかを調べる。
止まっている distro は起こさないので、調べられず、毎回警告（WARN）になる。
戻し先として、わざと止めて残す distro もある。その警告には、することが無い。
そこで、止めて残す distro の名前をファイルに書いたら、止まっている間は「事実」の印（INFO）で出す。
同じように、Windows で Podman のコマンドだけを入れ、仮想機械（machine）を置かない使い方では、エンジンに届かないのは普通の状態である。これも INFO で出す。

## Context

- `ollama_host.py --check`（`just doctor` が呼ぶ）は、Windows で `wsl.exe --list --quiet` と `--running` を読む。止まっている distro は起動せず、`WARN ollama-inspection "WSL <名前>: stopped, uninspected (not started)"` を出す（[runbook](../runbook/ollama-windows-wsl.md)）。`docker-desktop` だけは、Ollama のクライアントにならないので INFO で出す（ADR-0066 の追補）。
- 所有者の移行計画は、WSL の作業環境を新しい distro に移す。古い distro は unregister せず、戻し先と重みの 2 枚目の写しとして止めて残す。そのままでは、Windows の doctor が毎回 WARN を出す。計画の完了の条件は「Windows と WSL の `just doctor` が exit 0 で、コンテナと Ollama の行に WARN も ERR も無い」である。
- ADR-0067 の Decision 3 と 8 により、導入処理は Podman の machine を初期化も起動もしない。その GPU の Windows 機では、所有者が 2026-11-13 に、winget の Podman CLI を machine なしで残し、コンテナは WSL の Podman で動かすことを選んだ。そのため `podman info` は毎回失敗し、doctor は `WARN podman - CLI 5+ present, selected engine unavailable; operator activation is separate` を出す。することは無い。
- ADR-0066 の Decision 1 は、WARN を「その機体で operator が見るか、手を動かすべきこと」に限る。Decision 2 は、機体についての事実を INFO で出し、OK にしないとする。
- 機体ごとの宣言ファイルには先例がある。ADR-0063 の `%USERPROFILE%\.config\dotfiles\ollama-tailnet-forward` である。

## Decision

（Proposed。所有者が承認した計画の内容を、確定したときの MUST の形で書く。）

1. **宣言の場所と形。** 止めて残す distro は、`%USERPROFILE%\.config\dotfiles\wsl-retained-distros` に宣言しなければならない（MUST）。UTF-8（BOM は可）で、1 行に 1 つ、`wsl -l -q` が出すのと同じ名前（大文字と小文字も同じ）を書く。行の前後の空白、空行、`#` で始まる行は読まない。ファイルが無いとき、読めないとき、UTF-8 として読めないときは、何も宣言していないとする。宣言を読めないことで、動いている distro の検査を止めてはならない（MUST NOT）。
2. **止まっている宣言済みの distro。** `ollama_host.py --check` は、宣言した distro が止まっていれば、起動も検査もせず、`INFO ollama-inspection "WSL <名前>: declared retained and stopped; not inspected"` を出さなければならない（MUST）。OK にしてはならない（MUST NOT）。
3. **動いている distro と、宣言していない distro。** 宣言した distro でも、動いていれば、宣言していない distro と同じ検査をすべて行わなければならない（MUST）。宣言していない止まった distro は WARN のままとする。
4. **宣言の範囲。** 宣言は doctor の行の重さだけを変える。distro を消す、止める、起動する許可ではない。doctor と setup は、どの distro も起動、停止、unregister してはならない（MUST NOT）。宣言を消せば元の WARN に戻る。
5. **native Windows の Podman CLI。** `just doctor` は、native Windows（Git Bash の `uname -s` が `MINGW*`、`MSYS*`、`CYGWIN*`）で、Podman の CLI が 5 以上で、`podman info` が失敗し、読み取りだけの `podman machine list` が成功して machine が 1 つも無いとき、`INFO podman` を出さなければならない（MUST）。machine があるのにエンジンに届かないとき、machine の一覧を読めないとき、macOS と Linux（WSL を含む）では WARN のままとする。CLI が無いか 5 未満のとき、届いたエンジンが 5 未満のときの ERR は変えない（ADR-0067 の Decision 1）。doctor は machine を初期化も起動もしない（ADR-0067 の Decision 3）。

## Options Considered

| 案 | 内容 | 利点 | コスト・リスク |
| --- | --- | --- | --- |
| A) 宣言した distro と、machine の無い native Windows の Podman CLI を INFO にする（本案） | 上の Decision 1〜5 | 移行の後の doctor に、することの無い WARN が残らない。宣言していない distro と、作った machine に届かないときの WARN は残る。宣言を消せば元に戻る | 宣言した distro の中は、起動するまで調べない。doctor が Windows で `podman machine list` を 1 回読む |
| A') A のうち、native Windows の Podman は machine の有無を見ずに INFO | `podman info` の失敗だけで INFO | 呼ぶコマンドが 1 つ少ない | machine を作った operator が、止まった machine に WARN で気づけない。ADR-0066 の Decision 1 に合わない（独立レビューの指摘） |
| B) 今のまま | 両方 WARN | 変更が無い | 毎回することの無い WARN が 2 種残る。ADR-0066 の Decision 1 に合わず、移行計画の完了の条件を満たさない |
| C) 止まっている distro はすべて INFO | 宣言なしで INFO | 設定が要らない | 起こし忘れた distro や、知らない distro も黙って INFO になり、WARN の知らせが消える |
| D) 止めて残す distro を unregister する | 行そのものが消える | doctor に手を入れなくてよい | 戻し先と重みの 2 枚目の写しを失う。消すかどうかは、所有者が後で別に決めると計画で決めている |
| E) Windows の Podman の INFO も宣言で切り替える | `podman-no-machine` のようなファイルがある機体だけ INFO | 宣言で意図をはっきり書ける | 宣言ファイルが 1 つ増える。machine の有無は `podman machine list` で読めるので、宣言は要らない。宣言を忘れた機体で WARN が残る |
| F) Windows から Podman の CLI を外す | Windows には CLI を置かない | 行が出ない | `podman` が無いので ERR になる。ADR-0067 の Decision 3（Windows は winget で入れる）に合わない |

## Consequences

### Positive

- 古い distro を止めて残しても、Windows の doctor に、することの無い WARN が出ない。
- 止まった distro の WARN は、宣言していない distro に残るので、起こし忘れは今までどおり見える。
- 宣言はファイル 1 つで、消せば元の判定に戻る。

### Negative

- 宣言した distro は、止まっている間は中を調べない。中に Ollama の残りや設定の違反があっても、起動するまで見えない（起動すれば Decision 3 で調べる）。
- 宣言の名前を書き間違えたり、UTF-8 以外で書いたりすると WARN が残る。これは安全な側に倒れる。
- doctor が native Windows で `podman machine list` を 1 回呼ぶ（読み取りだけで、0.2 秒ほど）。

### Neutral

- `docker-desktop` の INFO は変えない。
- ERR の判定と、ERR があれば exit 1 という契約は変えない（ADR-0066 の Decision 6）。

## 反転記録 (Reversal)

none

## 他の DR との照合

0001〜0076 の 75 件（0046 は欠番）の題名と状態を走査し、doctor、WSL、Windows、Podman、Ollama、runner に触れる記録の本文を読んだ（0035、0042、0058、0062、0063、0064、0065、0066、0067）。PDR は無い。

- **矛盾**: なし。0066 の Decision 1 と 2 をそのまま当てはめる（OK にはしない）。0062 の Decision 4 は判定の詳細を runbook に任せており、runbook を同じ PR で直す。0067 の Decision 1（CLI とエンジンの版を別々に確かめる）の ERR は変えず、Decision 3 と 8（machine を自動で起こさない）を守る。
- **重複**: 番号 0077 は未使用。止めて残す distro を宣言する記録は無い。0066 の `docker-desktop` の INFO は、プラットフォームが管理する distro についてで、operator の宣言とは別である。
- **誤読**: 0067 の Negative の「macOS と Windows は仮想環境を別途準備する必要がある」は、native でコンテナを動かすときの話である。本案は machine を置かない構成を認めるだけで、machine を使う構成を禁じない。
- **偽の関連**: 0063 は宣言ファイルの置き場の先例であり、Tailscale の転送の判定には関係しない。0035 と 0042 の runner、0058 の Pi、0064 の網の形、0065 の kernel の判定は変えない。
- **関係誤認**: どの記録も置き換えない。0066 を前提にする（同じ時期に Accepted にした）。

## 決定（記入待ち）

- [ ] A 案で Accept / [ ] A' 案で Accept / [ ] C 案で Accept / [ ] E 案で Accept / [ ] 修正のうえ Accept（修正点: ____） / [ ] Reject（理由: ____） / [ ] Deferred
- 決定者・日付:
- A 案 Accept 時のアクション: 実装は同じ PR に入っている。status、decision-queue、README の索引と決定変更ログを更新する。移行の後、Windows で古い distro を宣言し、`just doctor` で INFO になることを確かめる。
- A' 案 Accept 時のアクション: doctor.sh から `podman machine list` の条件を外し、テストと README を直す。
- C 案 Accept 時のアクション: 宣言の読み取りを外し、止まった distro をすべて INFO にし、テストと runbook を直す。
- E 案 Accept 時のアクション: Podman の INFO を宣言ファイルの有無で切り替え、テストと README を直す。
- 修正 Accept 時のアクション: 修正点を実装とテストと runbook に反映する。
- Reject 時のアクション: 実装を戻し、両方の行を WARN に戻す。移行計画の完了の条件を見直す。
- Deferred 時のアクション: PR を merge せずに残し、移行の前に決め直す。
