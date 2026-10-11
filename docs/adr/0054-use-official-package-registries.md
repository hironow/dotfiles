# 0054. Flatt のミラーをやめ公式の取得元を使う

**Date:** 2026-10-11
**Status:** Accepted
**ID:** ADR-0054
**Decided-date:** 2026-10-11
**Decision-maker:** Hiroto N.
**Decision-maker-contact:** @hironow
**Author:** Codex
**Author-contact:** @hironow
**Supersedes:** [ADR-0028](0028-flatt-pypi-mirror-default-index.md)
**Consultation-trace:** [除去 PR の差分](https://github.com/hironow/dotfiles/pull/464)

## Context

2026-10-11、所有者は fork とアーカイブを除く個人リポジトリの Flatt 利用を点検し、残存する各リポジトリの除去と検証、squash merge を依頼した。
このリポジトリでは4つの uv project、シェル設定、環境設定の生成処理と検査に Flatt が残っていた。
既存 PR #463 はエージェント規約の更新も含むため、除去部分を独立した PR で扱う。

## Decision

Python は pypi.org、npm は registry.npmjs.org、Go は proxy.golang.org を使う。
uv の7日間の待機と npm の min-release-age を維持する。
Flatt の index、取得 URL、必須検査、専用の relock 処理を削除する。
環境設定の生成処理は Flatt を再設定せず、既存の npm Flatt registry の行を除去する。
lock の版は維持する。ただし main の mise と不一致だった Ruff と ty は宣言と lock を同じ版に合わせ、一致検査を維持する。

## Consequences

公式の取得元から直接インストールでき、Flatt への接続は不要になる。
Flatt のマルウェア検査は利用しない。公開直後の版を避ける待機設定と既存の検査は残す。
他の機体の設定を更新するには、マージ後の main で `just harden-env` を実行する。
既存の Accepted ADR の本文は変更せず、ADR-0028 の状態だけを更新する。
