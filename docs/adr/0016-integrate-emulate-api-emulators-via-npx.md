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
- `emulate@0.6.0` に pin。 公開 CLI で確認済みのサービスは github / google /
  slack / apple / microsoft (他に vercel / aws)。 要望の stripe / clerk / okta /
  resend は `@emulators/*` plugin が deps に同梱されるが公開 CLI での `--service`
  露出が未確認のため、 `services=` 引数で除外可能とし README に検証手順を明記
- base port 4100 (firebase UI 4000 との衝突回避)

## Consequences

### Positive

- vendor 不要で常に pin 版を npm から取得、 dotfiles を肥大させない
- datastore + API の両輪がローカルで揃う

### Negative

- 初回 `npx` DL のネットワーク依存
- emulate@0.6.0 では要望サービスの一部が未露出の可能性 (要初回検証)
- ポート pin 不可 (内部採番) のため portless alias は初回検証後に有効化

### Neutral

- compose service ではなく host プロセスとして動く (compose とは別ライフサイクル)
