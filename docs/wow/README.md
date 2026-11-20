# What's New in Streaming (Google Cloud Next '26) — Fact-checked notes

Notes verifying four new Next '26 streaming features against primary sources (cloud.google.com
official docs, Google Cloud Blog, and Apache Beam pydoc) and organizing them for implementation.
Based on the KDDI iret article
[Google Cloud Next '26: Latest Updates on Streaming Infrastructure (iret.media/194869)](https://iret.media/194869).

- Original article: Report by Naoki Tamura (KDDI iret / Google Cloud Partner Top Engineer 2025 & 2026)
  on the Next '26 session **"What's new in streaming: Real-time data for agentic AI"**
  (published 2026-04-24).
- Original session:
  [What's new in streaming: Real-time data for agentic AI (Next '26, Las Vegas)](https://www.googlecloudevents.com/next-vegas/session/3912220/what's-new-in-streaming-real-time-data-for-agentic-ai)
- Official summary blog:
  [Streaming AI news from Next '26 (Google Cloud Blog, 2026-05-19)](https://cloud.google.com/blog/products/data-analytics/streaming-ai-news-from-next26)

## Theme

Next '26 argues that streaming infrastructure has shifted from "pipelines that **transport** data" (translated)
to "pipelines that **interpret and infer** for agents" (translated). The article's tagline
"Turn flowing data into thinking data" (translated) refers to this shift and aligns with the official blog.

## Four features and verdicts

All four features in the article **exist**, and their launch stages match official sources. Only #4
uses the article's own loose translation for the name. See [fact-check.md](fact-check.md) for
claim-by-claim verdicts.

| # | Feature (detailed notes) | Official implementation | Launch stage | Verdict |
|---|---|---|---|---|
| 1 | [Pub/Sub AI Inference SMT](01-pubsub-ai-inference-smt/README.md) — Call models directly inside Pub/Sub | AI Inference Single Message Transform | **GA** | ✅ Accurate |
| 2 | [Pub/Sub Bigtable Subscriptions](02-pubsub-bigtable-subscriptions/README.md) — Pub/Sub -> Bigtable with no code | Bigtable subscription (a type of export subscription) | **Preview** | ✅ Accurate |
| 3 | [BigQuery Continuous Query — Stateful](03-bigquery-continuous-queries-stateful/README.md) — Always-on SQL for JOINs, windowing, and gen AI | Stateful operations in continuous queries | **Preview** | ✅ Accurate |
| 4 | [Dataflow — In-stream Agents](04-dataflow-streaming-agents/README.md) — Embed ADK agents in Dataflow | Dataflow + `RunInference` + `ADKAgentModelHandler` + ADK | GA (RunInference); ADKAgentModelHandler ships with Beam | ⚠️ Feature exists; "In-stream Agents" is not a product name |

For terminology caveats ("In-stream Agents", "Elastic Inference Queue", "Gemini Enterprise Agent
Platform"), see [Summary of caveats in fact-check.md](fact-check.md#summary-of-caveats).
Bigtable materialized views in the article's diagram are a separate feature from Bigtable Subscriptions
(see [02](02-pubsub-bigtable-subscriptions/README.md)).

## Related announcements not in the article (from the official blog)

The same session and blog also announced features for agents to consume streaming infrastructure.

- **Model Context Protocol (MCP) support (GA)** — Agents can operate each service through fully
  managed MCP endpoints.
    - Pub/Sub: <https://docs.cloud.google.com/pubsub/docs/use-pubsub-mcp>
    - Bigtable: <https://docs.cloud.google.com/bigtable/docs/use-bigtable-mcp>
    - BigQuery: <https://docs.cloud.google.com/bigquery/docs/use-bigquery-mcp>
    - Managed Service for Apache Kafka:
      <https://docs.cloud.google.com/managed-service-for-apache-kafka/docs/use-managed-service-for-apache-kafka-mcp>
- **ADK integration (GA)** — ADK agents connect to real-time data in Pub/Sub, Bigtable, BigQuery,
  and more using pre-built integrations:
  <https://adk.dev/integrations/?topic=google>
- **Dataflow unified embeddings sinks** — See
  [Related feature in 04](04-dataflow-streaming-agents/README.md#related-feature-dataflow-unified-embeddings-sinks).

## Overall architecture

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

Legend:

- publishers: Publishers (event sources)
- AI Inference SMT: Transform attaching model inference inside Pub/Sub (GA)
- enriched msg: Message enriched with inference results
- Bigtable sub (Preview): Bigtable subscription (Preview)
- BigQuery sub: BigQuery subscription
- continuous query (CQ) stateful (PV): Stateful processing in continuous queries (Preview)
- reverse ETL: Writing analytical results back to low-latency serving systems
- RunInference + ADK agent: Node embedding an agent in Dataflow
- serving: Low-latency serving to applications

## Where to start

- E2E demo spanning three features (BigQuery stateful CQ + Pub/Sub SMT + ADK):
  [Official samples in 03](03-bigquery-continuous-queries-stateful/README.md#official-sample-implementations-and-codelabs)
- Minimal example of running an agent on Dataflow:
  [Verified minimal example in 04](04-dataflow-streaming-agents/README.md#verified-minimal-example)

> Verification date: Based on official documentation as of 2026-06-08. Preview features may change
> in specification, so check the latest official pages before implementation.
