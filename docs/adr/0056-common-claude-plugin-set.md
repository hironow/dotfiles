# 0056. 5 つの Claude home で使っている plugin の和集合を、全 home 共通の宣言にする

**Date:** 2026-10-16
**Status:** Proposed
**ID:** ADR-0056
**Title:** 5 つの Claude home で使っている plugin の和集合を、全 home 共通の宣言にする
**Decided-date:** —
**Decision-maker:** Hiroto N.
**Decision-maker-contact:** @hironow
**Author:** Claude Code（owner session）
**Author-contact:** @hironow
**Supersedes:** [ADR-0048](0048-required-claude-plugins.md) の一部（Decision 1「各 marketplace をリリースタグで pin する」を、claude-plugins-official と hironow-plugins について）
**Superseded-by:** none
**Related:** [ADR-0048](0048-required-claude-plugins.md)、[ADR-0037](0037-layered-claude-settings-fragments.md)、[ADR-0044](0044-python-toolchain-uv-ruff-ty.md)、[ADR-0049](0049-headroom-mandatory-base-tooling.md)
**Consultation-trace:** —（この PR で所有者の裁定を受ける）

## やさしい説明

Claude Code の plugin（追加機能のまとまり）は、これまで home（設定の置き場所）ごとに手で入れていた。
そのため home によって入っているものがばらばらだった。
この提案では、5 つの home で使っているものを合わせた 40 個を dotfiles に書き、`just deploy` で全部の home にそろえる。

## Context

[ADR-0048](0048-required-claude-plugins.md) は、`dump/harness/claude-plugins.json` に必須の plugin を宣言し、`scripts/claude_plugins.py` が plugin CLI で全 Claude home に入れると決めた。
宣言にあるのは `codex@openai-codex` だけだった。
Decision 1 は、各 marketplace（plugin の配布元）をリリースタグで固定（pin）すると定める。

2026-10-16 に、この Mac の 5 つの home（`~/.claude`、`~/.claude-work-a`〜`d`）を `claude plugin list --json` で数えた。

- user scope（利用者単位）で有効な plugin は、home ごとに 6〜37 個で、中身もばらばらだった。
- 5 home の和集合は 43 個で、marketplace は 4 つ（claude-plugins-official、googlechrome、hironow-plugins、openai-codex）。

同じ日に、使い捨ての `CLAUDE_CONFIG_DIR` で plugin CLI を試した（Claude Code CLI、macOS）。

- `claude plugin marketplace add owner/repo#<40 桁の commit SHA>` は失敗した。git URL に SHA を付けても同じだった。
  エラーは `fatal: Remote branch <sha> not found in upstream origin`。CLI は `git clone --branch <ref>` を使うので、ref にはタグかブランチしか書けない。
- `anthropics/claude-plugins-official` にはタグが 1 つも無い。
- `GoogleChrome/modern-web-guidance#v0.0.193` のようなタグ指定は通った。入った plugin の version は `0.0.193` で、ADR-0048 の version 照合がそのまま効く。
- hironow-plugins は dotfiles 自身の `.claude-plugin/marketplace.json` を指す local marketplace で、CLI は絶対パスで記録する。絶対パスは機体と OS ごとに違う。
- marketplace を remove すると、その marketplace の plugin も消える（ADR-0048 の記述どおり）。

和集合のうち 3 個は、共通にすると問題が出る。

- `pyright-lsp` は pyright を動かす。[ADR-0044](0044-python-toolchain-uv-ruff-ty.md) は pyright を機体から除くと決めている。
- `bigquery-data-analytics` と `knowledge-catalog` は GCP の project ID が未設定だと MCP サーバー（Claude に外部の道具をつなぐ常駐プロセス）が起動しない（`project: null` の検証エラー）。
  project は home ごとに違う。

## Decision

（Proposed。裁定後に Accepted の MUST 文を書く。提案の中身は Options の A 案。）

## Options

