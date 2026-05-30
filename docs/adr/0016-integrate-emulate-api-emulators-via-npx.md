# 0016. Integrate vercel-labs/emulate API emulators via npx wrapper

**Date:** 2026-05-30
**Status:** Accepted

## Context

`emulator/` は datastore 系エミュレータ (postgres / bigtable / spanner / neo4j /
qdrant / elasticsearch / firebase) が中心で、 SaaS / API (github, google, stripe
等) のローカル代替が無かった。 agent 開発と `payments/` (ACP / AP2) において
API / auth / commerce のローカル検証需要がある。
[vercel-labs/emulate](https://github.com/vercel-labs/emulate) がこの空白を埋める。

## Decision

emulate を vendor せず **npx 薄ラッパ**で統合する。

- `just emu-api` が `npx -y emulate@0.6.0 --service <list> --port 4100 --seed
  emulate.config.yaml` を **host で**実行する (Node CLI を host に直接 bind し、
  コンテナ内 localhost-binding の取り回し問題を回避)
- 設定は `emulator/emulate/emulate.config.yaml` のみ git 管理
- `emulate@0.6.0` に pin。 要望の全 9 サービス (github / google / slack / apple /
  microsoft / stripe / clerk / okta / resend) が公開 CLI で利用可能なことを実機検証済み
  (公式 README の列挙は 7 種だが実際にはこれらも `--service` で起動する)
- base port 4100 (firebase UI 4000 との衝突回避)。 ポートは `--service` 順の
  base + index で確定する (github 4100 … resend 4108) ため portless alias を
  確定値で `config/portless-aliases.yaml` に登録済み

## Consequences

### Positive

- vendor 不要で常に pin 版を npm から取得、 dotfiles を肥大させない
- datastore + API の両輪がローカルで揃う

### Negative

- 初回 `npx` DL のネットワーク依存
- `services=` の集合 / 順序を変えると alias ポートと乖離する (順序がポートを決める)

### Neutral

- compose service ではなく host プロセスとして動く (compose とは別ライフサイクル)
