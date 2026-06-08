# What's New in Streaming (Google Cloud Next '26) — ファクトチェック済みノート

このディレクトリは、KDDI アイレットの記事
[Google Cloud Next '26: ストリーミング基盤の最新アップデート (iret.media/194869)](https://iret.media/194869)
の内容を **一次情報（cloud.google.com 公式ドキュメント・Google Cloud Blog・Apache Beam
pydoc）と突き合わせて裏取りし**、「実際にどう実装で使えるのか」まで踏み込んでまとめた
技術ノートである。

- 元記事: 田村直樹（KDDI アイレット / Google Cloud Partner Top Engineer 2025 & 2026）
  による Next '26 セッション **"What's new in streaming: Real-time data for agentic AI"**
  のレポート（公開日 2026-04-24）。
- 元セッション:
  [What's new in streaming: Real-time data for agentic AI (Next '26, Las Vegas)](https://www.googlecloudevents.com/next-vegas/session/3912220/what's-new-in-streaming-real-time-data-for-agentic-ai)
- 公式総括ブログ:
  [Streaming AI news from Next '26 (Google Cloud Blog, 2026-05-19)](https://cloud.google.com/blog/products/data-analytics/streaming-ai-news-from-next26)

## TL;DR — テーマ

ストリーミング基盤の位置づけが「データを **運ぶ** パイプライン（data transfer pipeline）」
から「エージェント向けに **意味づけ・推論する** インテリジェンスパイプライン（intelligence
pipeline for agents）」へ移った、というのが Next '26 の主張。記事のキャッチコピー
「流れるデータを、考えるデータへ」はこの転換を指しており、**公式ブログの内容と整合する**。

## ファクトチェック結果サマリ

記事が挙げた 4 つの目玉は **すべて実在の機能** であり、launch stage の記述も公式と一致する。
1 点だけ用語の注意が要る（下表 ★）。

| # | 記事の記述 | 公式での正式名称 / 実体 | Launch stage | 判定 |
|---|---|---|---|---|
| 1 | Pub/Sub AI Inference SMT | AI Inference [Single Message Transform](https://docs.cloud.google.com/pubsub/docs/smts/ai-inference-smt) | **GA** | ✅ 正確 |
| 2 | Pub/Sub Bigtable Subscriptions | [Bigtable subscription](https://docs.cloud.google.com/pubsub/docs/bigtable-subscriptions)（export subscription の一種） | **Preview** | ✅ 正確 |
| 3 | BigQuery Continuous Query — Stateful Data Processing | [continuous queries](https://docs.cloud.google.com/bigquery/docs/continuous-queries) の stateful operations（JOIN / 集約 / windowing） | **Preview** | ✅ 正確 |
| 4 | Dataflow — In-stream Agents | ★ Dataflow + `RunInference` + [`ADKAgentModelHandler`](https://beam.apache.org/releases/pydoc/current/apache_beam.ml.inference.agent_development_kit.html) + ADK | GA（RunInference は GA。ADKAgentModelHandler は Beam 同梱） | ⚠️ 機能は実在。ただし "In-stream Agents" は **正式な製品名ではなく記事の意訳** |

### ★ 用語の注意（重要）

記載ごとの判定は [fact-check.md](fact-check.md) に分離した。要注意は以下の 4 点。

- **「In-stream Agents」は SKU / 製品名ではない。** 公式は "event-driven autonomous
  agents in Dataflow" や「agentic logic を Dataflow パイプラインの first-class node として
  扱う」と表現する。実装の実体は **Apache Beam の `RunInference` トランスフォーム + 新しい
  `ADKAgentModelHandler` モデルハンドラ + [ADK (Agent Development Kit)](https://google.github.io/adk-docs/)**
  の組み合わせ。詳細は [04-dataflow-streaming-agents/](04-dataflow-streaming-agents/README.md)。
- **「Elastic Inference Queue」は公式用語ではない。** 公式ドキュメントに該当する製品 / 機能名は
  存在せず、AI Inference SMT の **フロー制御機能**（エンドポイント過負荷を避けるための
  レート自動調整）をスライドで言い換えた表現とみられる。詳細は
  [01-pubsub-ai-inference-smt/](01-pubsub-ai-inference-smt/README.md)。
- **「Gemini Enterprise Agent Platform」= Vertex AI のリブランド。** Next '26 前後で
  Vertex AI が "Agent Platform" / "Gemini Enterprise Agent Platform" に改称された。公式
  docs も "Agent Platform (previously Vertex AI)" と併記する。ただし **IAM ロール名
  （`Vertex AI Service Agent` / `Vertex AI User`）や API（`aiplatform.endpoints.predict`）
  は旧称のまま** なので、実装時は両方の名前が混在する点に注意。
- **「Bigtable のマテリアライズドビュー」は Bigtable Subscriptions とは別機能。**
  記事のアーキ図に出てくる Bigtable materialized view は実在する
  [Bigtable continuous materialized views](https://docs.cloud.google.com/bigtable/docs/continuous-materialized-views)
  （SQL 定義の背景集約ビュー）であり、目玉の **Bigtable Subscriptions（raw メッセージの
  直接書き込み）とは別物**。混同しないこと。

## ドキュメント構成

- [fact-check.md](fact-check.md)
  — 記事の **記載ごと** の判定（✅ / ⚠️ / ℹ️ / ❓）の詳細表

実装手順・gcloud / SQL / Beam コード・制約・公式リンク・開発リポジトリは機能ごとのフォルダに
分割した（各フォルダの本体は `README.md`）。

1. [01-pubsub-ai-inference-smt/](01-pubsub-ai-inference-smt/README.md)
   — Pub/Sub の中で直接モデルを呼ぶ（GA）
2. [02-pubsub-bigtable-subscriptions/](02-pubsub-bigtable-subscriptions/README.md)
   — コード不要で Pub/Sub → Bigtable に materialize（Preview）
3. [03-bigquery-continuous-queries-stateful/](03-bigquery-continuous-queries-stateful/README.md)
   — 常駐 SQL で JOIN / windowing / 生成 AI（Preview）
4. [04-dataflow-streaming-agents/](04-dataflow-streaming-agents/README.md)
   — Dataflow に ADK エージェントを組み込む（= 記事の "In-stream Agents"）

## 記事が触れていない関連発表（公式ブログより補足）

記事は 4 機能に絞っているが、同じセッション / ブログでは以下も発表されている。エージェントから
ストリーミング基盤を「使う」側の話なので、実装の全体像として押さえておくと良い。

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
- **Dataflow unified embeddings sinks** — ストリーム内で埋め込み生成し、Cloud Spanner
  （新ベクトル検索）/ AlloyDB に materialize（エージェント RAG の long-term memory 用途）。
  参考: [Deploying EmbeddingGemma at scale with Dataflow](https://developers.googleblog.com/en/deploying-embeddinggemma-at-scale-with-dataflow/)

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

## サンプル実装 / codelab（2026-06 実在確認済み）

各機能の詳細サンプルは機能別ドキュメントの「サンプル実装」節に記載。**最初に触るなら** 以下の
2 つが効率的。

- **3 機能横断 E2E デモ**（BigQuery stateful CQ + Pub/Sub SMT + ADK エージェント）:
  公式 codelab
  [Build an Event-Driven Data Agent with BigQuery and ADK](https://codelabs.developers.google.com/next26/bigquery-adk-event-driven-agents)
  / GitHub
  [`GoogleCloudPlatform/devrel-demos` → `data-analytics/event_driven_agents_demo`](https://github.com/GoogleCloudPlatform/devrel-demos/tree/main/data-analytics/event_driven_agents_demo)
- **Dataflow にエージェントを載せる最小例**: Apache Beam の `ADKAgentModelHandler` 本体 +
  テスト
  [`sdks/python/apache_beam/ml/inference/agent_development_kit.py`](https://github.com/apache/beam/blob/master/sdks/python/apache_beam/ml/inference/agent_development_kit.py)
  / [`..._test.py`](https://github.com/apache/beam/blob/master/sdks/python/apache_beam/ml/inference/agent_development_kit_test.py)

> GitHub のパス・codelab・docs はいずれも 2026-06-08 に GitHub API / 実フェッチで到達確認済み。

## 一次情報リンク集

- Pub/Sub SMT 概要: <https://docs.cloud.google.com/pubsub/docs/smts/smts-overview>
- AI Inference SMT: <https://docs.cloud.google.com/pubsub/docs/smts/ai-inference-smt>
- JavaScript UDF SMT: <https://docs.cloud.google.com/pubsub/docs/smts/udfs-overview>
- Bigtable subscriptions: <https://docs.cloud.google.com/pubsub/docs/bigtable-subscriptions>
- Bigtable subscription 作成: <https://docs.cloud.google.com/pubsub/docs/create-bigtable-subscription>
- Continuous queries 概要: <https://docs.cloud.google.com/bigquery/docs/continuous-queries-introduction>
- Continuous queries 実装: <https://docs.cloud.google.com/bigquery/docs/continuous-queries>
- Dataflow ML: <https://docs.cloud.google.com/dataflow/docs/machine-learning>
- Apache Beam RunInference: <https://beam.apache.org/documentation/ml/about-ml/>
- `ADKAgentModelHandler` pydoc:
  <https://beam.apache.org/releases/pydoc/current/apache_beam.ml.inference.agent_development_kit.html>
- ADK ドキュメント: <https://google.github.io/adk-docs/>
- 公式ブログ（Next '26 総括）:
  <https://cloud.google.com/blog/products/data-analytics/streaming-ai-news-from-next26>

> 検証日: 2026-06-08 時点の公式ドキュメントに基づく。Preview 機能は仕様が変わりうるため、
> 実装前に必ず各公式ページの最新版を確認すること。
