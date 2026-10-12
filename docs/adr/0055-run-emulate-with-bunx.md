# 0055. emulate は npx ではなく bunx で動かす

**Date:** 2026-10-12
**Status:** Accepted
**ID:** ADR-0055
**Title:** emulate は npx ではなく bunx で動かす
**Decided-date:** 2026-10-12
**Decision-maker:** Hiroto N.
**Decision-maker-contact:** @hironow
**Author:** Claude Code（owner session）
**Author-contact:** @hironow
**Supersedes:** [ADR-0016](0016-integrate-emulate-api-emulators-via-npx.md) の一部（`just emu-api` が `npx` で動く点）
**Superseded-by:** none
**Related:** [ADR-0016](0016-integrate-emulate-api-emulators-via-npx.md)、[ADR-0027](0027-bun-only-retire-per-repo-pnpm-carveout.md)
**Consultation-trace:** [公開PR #470の所有者裁定](https://github.com/hironow/dotfiles/pull/470#issuecomment-6113089576)

## やさしい説明

`just emu-api` は、emulate を `npx` ではなく `bunx` で起動する。
Node のコマンドは bun だけで動かす、という全体の決まりに合わせる。

## Context

ADR-0016 は、emulate を vendor せずに `npx` の薄いラッパで動かすと決めた。
その時点で pin は `emulate@0.6.0` だった。いまの recipe は `emulate@0.8.0` で、ADR と pin がずれている。

全エージェント共通の指示は「Node は bun だけを使う」と定める。
[ADR-0027](0027-bun-only-retire-per-repo-pnpm-carveout.md) は、エージェントが `npm` `npx` `pnpm` `yarn` を打つことを禁じた。
ただし recipe の中身までは対象外で、`emu-api` は `npx` を実行したまま残っていた。

2026-10-12 に実機で確かめた（bun 1.4.2、macOS）。

- `bunx emulate@0.8.0 --service <9 サービス> --port 4100 --seed emulate.config.yaml` が起動した。
- 9 サービスが 4100 から 4108 で待ち受け、`tokens` と seed を読んだ。
- `just emu-api-stop` で全部止まり、ポートが閉じた。
- emulate 0.8.0 は `#!/usr/bin/env node` の shebang を持つ。bunx はそれを守るので、中では Node が使われる。

## Decision

`just emu-api` は `bunx emulate@0.8.0 ...` で起動する。事前確認は `command -v bunx` にする。

## Options

- **A) bunx に替える（採択）**: 実行する道具が bun に揃う。`tests/unit/test_justfile_bun_only.py` が、justfile に npm 系の実行が残っていないことを見張る。
- **B) npx を例外として残す**: ADR-0016 のまま。ガードの許可リストに `emu-api` の1行を入れ、理由を書く。bun だけという決まりに例外が1つ残る。

## Consequences

### Positive

- justfile が「Node は bun だけ」で一貫する。
- 初回取得も bun の cache を使う。

### Negative

- emulate を bun で起動した経験が短い。bun の更新で挙動が変わる恐れがある。
- ADR-0016 の本文は `npx` のまま残る。読む人は、このADRとあわせて読む必要がある。

### Neutral

- 動くのは host プロセスのままで、compose とは別のライフサイクルである。

## 反転記録 (Reversal)

none

## 裁定欄

- [x] A 案で採択 / [ ] B 案で採択 / [ ] 修正のうえ採択（修正点: ____） / [ ] 却下（理由: ____） / [ ] 保留
- 決定者・日付: Hiroto N.、2026-10-12
- A 案で採択したときの作業: ADR-0016 の Status を `Superseded by [0055]` に変える（これだけが許される編集）。実施済み。
- B 案で採択したときの作業: 許可リストに `emu-api` を入れ、この PR の `emu-api` の変更を戻す。
- 却下・保留したときの作業: 同じ。
