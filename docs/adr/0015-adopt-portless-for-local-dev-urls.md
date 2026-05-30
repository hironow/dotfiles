# 0015. Adopt portless for stable .localhost URLs of local HTTP UIs

**Date:** 2026-05-30
**Status:** Accepted

## Context

emulator / telemetry の HTTP UI 群 (firebase UI, mlflow, a2a/mcp inspector,
grafana, prometheus, tempo, loki, qdrant, elasticsearch) は 127.0.0.1 の固定
ポートで露出していた。 ポート番号の暗記・衝突 (`EADDRINUSE`)・複数アプリ間の
cookie / localStorage 混線という local-dev の摩擦がある。

## Decision

[vercel-labs/portless](https://github.com/vercel-labs/portless) を採用し、 HTTP UI を
`<name>.localhost` の安定 URL で公開する。 portless は HTTPS リバースプロキシで、
`portless alias <name> <port>` により portless が起動しない外部管理 (docker)
サービスへも静的ルートを登録できる (`~/.portless/routes.json` に永続)。

- `config/portless-aliases.yaml` に name->port を集約し、 `just portless-up` で
  一括登録 / `just portless-down` で解除、 `just portless-trust` で CA 信頼
- **HTTP(S) UI のみ対象**。 TCP wire protocol (postgres 5433 / pgadapter 55432 /
  neo4j bolt 7687 / bigtable・spanner・qdrant gRPC / elasticsearch transport) は
  portless が proxy できないため alias 対象外とし、 127.0.0.1 ポートのまま据え置く
- emulate のポートは内部採番で非確定のため、 初回起動後に実ポートを検証してから
  alias を有効化する

## Consequences

### Positive

- 安定 URL、 HTTP/2 付き HTTPS、 ポート暗記不要、 アプリ間 cookie 分離
- OAuth redirect / CORS allowlist に使える固定 URL

### Negative

- portless のグローバルインストールと CA trust (`portless trust`) が前提
- proxy は 443 利用時に権限を要する (必要なら custom port `-p`)

### Neutral

- TCP データストアは引き続きポート直接アクセス (二系統のアクセス方式が併存)
