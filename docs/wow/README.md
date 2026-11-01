# What's New in Streaming (Google Cloud Next '26) — ファクトチェック済みノート

Next '26 のストリーミング新機能 4 つを、一次情報（cloud.google.com 公式ドキュメント・
Google Cloud Blog・Apache Beam pydoc）で裏取りし、実装で使える形にまとめたノート。
元は KDDI アイレットの記事
[Google Cloud Next '26: ストリーミング基盤の最新アップデート (iret.media/194869)](https://iret.media/194869)。

- 元記事: 田村直樹（KDDI アイレット / Google Cloud Partner Top Engineer 2025 & 2026）
  による Next '26 セッション **"What's new in streaming: Real-time data for agentic AI"**
  のレポート（公開日 2026-04-24）。
- 元セッション:
  [What's new in streaming: Real-time data for agentic AI (Next '26, Las Vegas)](https://www.googlecloudevents.com/next-vegas/session/3912220/what's-new-in-streaming-real-time-data-for-agentic-ai)
- 公式総括ブログ:
  [Streaming AI news from Next '26 (Google Cloud Blog, 2026-05-19)](https://cloud.google.com/blog/products/data-analytics/streaming-ai-news-from-next26)

## テーマ

Next '26 の主張は、ストリーミング基盤が「データを **運ぶ** パイプライン」から
「エージェント向けに **意味づけ・推論する** パイプライン」へ移った、というもの。記事の
キャッチコピー「流れるデータを、考えるデータへ」はこの転換を指し、公式ブログと整合する。

## 4 機能と判定

記事の 4 機能は **すべて実在** し、launch stage も公式と一致する。#4 だけ名前が記事の意訳。
記載ごとの判定は [fact-check.md](fact-check.md) にある。

| # | 機能（詳細ノート） | 公式での実体 | Launch stage | 判定 |
|---|---|---|---|---|
| 1 | [Pub/Sub AI Inference SMT](01-pubsub-ai-inference-smt/README.md) — Pub/Sub の中で直接モデルを呼ぶ | AI Inference Single Message Transform | **GA** | ✅ 正確 |
| 2 | [Pub/Sub Bigtable Subscriptions](02-pubsub-bigtable-subscriptions/README.md) — コード不要で Pub/Sub → Bigtable | Bigtable subscription（export subscription の一種） | **Preview** | ✅ 正確 |
| 3 | [BigQuery Continuous Query — Stateful](03-bigquery-continuous-queries-stateful/README.md) — 常駐 SQL で JOIN / windowing / 生成 AI | continuous queries の stateful operations | **Preview** | ✅ 正確 |
| 4 | [Dataflow — In-stream Agents](04-dataflow-streaming-agents/README.md) — Dataflow に ADK エージェントを組み込む | Dataflow + `RunInference` + `ADKAgentModelHandler` + ADK | GA（RunInference）。ADKAgentModelHandler は Beam 同梱 | ⚠️ 機能は実在。"In-stream Agents" は製品名ではない |

用語の注意（「In-stream Agents」「Elastic Inference Queue」「Gemini Enterprise Agent
Platform」）は [fact-check.md の要注意点まとめ](fact-check.md#要注意点まとめ) を見る。
記事の図にある Bigtable のマテリアライズドビューは Bigtable Subscriptions とは別機能
（[02](02-pubsub-bigtable-subscriptions/README.md) を参照）。

## 記事にない関連発表（公式ブログより）

同じセッション / ブログで、エージェントからストリーミング基盤を「使う」側の発表もあった。

- **Model Context Protocol (MCP) support（GA）** — エージェントがフルマネージドな MCP
  エンドポイント経由で各サービスを操作できる。
    - Pub/Sub: <https://docs.cloud.google.com/pubsub/docs/use-pubsub-mcp>
    - Bigtable: <https://docs.cloud.google.com/bigtable/docs/use-bigtable-mcp>
    - BigQuery: <https://docs.cloud.google.com/bigquery/docs/use-bigquery-mcp>
    - Managed Service for Apache Kafka:
      <https://docs.cloud.google.com/managed-service-for-apache-kafka/docs/use-managed-service-for-apache-kafka-mcp>
- **ADK integration（GA）** — ADK エージェントが Pub/Sub / Bigtable / BigQuery 等の
  リアルタイムデータに pre-built integration で接続:
  <https://adk.dev/integrations/?topic=google>
- **Dataflow unified embeddings sinks** — 詳細は
  [04 の関連機能](04-dataflow-streaming-agents/README.md#関連機能-dataflow-unified-embeddings-sinks)。

## アーキテクチャ全体像

```text
                 +---------------------------+
   publishers -> |  Pub/Sub (topic)          |
                 |   + AI Inference SMT (GA)  |--enriched msg--+
                 +---------------------------+                 |
                      |                  |                     v
        Bigtable sub  |                  | BigQuery sub   +-----------+
        (Preview)     v                  v                |  Dataflow |
                 +----------+      +-------------+         | RunInfer. |
                 | Bigtable |      |  BigQuery   |         | + ADK     |
                 | (serving)|      | continuous  |         | agent     |
                 +----------+      | query (CQ)  |         +-----------+
                      ^            | stateful(PV)|              |
                      |            +-------------+              v
                      +--reverse ETL--+   |   +--> Pub/Sub / Spanner / Bigtable
                                          v
                                  AI.GENERATE_TEXT etc.
```

Legend / 凡例:

- publishers: パブリッシャー（イベント発行元）
- AI Inference SMT: Pub/Sub 内でモデル推論を付与する変換（GA）
- enriched msg: 推論結果を付与済みのメッセージ
- Bigtable sub (Preview): Bigtable サブスクリプション（プレビュー）
- BigQuery sub: BigQuery サブスクリプション
- continuous query (CQ) stateful (PV): 常駐クエリの stateful 処理（プレビュー）
- reverse ETL: 分析結果を低レイテンシ配信系へ書き戻す処理
- RunInference + ADK agent: Dataflow にエージェントを組み込むノード
- serving: アプリへの低レイテンシ配信

## 最初に触るなら

- 3 機能横断の E2E デモ（BigQuery stateful CQ + Pub/Sub SMT + ADK）:
  [03 の公式サンプル](03-bigquery-continuous-queries-stateful/README.md#公式サンプル実装--codelab)
- Dataflow にエージェントを載せる最小例:
  [04 の検証済み最小例](04-dataflow-streaming-agents/README.md#検証済み最小例)

> 検証日: 2026-06-08 時点の公式ドキュメントに基づく。Preview 機能は仕様が変わりうるので、
> 実装前に各公式ページの最新版を確認する。
