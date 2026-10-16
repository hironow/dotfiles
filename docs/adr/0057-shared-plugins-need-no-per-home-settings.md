# 0057. 共通セットの plugin は、home ごとの設定なしで動くものに限る

**Date:** 2026-10-16
**Status:** Proposed
**ID:** ADR-0057
**Title:** 共通セットの plugin は、home ごとの設定なしで動くものに限る
**Decided-date:** —
**Decision-maker:** Hiroto N.
**Decision-maker-contact:** @hironow
**Author:** Claude Code（owner session）
**Author-contact:** @hironow
**Supersedes:** [ADR-0056](0056-common-claude-plugin-set.md) の一部（Decision 1 の「40 個」と除外 3 個、Decision 5 の pyright-lsp の扱い）
**Superseded-by:** none
**Related:** [ADR-0056](0056-common-claude-plugin-set.md)、[ADR-0048](0048-required-claude-plugins.md)、[ADR-0044](0044-python-toolchain-uv-ruff-ty.md)、[ADR-0037](0037-layered-claude-settings-fragments.md)、[ADR-0049](0049-headroom-mandatory-base-tooling.md)
**Consultation-trace:** —（この PR で所有者の裁定を受ける）

## やさしい説明

全部の home にそろえる plugin の中に、Google Cloud のプロジェクト名などを home ごとに設定しないと動かないものが 2 つ混ざっていた。
この提案では、その 2 つを共通セットから外す。
同じ種類の plugin がまた混ざったら、`just doctor` が知らせるようにする。

## Context

[ADR-0056](0056-common-claude-plugin-set.md) は、5 つの home の和集合から 3 個を除いた 40 個を共通セットにした。
除いた理由の一つは、bigquery-data-analytics と knowledge-catalog が GCP の project ID を home ごとに設定しないと MCP サーバー（Claude に外部の道具をつなぐ常駐プロセス）を起動できないことだった。

2026-10-16 に #475 を merge し、この Mac の 5 home に 40 個を入れた。
その後 `claude mcp list` で、work-a〜d の cloud-sql-sqlserver と firestore-native の MCP が起動しなかった（`Key: 'Config.Project' Error:Field validation ... 'required'`）。

- 新しく入った cloud-sql-sqlserver 0.2.0 と firestore-native 0.3.4 は、plugin.json に `mcpServers`（`npx @toolbox-sdk/server --prebuilt ...`、環境変数は `${user_config.*}`）を持っていた。
- `~/.claude` にある同じ version の古いキャッシュには `mcpServers` が無かった。upstream が version を上げずに MCP を足した。claude-plugins-official は ADR-0056 で追従にしているので、こうした変更はそのまま入る。
- 和集合を取ったときの `~/.claude` では MCP が無かったので、この 2 つは除外をすり抜けた。

`claude plugin configure <id> --json` は、設定項目の `schema`（項目ごとに type、title、description、あれば `default`）を返す。
宣言の 40 個と bigquery-data-analytics、knowledge-catalog を調べると、default の無い項目を持つのは GCP 系の 4 個（cloud-sql-sqlserver、firestore-native、bigquery-data-analytics、knowledge-catalog）だけだった。
code-modernization は 7 項目を持つが、どれも default 付きで、そのまま動いている。
firestore-native の `firestore_database` は説明に「Optional」とあるのに default が無い。default が無いことは、その項目が必須であることを意味しない。

`claude plugin update` は `scripts/claude_plugins.py` を通らない。
`configure --json` は 1 回あたり約 0.9 秒かかり、`plugin list --json` には schema が含まれない。

## Decision

（Proposed。裁定後に Accepted の MUST 文を書く。提案の中身は Options の A 案。）

## Options

