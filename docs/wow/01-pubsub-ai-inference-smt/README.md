# Pub/Sub AI Inference SMT（GA）

Pub/Sub のメッセージが流れる途中で、**外部サービスを挟まずに直接モデル推論を呼び、結果を
メッセージに付与する** 機能。SMT = Single Message Transform（単一メッセージ変換）。

- Launch stage: **GA（一般提供）**
- 公式: <https://docs.cloud.google.com/pubsub/docs/smts/ai-inference-smt>
- SMT 全体像: <https://docs.cloud.google.com/pubsub/docs/smts/smts-overview>

## ファクトチェック

- 記事の「Pub/Sub ストリーミング内での直接モデル呼び出し」「Gemini Enterprise Agent
  Platform 対応」「NLP / 不正検知 / セマンティック検索」は **公式の use case と一致**（公式は
  real-time enrichment / simplified AI pipelines / reduced latency / enhanced flow control を挙げる）。
- 記事の **GA 表記は正しい**（公式ブログ "Streaming AI news from Next '26" で GA と明記）。
- 「Gemini Enterprise Agent Platform」は **Vertex AI のリブランド**。IAM ロール・API は
  旧称（`Vertex AI ...` / `aiplatform.*`）のままなので注意。

## SMT は 2 種類ある

| 種類 | 用途 | 公式 |
|---|---|---|
| **AI Inference** | Agent Platform のモデルに推論させ、結果をメッセージへ付与 | [ai-inference-smt](https://docs.cloud.google.com/pubsub/docs/smts/ai-inference-smt) |
| **JavaScript UDF** | 任意の JS 関数で変換 / フィルタ（`null` を返すと drop） | [udfs-overview](https://docs.cloud.google.com/pubsub/docs/smts/udfs-overview) |

両者は **チェーン可能**。典型は「UDF でモデル入力形式に整形 → AI Inference → UDF で後処理」。

## Topic SMT と Subscription SMT

- **Topic SMT**: Pub/Sub が保存する **前** に実行。結果は **全 subscriber で共有**。
- **Subscription SMT**: 配信 **直前** に実行。結果は **その subscription のみ**。

```text
Topic SMT  (runs once before storage; result shared by ALL subscribers)

  publisher --> [ Topic + SMT ] --> stored --> sub A --> subscriber A
                                       |
                                       +-------> sub B --> subscriber B

Subscription SMT  (runs per subscription, just before delivery)

  publisher --> [ Topic ] --> sub A + SMT  --> subscriber A
                    |
                    +--------> sub B (no SMT) --> subscriber B
```

Legend / 凡例:

- Topic SMT: トピック側変換（保存前に 1 回、全 subscriber が共有）
- Subscription SMT: サブスクリプション側変換（配信直前、その sub だけに適用）
- stored: Pub/Sub 内部ストレージへ保存
- sub: subscription（購読）
- subscriber: 購読アプリ

## 実装：最小手順（gcloud）

### 1. 変換定義ファイル（YAML）

```yaml
# ai-smt.yaml
- aiInference:
    endpoint: projects/PROJECT_ID/locations/LOCATION/publishers/google/models/gemini-2.5-flash
    unstructuredInference: {
        parameters: {
            "max_tokens": 25000
        }
    }
```

- `endpoint` の形式:
    - Model Garden（MaaS）モデル:
      `projects/PROJECT/locations/LOCATION/publishers/PUBLISHER/models/MODEL_NAME`
    - 自前デプロイモデル: `projects/PROJECT/locations/LOCATION/endpoints/ENDPOINT`
- `unstructuredInference.parameters` は各メッセージにマージされるモデルパラメータ（任意）。
- `service_account_email` も指定可（任意。未指定なら Pub/Sub service agent を使用）。

### 2. topic / subscription を作成して試す

```bash
# topic を作成
gcloud pubsub topics create TOPIC_ID

# AI Inference SMT 付き subscription を作成（推論は最長 60s なので ack-deadline を伸ばす）
gcloud pubsub subscriptions create TOPIC_ID-sub \
  --ack-deadline=600 \
  --topic TOPIC_ID \
  --message-transforms-file ai-smt.yaml

# Chat Completions API 形式のプロンプトを publish
gcloud pubsub topics publish TOPIC_ID --message=$'{
  "model":"google/gemini-2.5-flash","messages":[{
    "role": "user",
    "content": "Explain how AI works in a few words"
    }]
  }'

# 推論結果が付与されたメッセージを pull
gcloud pubsub subscriptions pull TOPIC_ID-sub
```

Topic に付ける場合は `gcloud pubsub topics create TOPIC_ID --message-transforms-file ai-smt.yaml`。

## 入出力フォーマット

- **入力**: メッセージ data は **モデルへ送る JSON 文字列**。SMT が `parameters` をマージして
  送信。Pub/Sub は入力を検証しないので、形式の正しさは利用者責任。
- **出力**: 成功すると元メッセージを次の形にラップする。

```json
{
  "original_message": { ORIGINAL_MESSAGE },
  "model_output": { INFERENCE_RESULT }
}
```

## 呼び出される API（モデル種別ごと）

| モデル | 呼ばれる API |
|---|---|
| 自前デプロイ（全種） | `rawPredict` |
| Gemini foundational（例 `gemini-3.0-pro`） | Chat Completions API |
| その他 Gemini（例 embeddings） | `rawPredict` |
| Anthropic / Mistral / AI21 | `rawPredict` |
| その他 MaaS | Chat Completions API |

互換 MaaS モデルは Gemini 2.0/2.5/3 系、Claude（Sonnet/Opus/Haiku 4 系）、Llama 3.3/4、
Mistral、DeepSeek、Qwen3、GPT-OSS、各種 embedding 等。一部（一部 embedding-2 / Veo / Lyria /
最新 thinking 系など）は **非対応**。最新の対応・非対応表は公式ページを参照。

## IAM

- 操作者: `roles/pubsub.editor`（topic/subscription 作成権限）。
- 推論呼び出し用 service account に Agent Platform エンドポイントへの権限:
    - 権限: `aiplatform.endpoints.get` / `aiplatform.endpoints.predict`
    - 付与ロール: Pub/Sub service agent を使うなら **Vertex AI Service Agent**、独自 SA なら
      **Vertex AI User**。

## フロー制御（記事の「不正検知」等で効く）

エンドポイント過負荷を避けるため、Pub/Sub がレイテンシ・quota に応じて **リクエストレートを
自動調整** する（unary pull API 利用時は非対応）。バックプレッシャーを自前で組まなくてよい。

> **用語注意（ファクトチェック）**: 元記事の「Elastic Inference Queue」は **公式ドキュメントに
> 該当用語がない**。製品 / 機能名ではなく、ここで説明した **フロー制御（レート自動調整）** を
> セッションスライドで言い換えた表現とみられる。実装上「Elastic Inference Queue」という設定や
> API は存在しないため、固有名として探さないこと。

## 制約・落とし穴

- 1 つの topic / subscription につき **AI Inference SMT は 1 個** まで。
- **private endpoint 非対応**（自前モデルは public な Agent Platform endpoint に置く）。
- **global endpoint** は Gemini foundation model のみ。他は regional endpoint 必須。
- **クライアント側バッチングなし**（1 メッセージ = 1 推論リクエスト）。非同期バッチ推論も不可。
- 推論は **60 秒以内**。超えると配信タイムアウト → リトライ、最終的に dead-letter topic 行き。
  **subscription SMT を使うときは dead-letter topic の設定を推奨**。
- 最終メッセージサイズ（元 + 推論出力）は Pub/Sub のメッセージサイズ上限内に収める必要あり。
- **リージョン制約**: topic SMT はエンドポイントのリージョンが topic の message storage policy
  内であること。export subscription（BigQuery / Cloud Storage）に付ける場合は宛先リソースの
  リージョンと一致が必要。pull は locational endpoint 推奨。

## エラーハンドリング

- **Topic SMT のエラー**: publish 全体が失敗し、publisher にエラーが返る（バッチ内 1 件でも
  失敗すると **バッチ全体が失敗**）。
- **Subscription SMT のエラー**: dead-letter topic に転送可能。
- 監視: `topic/message_transform_latencies`（status / filtered ラベル）、`topic/byte_cost`
  （`operation_type` / `response_code`）。

## 公式サンプル実装（2026-06 確認）

- Python サンプル群（`pubsub_v1` クライアント。SMT は `MessageTransform` /
  `JavaScriptUDF` 型を使う）:
  [`GoogleCloudPlatform/python-docs-samples` → `pubsub/cloud-client`](https://github.com/GoogleCloudPlatform/python-docs-samples/tree/main/pubsub/cloud-client)
- SMT 検証・テスト手順（topic / subscription 作成前に validate）:
  [create-topic-smt](https://docs.cloud.google.com/pubsub/docs/smts/create-topic-smt) /
  [create-subscription-smt](https://docs.cloud.google.com/pubsub/docs/smts/create-subscription-smt)
- E2E デモで AI Inference SMT ではなく **UDF SMT** を payload 整形に使う実例:
  [`devrel-demos` → `data-analytics/event_driven_agents_demo` の `setup/`](https://github.com/GoogleCloudPlatform/devrel-demos/tree/main/data-analytics/event_driven_agents_demo)
  （詳細は [03-bigquery-continuous-queries-stateful/](../03-bigquery-continuous-queries-stateful/README.md)）

## 関連リンク

- AI Inference SMT: <https://docs.cloud.google.com/pubsub/docs/smts/ai-inference-smt>
  （本ドキュメントは 2026-06 時点の公式版に基づく）
- SMT 概要 / 発表ブログ:
  <https://docs.cloud.google.com/pubsub/docs/smts/smts-overview> /
  <https://cloud.google.com/blog/products/data-analytics/pub-sub-single-message-transforms>
- topic に SMT を付ける: <https://docs.cloud.google.com/pubsub/docs/smts/create-topic-smt>
- subscription に SMT を付ける:
  <https://docs.cloud.google.com/pubsub/docs/smts/create-subscription-smt>
- topic / subscription どちらに付けるか:
  <https://docs.cloud.google.com/pubsub/docs/smts/choose-smts>
- Pub/Sub リリースノート: <https://docs.cloud.google.com/pubsub/docs/release-notes>
- 解説記事（Medium / Google Cloud Community）:
  <https://medium.com/google-cloud/deep-dive-into-google-cloud-pub-sub-single-message-transforms-and-ai-inference-baa920d8103a>
