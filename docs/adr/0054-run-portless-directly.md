# 0054. portless を just の recipe で包まず、直接使う

**Date:** 2026-10-11
**Status:** Proposed
**ID:** ADR-0054
**Title:** portless を just の recipe で包まず、直接使う
**Decided-date:** none
**Decision-maker:** Hiroto N.
**Decision-maker-contact:** @hironow
**Author:** Claude Code（owner session）
**Author-contact:** @hironow
**Deadline:** 2026-10-18
**Supersedes:** [ADR-0015](0015-adopt-portless-for-local-dev-urls.md) の一部（別名の一括登録と CA 信頼を just の recipe で行う点）
**Superseded-by:** none
**Related:** [ADR-0015](0015-adopt-portless-for-local-dev-urls.md)、[ADR-0016](0016-integrate-emulate-api-emulators-via-npx.md)、[portless の別名一覧](../portless-urls.md)
**Consultation-trace:** 公開PR（この記録を含む PR）

## やさしい説明

portless は、just の recipe を通さずに `portless` コマンドを直接打って使う。
登録する別名の一覧は `docs/portless-urls.md` の1か所にまとめる。

## Context

ADR-0015 は portless を採用し、別名を `config/portless-aliases.yaml` に集めて、`just portless-up` で一括登録、`just portless-down` で解除、`just portless-trust` で CA を信頼すると決めた。
あわせて `just portless-ls`、`just portless-doc`、`just portless-doc-check` もでき、`docs/portless-urls.md` はその YAML から生成し、`just ci` がずれを検査していた。

`portless-trust` と `portless-ls` は、`portless trust` と `portless list` を1行で包むだけである。
`portless-up` と `portless-down` は YAML を読んで `portless alias` を繰り返す。
portless には、ファイルから別名をまとめて登録する機能はない。

2026-10-11、所有者は portless の recipe を6つとも消し、使う箇所では `portless` を直接使うと決めた。

## Decision

1. justfile から portless の recipe 6つ（`portless-up`、`portless-down`、`portless-trust`、`portless-ls`、`portless-doc`、`portless-doc-check`）と、内部の `_portless-pairs` を消す。`just ci` から `portless-doc-check` を外す。
2. 別名の一覧は `docs/portless-urls.md` の `portless alias <name> <port> --force` の並びを唯一の置き場所にする。`config/portless-aliases.yaml` と生成スクリプト `scripts/generate-portless-doc.sh` は消す。
3. ADR-0015 のうち、portless を使うこと、HTTP(S) の UI だけを対象にすること、TCP は別名にしないことは変えない。

## Options Considered

- **A) recipe を消し、直接使う（この案）**：道具をそのまま使うので、portless の使い方がそのまま通じる。20件の別名は手で登録する。
- **B) 1行の shorthand（`portless-trust`、`portless-ls`）だけ消す**：一括登録は残るが、薄い wrapper と一覧の生成と検査が残る。
- **C) 今のまま**：手間は少ないが、wrapper を覚える必要が残る。

## Consequences

- **Positive**：portless の公式の使い方と同じ手順になる。生成スクリプト、YAML、CI の検査がなくなり、保守する物が減る。
- **Negative**：20件の別名を登録するには、`docs/portless-urls.md` のコマンドを実行する必要がある。一覧とポートのずれを機械で検査しない（以前の検査も YAML と docs の一致だけで、compose の実ポートとは照合していなかった）。
- **Neutral**：`portless` は引き続き mise（`npm:portless`）で入る。

## 他のDRとの照合

ADR-0015 の一部を置き換える。ADR-0015 の本文は変えず、裁定後に状態の行だけを更新する。
ADR-0016 は emulate のポートを YAML に登録したと書いているが、Accepted の記録なので変えない。今のポートの一覧は `docs/portless-urls.md` にある。
ADR-0051 の決裁待ち一覧の手順に従い、この記録を決裁待ちとして登録する。

## 裁定・merge前の停止条件

- 所有者がこの記録を含む PR で裁定するまで merge しない。
- 裁定後は、この記録の状態、ADR-0015 の状態の行、決裁待ち一覧の行、ADR 索引を同じ変更で更新する（ADR-0051）。

## 反転記録 (Reversal)

none（ADR-0015 の一部を置き換える。ADR-0015 の本文は変えない。）
