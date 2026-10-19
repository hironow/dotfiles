# 0059. remote-pi を外し、host 提供パッケージを vendor させない

**Date:** 2026-10-19
**Status:** Accepted
**ID:** ADR-0059
**Title:** remote-pi を外し、host 提供パッケージを vendor させない
**Decided-date:** 2026-10-19
**Decision-maker:** Hiroto N.
**Decision-maker-contact:** @hironow
**Author:** Pi（owner session）
**Author-contact:** @hironow
**Supersedes:** none
**Superseded-by:** none
**Related:** [ADR-0058](0058-pi-web-search-ollama.md)、[ADR-0038](0038-declarative-third-party-skills.md)
**Consultation-trace:** 本セッションでの所有者の選択（選択肢 A）

## やさしい説明

Pi の extension は、Pi 本体が用意している部品（`@earendil-works/pi-coding-agent` など）を自分で持ってはいけない。
持つと、extension が本体と別物の古い部品を使い、壊れるおそれがある。
`remote-pi` という extension がこの規則を破っていたので、外した。
必要になったら、相手側が直ってから入れ直す。

## Context

Pi は extension に対し、Pi が用意するパッケージ（`@earendil-works/pi-ai`、`@earendil-works/pi-agent-core`、`@earendil-works/pi-coding-agent`、`@earendil-works/pi-tui`、`typebox`）を `peerDependencies` に `"*"` で宣言するよう求める。
`dependencies` に書くと Pi が警告し、インストールされた実体が extension のモジュール解決を素通りして重複モジュールを作りうる（公式 docs「Create a package」）。

2026-10-19、`npm:remote-pi@0.7.0`（npm 上の最新）が三つを `dependencies` で宣言していることを確認した。
隔離した `PI_CODING_AGENT_DIR` に単体で入れて比べた結果:

- `pi-subagents` 単体: `@earendil-works/*` も `typebox` も vendor しない（`peerDependencies` のみ）。
- `remote-pi` 単体: `@earendil-works/pi-coding-agent`、`@earendil-works/pi-tui`、`typebox` の **0.79.10** を `~/.pi/agent/npm/node_modules` に vendor する。

本体（pi 1.3.0）の同パッケージは 1.3.0 なので、extension から見て古い実体が同居する。実際 `npm ls` はそれらを `invalid` と判定し（`pi-background-tasks` は `^0.81.1 || …`、`pi-goal-x` は `>=0.83.0 <2.0.0`、`pi-memory` は `>=0.81.1` を要求）、Pi も起動時に警告していた。
Pi の extension loader はこれらを alias で本体へマップし、`pi-subagents` の detached runner も `pi-tui` だけは本体へ redirect するため、通常は回避される。ただし runner が redirect するのは `pi-tui` のみで、`pi-coding-agent` や `typebox` は物理コピーを掴みうる（`pi-subagents` の CHANGELOG は background subagent の起動失敗を host package 解決で何度も直している）。

同時に、`pi-subagents` 0.79.1 が Pi 1.3.0 で動作することを実機で確認した（`oracle` サブエージェントが回答）。
Pi 本体に subagent 機能は無く、同梱の example (`examples/extensions/subagent`) のみなので、`pi-subagents` は残す。

## Decision

1. `dump/harness/pi-packages.json` から `npm:remote-pi` を外す。
2. `scripts/install_pi_extensions.py` の retire 対象に加え、まだ宣言している機体の settings から `pi remove` で除く（`npm:pi-web-access` と同じ仕組み）。
3. 再導入は、remote-pi が三つを `peerDependencies` に移してから（または同等の代替が出てから）行う。

## Consequences

### Positive

- 古い host package の実体が消え、`npm ls` の `invalid` と Pi の警告が消える。
- extension が本体の `@earendil-works/*` / `typebox` を一意に解決する。
- `pi-subagents` の background runner が物理コピーを掴む余地が無くなる。

### Negative

- remote-pi の機能（モバイルアプリ、同一マシン内の agent mesh）を失う。
- 使いたい場合は upstream の修正後に `pi install npm:remote-pi` で戻す必要がある。

### Neutral

- 退避の仕組みは ADR-0058 の `RETIRED_PACKAGES` を共用する（片方だけ設定されていても他方の除去は起きない）。

## 実機確認 (2026-10-19)

- `pi remove npm:remote-pi` 後、`@earendil-works/pi-coding-agent`・`pi-tui`・`typebox` の実体が消え、`npm ls` が `(empty)`。
- 起動警告が消え、`pi -p "reply with just: ok"` が `ok`。
- 残った `@earendil-works/pi-voice` は extension 自身であり、host 提供パッケージではない（`peerDependencies` のみ）。
