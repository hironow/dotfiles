# 0066. doctor の WARN は手を動かすべきことだけにし、注意書きは INFO で出し、OS に合わない行は出さない

**Date:** 2026-11-01
**Status:** Proposed（決裁待ち。[decision-queue](../decision-queue.md) で追跡する）
**ID:** ADR-0066
**Title:** doctor の WARN は手を動かすべきことだけにし、注意書きは INFO で出し、OS に合わない行は出さない
**Decided-date:** （未決）
**Decision-maker:** Hiroto N.
**Decision-maker-contact:** @hironow
**Author:** Claude Code（owner session 6f9f9d8e）
**Author-contact:** @hironow
**Supersedes:** none
**Superseded-by:** none
**Related:** [ADR-0065](0065-kernel-cve-is-evidence-only.md)（Proposed。kernel の所見は WARN 止まり）、[ADR-0062](0062-one-windows-ollama-for-wsl.md)（Decision 4: Ollama の判定は `ollama_host.py --check`）、[ADR-0064](0064-mirrored-wsl-uses-the-shared-loopback.md)、計画 [doctor-os-aware-warn](../plan/doctor-os-aware-warn.md)、計画 [kernel-cve-evidence](../plan/kernel-cve-evidence.md)（D3）、計画 [doctor-windows-wsl-warn](../plan/doctor-windows-wsl-warn.md)（Windows と WSL の実測からの追補）、計画 [ca-control-ipv4](../plan/ca-control-ipv4.md)（D3 の再試行の 2 回目を IPv4 にする）、[CA runbook](../runbook/ca-doctor.md)、[Ollama runbook](../runbook/ollama-windows-wsl.md)
**Consultation-trace:** 2026-11-01 17:07 の本セッションで所有者が計画を承認した（D1 = テストホストを全部拒否したクライアントは INFO、D2 = 本 ADR を起票）。決裁は PR で記録する。2026-11-01 19:32 に所有者が Windows と WSL の実測からの追補計画を承認した（D1 = kernel の数値と助言は INFO、D2 = docker-desktop は INFO、D3 = control の再試行を入れる）。2026-11-01 21:46 に所有者が、再試行の 2 回目を IPv4 にする計画を承認した（trade 機のセッション、[#529](https://github.com/hironow/dotfiles/pull/529)）

## やさしい説明

`just doctor` は機体の健康診断である。
この Mac では警告（WARN）が 103 件出ていたが、手を動かすべきものはほとんど無かった。
「調べた範囲には限りがある」という毎回同じ注意書きや、正しく動いている事実まで、警告として数えていたからである。
そこで、警告は「その機体で見るか、手を動かすべきこと」だけにする。
注意書きと事実は、別の印（INFO）で出し、警告には数えない。
その OS に関係の無い検査の行は出さない。

## Context

- 2026-11-01、この Mac（macOS 27.2）で `just doctor` は `ok=55 warn=103 err=15` だった。
  WARN の内訳は、14 のテストホストを正しく拒否した結果を 1 ホスト 1 行で並べた 70 件とその要約 5 件、
  調べた実行ファイルの事実 10 件、runbook が macOS で勧める CA ファイルの環境変数 4 件、
  毎回同じ範囲の注意書き 7 件、Git の既定が上書きされていない事実 1 件、
  certifi と pip が入っていないことを「版を解析できない」と誤って言う 3 件、
  Linux カーネルが無い macOS での kernel の注意書き 1 件である。
- ERR 15 件も、`/usr/bin/python3` がテストホストを受け入れたという 1 つの事実を、14 ホスト分と要約の 15 行に展開していた。
- macOS で、WSL だけの検査（`PATH-windows`）と、Windows と WSL だけの方針（`ollama-policy - not applicable`）が OK の行として出ていた。
- 所有者は 2026-11-01 に「doctor の処理もその OS に基づいたもので、WARN を過剰に出しすぎないようにしたい」と依頼した。
- 守ってきた決まりは 2 つある。未確認のものを合格にしない（[CA runbook](../runbook/ca-doctor.md)「結果と限界」）。
  kernel の所見は WARN 止まりで `err` に入れない（[ADR-0065](0065-kernel-cve-is-evidence-only.md) Decision 4）。
  どちらも、警告を 1 つずつ確かめる手間を前提にしていた。
- kernel の計画（[kernel-cve-evidence](../plan/kernel-cve-evidence.md) の D3）は、coverage の行を常に出すとしていた。
  Linux カーネルが無い機体では、`kernel-not-applicable` の行がすでに「この機体から使う WSL と Linux VM は調べていない」と述べている。
- 2026-11-01、trade 機の native Windows で `ok=61 warn=11 err=1 info=20`、WSL（Ubuntu 24.04）で `ok=54 warn=12 err=1 info=26` だった（#526 のコメント）。
  WARN の判定と出し分けに、Mac では見えなかった誤りが 7 種あった。
  Windows の curl（Schannel）が証明書の拒否を終了コード 35 で返すので「未確認」になる。
  Windows で正常系への接続が時々リセットされる（あとで、正常系の IPv6 の経路だけで起きると分かった。[ca-control-ipv4](../plan/ca-control-ipv4.md)）。
  pip の `24.0` のような 2 要素の版を「解析できない」とする。
  Homebrew が無いことを、使わない Windows と任意の Linux でも WARN にする。
  Windows の OS の CA ストアに版を問い合わせる手段が無く、常に WARN になる。
  kernel の第三者の数値と記録の助言を、CVE 1 件につき 6 行の WARN にする。
  Docker Desktop の `docker-desktop` distro を、Ollama のクライアントでないのに「未検査」の WARN にする。

## Decision

（Proposed。所有者が承認した計画の内容を、確定したときの MUST の形で書く。）

1. **WARN の意味。** `just doctor` とその下の検査（ca-doctor、kernel-doctor、`scripts/doctor_lines.py` を使う checker、`ollama_host.py --check`）は、WARN を「その機体で operator が見るか、手を動かすべきこと」にだけ使わなければならない（MUST）。
2. **INFO。** 検査の範囲の注意書きと、機体についての事実は `INFO` の行で出さなければならない（MUST）。kernel の第三者の数値と、事故の記録にある助言の文もこれにあたる。`INFO` は表示し、`Doctor summary` の `info=` に数えるが、OK にも WARN にも数えず、終了コードを変えてはならない（MUST NOT）。未確認のものを OK にしてはならない（MUST NOT）。
3. **全部拒否したクライアント。** 正常系が通り、事故のテストホストの証明書をすべて拒否したクライアントは `INFO` とし、「拒否の理由が CA の不信頼化だとは証明できない」と文に残さなければならない（MUST）。1 つでも受け入れたら ERR、不明が混じれば WARN とする（今と同じ）。
4. **要約。** `just doctor` は `ca-doctor --summary` を使い、テストホストごとの行を省いてクライアントごとの 1 行にしなければならない（MUST）。ERR の行は受け入れたホストの名前を並べる。ホストごとの全行は `just ca-doctor` で出す。
5. **OS に合わない行。** その OS に意味の無い検査は、行そのものを出してはならない（MUST NOT）。WSL の `/mnt` 漏れの検査は WSL でだけ出す。Ollama の方針の検査は、`host_policy()` が対象外とした機体では出力なしの exit 3 で終わり、doctor はそれを黙って通す。kernel の coverage の注意書きは、カーネルの版を調べた機体でだけ INFO で出す。Homebrew が無いことは macOS でだけ WARN とし、任意の Linux では INFO、使わない native Windows では行を出さない。Windows の OS の CA ストアは package でなく Windows Update が更新するので INFO で出す。
6. **ERR と終了コードは変えない。** ERR の判定、`err` の数え方、ERR があれば exit 1 という契約は変えない（ADR-0065 Decision 4 の「kernel は WARN 止まり」もそのまま）。

## Options Considered

| 案 | 内容 | 利点 | コスト・リスク |
| --- | --- | --- | --- |
| A) INFO を足し、要約し、OS で出し分ける（本案） | 上の Decision 1〜6 | WARN が手を動かすべきことだけになる。この Mac で WARN 103 → 1、ERR 15 行 → 1 行（終了コードは同じ）。証拠の全量は `just ca-doctor` に残る | 行の protocol に 4 つ目の level が増え、doctor.sh、checker、テスト、runbook を揃えて直す。Windows と WSL の実機での確認が別に要る |
| B) 今のまま | 103 件の WARN を残す | 変更が無い | 本当の警告が埋もれる。所有者の依頼に応えない |
| C) 注意書きを出さない | 範囲の注意書きを消す | 行が最も少ない | 調べていない範囲が見えなくなり、doctor が「全部大丈夫」と読める。未確認を隠すことになる |
| D) 注意書きを OK にする | 範囲の注意書きを OK の行にする | protocol を変えずに済む | 合格ではないものを合格と数える。「未確認を合格にしない」に反する |
| E) 全部拒否したクライアントも WARN のまま（Decision 3 だけ変える） | A のうち、全部拒否は WARN | 拒否の理由が未証明であることを強く示す | この Mac で WARN が 5 件残り、毎回同じ結果で対処が無い |

