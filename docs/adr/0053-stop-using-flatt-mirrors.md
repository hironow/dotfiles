# 0053. Flatt のパッケージミラーをやめ、公式の取得元に戻す

**Date:** 2026-10-11
**Status:** Proposed
**ID:** ADR-0053
**Title:** Flatt のパッケージミラーをやめ、公式の取得元に戻す
**Decided-date:** none
**Decision-maker:** Hiroto N.
**Decision-maker-contact:** @hironow
**Author:** Claude Code（owner session）
**Author-contact:** @hironow
**Deadline:** 2026-10-16
**Supersedes:** [ADR-0028](0028-flatt-pypi-mirror-default-index.md)
**Superseded-by:** none
**Related:** [ADR-0052](0052-renew-global-agent-instructions.md)、[依存の方針](../../ROOT_AGENTS_docs_agents_dependency-policy.md)
**Consultation-trace:** [公開PR #463](https://github.com/hironow/dotfiles/pull/463)

## やさしい説明

Python と npm のパッケージを、Flatt Security のミラーではなく公式の取得元（pypi.org と npmjs）から取る。
新しい版が出てから 7 日待って入れる仕組みは、そのまま残す。

## Context

ADR-0028 は、uv の既定の取得元を Flatt Security の PyPI ミラー（`pypi.flatt.tech`）にした。
この repo の 4 つの uv project は、`pyproject.toml` でこのミラーを宣言し、lock もミラーの URL で書いていた。
各機体では `just harden-env` が `~/.config/uv/uv.toml` に同じミラーを書き、`.zshrc` が pip にも同じミラーを使わせていた。
一部の機体は、`~/.npmrc` に npm のミラー（`npm.flatt.tech`）を手で設定していた。

ミラーには、新しい版がなかなか届かない。
まだ載っていない版は解決できず、`uv sync` でも版が下がることがあった。
ty のように新しい版が要る道具だけ、pypi.org を明示する設定を別に足す必要もあった。
これは「新しく、より安全な版を取る」という依存の方針に合わない。

2026-10-11、所有者は Flatt の利用をやめると決めた。
理由は、新しい版が届かないことである。
範囲はこの repo と、`just harden-env` が設定する全機体とする。
ほかの repo は別の作業で扱う。
7 日の待機（uv の `exclude-newer = "7 days"`、npm の `min-release-age=7`）は残す。

## Decision

1. uv project は pypi.org を既定の取得元にする。Flatt の index と、その代わりに足した pypi.org の明示 index を `pyproject.toml` から消す。
2. 4 つの lock を、版を変えずに pypi.org の URL で作り直す。
3. 各 uv project は、7 日の待機（`exclude-newer = "7 days"`）を自分の `pyproject.toml` で宣言する。機体の設定には頼らない。
4. Flatt を前提にした検査（`check_uv_flatt_index.sh` とその CI の step）と、Flatt 経由で lock を作り直す recipe（`relock-uv`）を消す。
5. `just harden-env` は、uv の設定に 7 日の待機だけを書き、`~/.npmrc` から Flatt の registry の行だけを消す。`.zshrc` は pip に Flatt を使わせない。

## Options Considered

- **A) Flatt をやめ、公式の取得元に戻す（この案）**：新しい版が届く。マルウェアの走査はなくなるが、7 日の待機で、公開直後に見つかる悪い版は避けられる。
- **B) Flatt を続け、届かない版だけ pypi.org を明示する**：走査は残る。届かない版が出るたびに例外の設定を足す手間が続く。
- **C) uv だけ公式に戻し、npm は Flatt のまま**：手間が半分だけ残り、道具ごとに取得元が違う。

## Consequences

- **Positive**：新しい版が公開の 7 日後に届く。版の例外のための pypi.org の明示 index が要らなくなる。外部のミラーが止まっても CI と開発は止まらない。
- **Negative**：Flatt のマルウェア走査がなくなる。守りは 7 日の待機と、Dependabot の security alert になる。
- **Neutral**：ほかの機体は、merge のあとに `just harden-env` を実行すると設定が変わる。ほかの repo の Flatt の設定は、この決定では変えない。

## 他のDRとの照合

ADR-0028 を置き換える。
ADR-0044（Python の道具）の ty の版の扱いは変わらない。ty を pypi.org から取るための明示 index が不要になるだけである。
ADR-0051 の決裁待ち一覧の手順に従い、この記録を決裁待ちとして登録する。

## 裁定・merge前の停止条件

- 所有者が PR #463 で裁定するまで merge しない。
- 裁定後は、この記録の状態、ADR-0028 の状態（`Superseded by [0053]`）、決裁待ち一覧の行、ADR 索引を同じ変更で更新する（ADR-0051）。

## 反転記録 (Reversal)

none（ADR-0028 を置き換える。ADR-0028 の本文は変えない。）
