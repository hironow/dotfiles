# ファクトチェック詳細（記載ごとの判定）

[iret.media/194869](https://iret.media/194869) が述べている **個々の記載** を、一次情報
（cloud.google.com 公式ドキュメント・Google Cloud Blog・Apache Beam pydoc）と一文ずつ
突き合わせた結果。総括は [README.md](README.md) を、各機能の実装詳細は各機能ドキュメントを参照。

> 検証日: 2026-06-08 時点の公式ドキュメントに基づく。

## 判定記号

- ✅ **正確** — 公式と一致
- ⚠️ **要注意** — 不正確、または誤解を招く（製品名でないものを製品名扱い等）
- ℹ️ **補足必要** — 誤りではないが、文脈・但し書きの追加が要る
- ❓ **検証対象外** — 記事メタ情報など、一次情報で裏取りできない / する意味が薄い

## 結論

記事の事実精度は **高い**。4 機能の正式名称・launch stage（GA / GA / Preview / Preview）は
すべて公式と一致し、ユースケースも概ね正確。**要注意は用語まわりの 3 点のみ**（下記 ⚠️ / ℹ️）。

## 著者・セッション情報

| 記載 | 判定 | 一次情報との照合 |
|---|---|---|
| セッション名「What's New in Streaming」 | ℹ️ | 公式の正式名は **"What's new in streaming: Real-time data for agentic AI"**。記事は短縮形。実体は同一 |
| 田村直樹 / Partner Top Engineer 2025 & 2026 / 2026-04-24 公開 | ❓ | 記事メタ情報ゆえ検証対象外。Partner Top Engineer は実在の Google Cloud プログラム |

## 全体アーキテクチャ

| 記載 | 判定 | 照合 |
|---|---|---|
| Raw Events → Pub/Sub → AI Inference SMT →（BigQuery CQ / Bigtable）→ MCP 経由でエージェント | ✅ | 公式ブログの構図と一致。**MCP support は GA**（Pub/Sub / Bigtable / BigQuery / Kafka）確認済 |
| 「Bigtable のマテリアライズドビュー」 | ℹ️ | [Bigtable continuous materialized views](https://docs.cloud.google.com/bigtable/docs/continuous-materialized-views) は実在機能。ただし **目玉の Bigtable Subscriptions とは別の Bigtable 機能**（subscriptions は raw メッセージ書き込み、materialized view は SQL 定義の背景集約ビュー） |
| エージェント 3 条件（リアルタイムシグナル / セマンティックメモリ / 低レイテンシ） | ✅ | セッションの editorial framing。ブログの論旨と整合 |

## ① Pub/Sub AI Inference SMT

| 記載 | 判定 | 照合 |
|---|---|---|
| 正式名称 Single Message Transforms（SMT） | ✅ | 公式と一致（厳密には単数 "Transform" が正準） |
| Launch stage: **GA** | ✅ | 公式ブログ "Streaming AI news from Next '26" で GA 明記 |
| ストリーミングパス内で直接モデル呼び出し / 間にサービス不要 | ✅ | 公式の "reduced latency" / "simplified AI pipelines" と一致 |
| 対応: Agent Platform 上のモデル / Model Garden / カスタム | ✅ | self-deployed + MaaS で一致 |
| 「Gemini Enterprise Agent Platform（このイベントで GA）」 | ℹ️ | **= Vertex AI のリブランド**。IAM ロール（`Vertex AI User`）と API（`aiplatform.endpoints.predict`）は **旧称のまま残る** 点に注意 |
| フロー制御を Pub/Sub 側で統合管理、過負荷を心配せず済む | ✅ | 公式 "enhanced flow control"（レート自動調整）と一致 |
| ユースケース: NLP（embedding / 分類）、予測（不正検知 / センチメント） | ✅ | 公式 use case（enrichment / classification / sentiment / embedding）と一致 |
| 「Elastic Inference Queue」 | ⚠️ | **公式ドキュメントに該当用語なし**。AI Inference SMT のフロー制御機能をスライドで言い換えたものとみられる。製品 / 機能名として扱うと誤り |

## ② Pub/Sub Bigtable Subscriptions

| 記載 | 判定 | 照合 |
|---|---|---|
| 正式名称 / Launch stage: **Preview** | ✅ | 公式に Pre-GA バナー。`gcloud beta` 系コマンド |
| Bigtable へ直接書き込む新しいサブスクリプションタイプ | ✅ | export subscription の一種で一致 |
| 「カスタム ETL も Dataflow も不要」 | ✅ | 一致（複雑変換時は Dataflow 推奨、という但し書きは公式にあり） |
| スケーリング / エラー / フロー制御を Pub/Sub が全管理 | ✅ | 一致。ただし **配信は at-least-once**（重複排除なし）という前提が記事では省略 |
| 「BigQuery・Cloud Storage に続く 3 つ目のネイティブ書き込み先」 | ✅ | export subscription の系譜として正確 |
| サブミリ秒サービング向け | ✅ | Bigtable の読み取りサービング特性として妥当 |

## ③ BigQuery Continuous Query / Stateful Data Processing

| 記載 | 判定 | 照合 |
|---|---|---|
| 「BigQuery は実はストリーミング処理エンジンでもある」 | ✅ | continuous queries で正確 |
| CQ の 4 ユースケース分類（分析 / 生成 AI / reverse ETL / Agentic） | ✅ | 公式 use case と整合（セッションの分類軸） |
| 正式名称 Stateful Data Processing / Launch stage: **Preview** | ✅ | 公式 stateful operations は Preview（フィードバック窓口 `bq-continuous-queries-feedback@google.com`） |
| 従来はステートレス（1 件ずつ独立処理）だった | ✅ | 公式の説明と一致 |
| 集約（SUM / AVG / APPROX_COUNT_DISTINCT）/ タンブリングウィンドウ / ストリーム間 INNER JOIN | ✅ | `TUMBLE`・JOIN・集約すべて公式で確認 |
| Updates / Deletes 処理（CHANGES TVF 経由で Pub/Sub シンクへ） | ✅ | 正確。ただし **CHANGES は stateful 操作とは併用不可・Pub/Sub export 時のみ** という制約あり |
| 「Flink / Spark Structured Streaming の領域に SQL だけで入れる」 | ✅ | editorial だが JOIN + windowing 追加で妥当な評価 |

## ④ Dataflow

| 記載 | 判定 | 照合 |
|---|---|---|
| SMT / CQ で処理しきれない複雑ケースに対応 / プログラマティック制御 | ✅ | 公式ポジショニングと一致 |
| 統合データソース: Spanner / AlloyDB / BigQuery / GCS / Pub/Sub / Kafka | ✅ | Beam I/O コネクタで正確 |
| 「In-stream Agents というエージェントがカスタム AI モデルをパイプライン内で直接実行」 | ⚠️ | **「In-stream Agents」は正式な製品 / 機能名ではない**。実体は Apache Beam の `RunInference` + 新ハンドラ `ADKAgentModelHandler` + ADK。公式表現は "event-driven autonomous agents in Dataflow"。「エージェントがモデルを実行」も主客が逆気味で、正しくは「パイプラインが ADK エージェントをノードとして実行」 |
| 使い分け（1 msg 推論 → SMT / SQL 集約・結合 → CQ / 複数ソース・カスタム → Dataflow） | ✅ | 公式の選択指針と一致 |

## 要注意点まとめ

1. ⚠️ **「In-stream Agents」** — 正式名称ではない。実体は ADK エージェントを
   `RunInference` + `ADKAgentModelHandler` で実行する構成（詳細:
   [04-dataflow-streaming-agents/](04-dataflow-streaming-agents/README.md)）。
2. ⚠️ **「Elastic Inference Queue」** — 公式用語ではない。AI Inference SMT のフロー制御機能の
   言い換え（詳細: [01-pubsub-ai-inference-smt/](01-pubsub-ai-inference-smt/README.md)）。
3. ℹ️ **「Gemini Enterprise Agent Platform」** — Vertex AI のリブランド。IAM / API は旧称が残存。

軽微な省略（誤りではない）:

- Bigtable Subscriptions の at-least-once（重複排除なし）配信。
- CHANGES TVF と stateful 操作の併用不可制約。

## ドキュメント記載の自己検証（2026-06-08）

記事だけでなく、本 docs に **後から追加した実装コード・ファイルパス・サンプル・図** も
primary source に当て直した結果。

| 検証対象 | 方法 | 結果 |
|---|---|---|
| `ADKAgentModelHandler` 最小例（[04](04-dataflow-streaming-agents/README.md)）| beam ソース `agent_development_kit.py` の docstring と逐語照合 | ✅ import / `gemini-2.0-flash` / `beam.Create([...])` / `RunInference(...)` 完全一致 |
| `ADKAgentModelHandler.__init__` 署名（`max_batch_weight` 含む）| 同ソース `def __init__` 照合 | ✅ 一致（`max_batch_weight` も実在） |
| beam の `.py` / `_test.py` パス | GitHub API HTTP ステータス | ✅ 両方 200 |
| `devrel-demos` の SMT 配置（`setup/transform.yaml`）| GitHub API で実ファイル確認 | ✅ `setup/` が正（repo 自身の README 散文は `agent/` と誤記） |
| デモ agent のモデル / ツール | `agent/adk_agent_app/agent.py` 照合 | ✅ `gemini-2.5-flash` 既定 + `BigQueryToolset` + `google_search` |
| Bigtable 書き込みレイアウト図（[02](02-pubsub-bigtable-subscriptions/README.md)）| 公式 docs で行構造を確認 | ✅ metadata は **同一行**（同一 row key）に `pubsub_metadata` family |
| ASCII 図 5 枚 | text-fence 内を byte 単位スキャン | ✅ 多バイト文字ゼロ（規約準拠）+ 各図に日本語 legend |

修正した記載:

- ⚠️→修正: [01](01-pubsub-ai-inference-smt/README.md) の「docs 最終更新 2026-05-14」は二次
  ソースの paraphrase で primary 未確認 → 「2026-06 時点の公式版に基づく」に軟化。

## 判定の根拠（一次情報）

- AI Inference SMT: <https://docs.cloud.google.com/pubsub/docs/smts/ai-inference-smt>
- SMT 概要: <https://docs.cloud.google.com/pubsub/docs/smts/smts-overview>
- Bigtable subscriptions: <https://docs.cloud.google.com/pubsub/docs/bigtable-subscriptions>
- Bigtable continuous materialized views:
  <https://docs.cloud.google.com/bigtable/docs/continuous-materialized-views>
- BigQuery continuous queries: <https://docs.cloud.google.com/bigquery/docs/continuous-queries-introduction>
- `ADKAgentModelHandler` pydoc:
  <https://beam.apache.org/releases/pydoc/current/apache_beam.ml.inference.agent_development_kit.html>
- 公式ブログ（Next '26 総括）:
  <https://cloud.google.com/blog/products/data-analytics/streaming-ai-news-from-next26>