## Consequences

### Positive

- WARN と ERR が、その機体で手を動かすべきことだけになる。
- 調べていない範囲は INFO として毎回見えるので、doctor が「全部大丈夫」とは読めない。
- ERR の行が、受け入れたホストの名前を持つので、1 行で状況が分かる。

### Negative

- 行の protocol が 4 level になる。新しい checker は INFO を正しく使い分ける必要がある。
- `--summary` を知らない古い ca-doctor の binary は、作り直すまで `WARN ca-build` になる（doctor が再ビルドを案内する）。
- 全部拒否したクライアントが INFO になるので、テストホスト側の証明書が期限切れになって全クライアントが拒否する状態は、WARN では気づけない。事故別ルールのレビュー期限（`ca-policy-*`、期限を過ぎると WARN）で見直す。
- Windows と WSL の実機での結果は、クロスビルドでは確かめられない。2026-11-01 に trade 機で確かめ、見つかった 7 種の誤りを直した（[doctor-windows-wsl-warn](../plan/doctor-windows-wsl-warn.md)）。直した後も、各機体で `just doctor` を実行して確かめる必要がある。

### Neutral

- `INFO` の行（この Mac で 31 行）は出力に残る。行の数は減らないが、警告としては数えない。
- kernel の計画の D3（coverage を常に出す）は、カーネルの版を調べた機体に狭まる。ADR-0065 の本文は変えない。

## 反転記録 (Reversal)

none

## 決定（記入待ち）

- [ ] A 案で Accept / [ ] E 案で Accept / [ ] 修正のうえ Accept（修正点: ____） / [ ] Reject（理由: ____） / [ ] Deferred
- 決定者・日付:
- A 案 Accept 時のアクション: 追加の実装は無い（#526、[doctor-windows-wsl-warn](../plan/doctor-windows-wsl-warn.md) の #527、[ca-control-ipv4](../plan/ca-control-ipv4.md) の #529 で main に入っている）。status、decision-queue、README の索引を更新する。
- E 案 Accept 時のアクション: `ProbeEvidenceFor` と `ChainEvidence` の全部拒否を WARN に戻し、runbook の表を直す。
- 修正 Accept 時のアクション: 修正点を計画と実装に反映し、テストを直す。
- Reject 時のアクション: #526 と doctor-windows-wsl-warn の PR の振る舞いの変更を戻し、INFO の無い WARN の扱いに戻す。
- Deferred 時のアクション: 実装は main に残したまま、doctor-windows-wsl-warn の変更後の Windows と WSL の再確認がそろってから再検討する。