- **A) 和集合を共通の宣言にし、pin できないものだけ例外にする（提案）**
  1. `dump/harness/claude-plugins.json` は、5 home で user scope かつ有効な plugin の和集合から `pyright-lsp`、`bigquery-data-analytics`、`knowledge-catalog` を除いた 40 個を宣言する（MUST）。配布先は ADR-0048 のとおり、存在するすべての Claude home。
  2. GitHub の marketplace はリリースタグで pin する（MUST）。例外は `claude-plugins-official` だけで、pin せず既定ブランチに追従する。タグが無く、CLI が SHA を受け付けないため。
  3. hironow-plugins は repo 相対パス（`./.claude-plugin/marketplace.json`）で宣言する（MUST）。`scripts/claude_plugins.py` が repo root 基準の絶対パスに直す。中身は dotfiles の追跡済みファイルなので、pin は要らない。
  4. タグを選ぶときは、公開から 7 日以上たった版を使う（依存方針の cooldown（待機期間））。googlechrome は `v0.0.193` にする。
  5. `pyright-lsp` は宣言せず、入っている home からは外す。

    - 利点: どの home でも同じ道具が使える。新しい機体も `just deploy` 1 回でそろう。
    - コスト: claude-plugins-official の更新は、レビューなしで入る。MCP を持つ plugin（firebase、linear、context7、playwright など）が全 home で起動する。

- **B) 個人 home（`~/.claude`）だけに宣言を足し、work home は codex だけのままにする**
    - 利点: work 用アカウントの home に個人の道具が入らない。
    - コスト: home ごとの宣言が必要になり、`claude_plugins.py` の宣言形式を変えることになる。home ごとのばらつきも残る。

- **C) claude-plugins-official を自前で fork し、タグを打って pin する**
    - 利点: 公式の更新もレビューを通る。
    - コスト: fork の同期作業が増える。全 home で marketplace の差し替え（＝plugin を一度消して入れ直す）が起きる。

## Consequences

### Positive

- 5 つの home と、今後 `just deploy` する機体で、plugin の組み合わせが同じになる。
- `just doctor` の `claude-plugins` 行が、宣言とのずれを home ごとに教える。

### Negative

- claude-plugins-official の中身は、upstream の変更がそのまま入る。plugin が要求する npm パッケージの版が上がると、npm の cooldown で MCP が一時的に起動しないことがある（2026-10-16 時点の chrome-devtools-mcp@1.11.0 がそう）。
- MCP を持つ plugin が全 home で起動するので、起動が遅くなり、ネットワーク接続も増える。
- googlechrome を pin すると、すでに追従で入っている home では marketplace の差し替えが起き、modern-web-guidance が 0.0.194 から 0.0.193 に下がる。
- ADR-0048 の本文は「各 marketplace をタグで pin」のまま残る。読む人は、この ADR とあわせて読む必要がある。

### Neutral

- 宣言にない plugin は消さない（ADR-0048 の動きのまま）。work home にだけある marketplace や plugin は残る。
- bigquery-data-analytics と knowledge-catalog は、必要な home で `/plugin configure` して有効にすれば使える。

## 反転記録 (Reversal)

none

## 裁定欄

- [ ] A 案で採択 / [ ] B 案で採択 / [ ] C 案で採択 / [ ] 修正のうえ採択（修正点: ____） / [ ] 却下（理由: ____） / [ ] 保留
- 決定者・日付:
- A 案で採択したときの作業: ADR-0048 の Status を `Superseded by [0056]`（部分）に変える（これだけが許される編集）。merge 後に main の checkout で `just claude-plugins-install` を実行する。work home から pyright-lsp を外し、`~/.claude` の bigquery-data-analytics と knowledge-catalog を無効にする。
- B 案で採択したときの作業: 宣言を codex だけに戻し、home ごとの宣言形式を別 PR で提案する。
- C 案で採択したときの作業: fork を作ってタグを打ち、宣言の source を fork に替える。
- 却下・保留したときの作業: 宣言を codex だけに戻す。local marketplace 対応のコード（`resolve_source`）は残してよい。