- **A) 外して、規則にし、移行も script で行う（提案）**
  1. 共通セットの plugin は、home ごとの設定なしで動かなければならない（MUST）。判定は保守的に行う。`configure --json` の schema に default の無い項目が 1 つでもあれば、home ごとの設定が要る可能性があるとして共通セットに入れない。項目が本当に必須かどうかは判定しない。
  2. `scripts/claude_plugins.py` は、宣言した plugin の schema を install のときも `--check`（doctor）のときも確かめ、1 に当たるものを WARN にする（MUST）。読めなければ、それも WARN にする。
     読んだ結果は home の `claude-plugins.sync-state.json` に、`plugin list --json` の version と lastUpdated を key にして保存してよい。key が変わったときと、`readFromFolder`（repo のフォルダを直接読む plugin）のときは、毎回読み直す。保存は install のときだけ行い、doctor は読むだけにする。
  3. 宣言は cloud-sql-sqlserver と firestore-native を外した 38 個とする（MUST）。
  4. 宣言の `disabled` に書いた plugin は、user scope で有効なら毎回無効にする（MUST）。pyright-lsp をここに書く。plugin は pyright の起動設定なので、無効にすれば pyright は動かない（ADR-0044 と整合）。
  5. 宣言の `retired` に書いた移行（ID と plugin の組）は、各 home で 1 回だけ、user scope で有効な対象を無効にする（MUST）。対象がすべて無効だと確かめたら、ほかの WARN の有無にかかわらず、その home の `claude-plugins.sync-state.json` に ID を記録する。記録後に利用者が設定して有効にした plugin は残す。記録が読めないときは移行を走らせず、WARN にする。GCP 系の 4 個をこの移行に書く。

    - 利点: 共通セットが、どの home でも設定なしで動く。upstream が同じ version のまま設定を要求し始めても、doctor が知らせる。ほかの機体の home も、次の `just deploy` で同じ状態に移る。GCP 系を使いたい home では、設定すれば使い続けられる（ADR-0056 の Neutral のとおり）。
    - コスト: 初回と更新後は、home ごとに最大 38 回 CLI を呼ぶ（8 並列）。home の中に dotfiles 所有のファイルが 1 つ増える。default の無い任意項目しか持たない plugin も外れる。

- **B) 2 つを外すだけにする**
    - 利点: script の変更が要らない。
    - コスト: 同じすり抜けを見張れない。ほかの機体では 2 つが有効なまま残る。

- **C) 共通セットに残し、各 home で project を設定する**
    - 利点: 宣言を変えずに済む。
    - コスト: home ごと、機体ごとに設定が要る。共通セットの意味（設定なしでそろう）が崩れる。

## Consequences

### Positive

- 共通セットの 38 個は、どの home でも設定なしで動く。
- 設定の要る plugin の混入と、upstream の無断の変更を、doctor が知らせる。
- 移行は 1 回だけなので、利用者の後からの選択を上書きしない。

### Negative

- 結果を保存しないと、doctor の `claude-plugins` 行は 5 秒から 40 秒前後に延びた（2026-10-16 の実測、`configure --json` は 1 回約 0.55 秒）。保存した結果を使うので、普段の増分は `plugin list --json` の 1 回分と、`readFromFolder` の plugin の読み直しだけになる。
- 保存した結果は、home の中の plugin が install か update で入れ替わるまで使い回す。入れ替われば lastUpdated が変わるので読み直すが、state ファイルを手で書き換えれば検査をすり抜けられる。
- 保守的な判定なので、default の無い任意項目だけを持つ plugin も共通セットに入れられない。入れたいときは、この ADR を置き換える。
- pyright-lsp は無効にするだけで、ファイルは home に残る。

### Neutral

- 宣言にも `disabled` にも `retired` にも無い plugin には、これまでどおり触れない。
- 移行の記録は home ごとなので、新しい home では最初の install で一度だけ移行が走る。

## 反転記録 (Reversal)

none

## 裁定欄

- [ ] A 案で採択 / [ ] B 案で採択 / [ ] C 案で採択 / [ ] 修正のうえ採択（修正点: ____） / [ ] 却下（理由: ____） / [ ] 保留
- 決定者・日付:
- A 案で採択したときの作業: ADR-0056 の Status を `Superseded by [0057]`（部分）に変える（これだけが許される編集）。merge 後に main の checkout で 5 home を退避してから `just claude-plugins-install` を実行し、`claude mcp list` を確かめる。
- B 案で採択したときの作業: schema 検査と `disabled` / `retired` のコードを外し、宣言を 38 個だけにする。この Mac の 5 home で 2 つを手で無効にする。
- C 案で採択したときの作業: 宣言を 40 個に戻し、project ID を受け取って各 home で `/plugin configure` する。
- 却下・保留したときの作業: 宣言を 40 個に戻す。
