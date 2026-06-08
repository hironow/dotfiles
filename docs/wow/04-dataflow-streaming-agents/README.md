# Dataflow Streaming Agents（記事の "In-stream Agents"）

記事が「Dataflow — In-stream Agents によるカスタム AI 実行」と書いた機能の **実体**。Dataflow
（= Apache Beam のマネージドランナー）パイプラインの中に、**ADK（Agent Development Kit）で
書いたエージェントを 1 ノードとして組み込み**、高スループットなストリームに対して数百の
エージェントセッションを並列実行する。

## ファクトチェック（最重要）

- **"In-stream Agents" は正式な製品名ではない。** 記事の意訳であり、公式 SKU / 機能名では
  ない。公式（Google Cloud Blog "Streaming AI news from Next '26"）の表現は
  **"event-driven autonomous agents in Dataflow"** / 「agentic logic を Dataflow パイプラインの
  first-class citizen として扱う」。
- **実装の実体は次の 3 つの組み合わせ**:
    1. Apache Beam の **`RunInference`** トランスフォーム（GA、Beam 2.40.0+）
    2. 新しいモデルハンドラ **`ADKAgentModelHandler`**（`apache_beam.ml.inference.agent_development_kit`）
    3. **ADK（Agent Development Kit）** で定義したエージェント
- 記事の「複数データソース統合（Spanner / AlloyDB / BigQuery / GCS / Kafka）」は **正確**。
  これは Beam の I/O コネクタと enrichment 変換で実現する従来からの強み。
- `ADKAgentModelHandler` クラスは **Apache Beam の current pydoc に実在を確認済み**:
  <https://beam.apache.org/releases/pydoc/current/apache_beam.ml.inference.agent_development_kit.html>

## なぜ Dataflow にエージェントを載せるのか

- **スケーラビリティ**: 高速イベントを上流（Dataflow）で前処理・集約し、数百のエージェント
  セッションを並列実行。エージェント側は重い I/O やバッチングを意識しなくてよい。
- **"action-ready" コンテキスト**: Dataflow が複雑なデータ充実化（enrichment / join / 整形）を
  済ませ、エージェントには「すぐ行動に移せる」入力だけ渡す。
- **統一エンジン**: Dataflow は batch / streaming / agentic AI を 1 つのサーバーレスエンジンで
  扱う、という位置づけになった。

## `ADKAgentModelHandler` の仕様（pydoc 実機確認）

`apache_beam.ml.inference.agent_development_kit.ADKAgentModelHandler`

コンストラクタ引数:

- `agent`: ADK の `Agent` インスタンス、または **ゼロ引数の callable**（シリアライズ不可能な
  状態を持つエージェントは lambda でラップして遅延生成する）
- `app_name`: ADK アプリ名（デフォルト `'beam_inference'`）
- `session_service_factory`: `BaseSessionService` を返す callable（任意）
- `min_batch_size` / `max_batch_size` / `max_batch_duration_secs` / `max_batch_weight`:
  バッチ制御（任意）
- `element_size_fn`: 要素サイズを返す関数（任意）

主なメソッド:

- `load_model()`: ワーカー上で ADK `Runner` を初期化
- `run_inference()`: バッチの各要素に対しエージェントを実行
- `get_metrics_namespace()`: メトリクス名前空間

基底 / 戻り値: `ModelHandler` / `PredictionResult`。

## 実装：検証済み最小例（Apache Beam ソース由来）

以下は Apache Beam ソースの docstring に載っている **検証済みの最小例**（2026-06 時点、
`sdks/python/apache_beam/ml/inference/agent_development_kit.py`）。`LlmAgent` をそのまま
`ADKAgentModelHandler` に渡し、`RunInference` で実行する。

```python
import apache_beam as beam
from apache_beam.ml.inference.base import RunInference
from apache_beam.ml.inference.agent_development_kit import ADKAgentModelHandler
from google.adk.agents import LlmAgent

agent = LlmAgent(
    name="my_agent",
    model="gemini-2.0-flash",
    instruction="You are a helpful assistant.",
)

with beam.Pipeline() as p:
    results = (
        p
        | beam.Create(["What is the capital of France?"])
        | RunInference(ADKAgentModelHandler(agent=agent))
    )
```

- **stateful なマルチターン会話**: `RunInference(..., inference_args={"session_id": ...})` で
  `session_id` を渡すと、同じ `session_id` の要素が会話履歴を共有する（test
  `test_shared_session_id_from_inference_args` で実証）。
- エージェントがシリアライズ不可能な状態を持つ場合は、`agent` に **ゼロ引数 callable**
  （lambda）を渡してワーカー上で遅延生成する。

### ストリーミングへの応用（Pub/Sub 入力）

上記の `beam.Create(...)` を Pub/Sub 読み取りに差し替え、前段で enrichment するのが
ストリーミング構成。Dataflow ランナーで実行する。

```python
with beam.Pipeline(options=pipeline_options) as p:
    (
        p
        | "Read"  >> beam.io.ReadFromPubSub(subscription="projects/.../subscriptions/...")
        | "Prep"  >> beam.Map(to_action_ready_context)   # Dataflow 側で enrichment
        | "Agent" >> RunInference(ADKAgentModelHandler(agent=agent))
        | "Sink"  >> beam.Map(dispatch_action)           # 結果を下流へ
    )
```

## パイプライン像

```text
 Pub/Sub / Kafka --> Dataflow --> [ enrichment ] --> RunInference(ADKAgentModelHandler) --> action
   (events)          (Beam)        Spanner/AlloyDB/      ADK agent (gemini)                 Pub/Sub
                                   BigQuery/GCS lookup                                      / DB update
```

Legend / 凡例:

- events: 着信イベント（Pub/Sub / Kafka）
- enrichment: 文脈付与（外部データソース参照による充実化）
- RunInference(ADKAgentModelHandler): エージェント実行ノード
- ADK agent: ADK 定義のエージェント（Gemini 等）
- action: エージェントの決定（下流アクション・DB 更新・通知など）

## 関連機能: Dataflow Unified Embeddings Sinks

記事本文では薄いが、同じ Next '26 発表の一部。ストリーム内で埋め込みを生成し、**Cloud
Spanner（新ベクトル検索）/ AlloyDB** に materialize する sink。エージェント RAG の long-term
memory を最新化し続ける用途。

- `MLTransform`（Beam 2.53.0+）で Vertex AI / Hugging Face の埋め込みを生成、または `Gemma` 等を
  ローカル推論。
- 参考: [Deploying EmbeddingGemma at scale with Dataflow](https://developers.googleblog.com/en/deploying-embeddinggemma-at-scale-with-dataflow/)

## Dataflow ML の基礎（前提知識）

- `RunInference`（Beam 2.40.0+）: モデル設定を `ModelHandler` に渡すだけで推論を組み込める。
  PyTorch / scikit-learn / TensorFlow / ONNX / TensorRT / Vertex AI endpoint / **ADK** 等の
  ハンドラがある。複数モデルの keyed handler、自動モデルリフレッシュ（side input）にも対応。
- `MLTransform`（Beam 2.53.0+）: 前処理を 1 クラスに集約。
- GPU/TPU 対応（H100 / TPU v5e・v5p・v6e、GPU autoscaling、right fitting）。
- batch / streaming 両対応。

## 開発リポジトリ / SDK / サンプル実装（2026-06 実在確認済み）

### Apache Beam（`ADKAgentModelHandler` 本体）

- リポジトリ: <https://github.com/apache/beam>（製品サイト <https://beam.apache.org/>）
- **ソース実体**（GitHub API で 200 確認）:
    - 本体: [`sdks/python/apache_beam/ml/inference/agent_development_kit.py`](https://github.com/apache/beam/blob/master/sdks/python/apache_beam/ml/inference/agent_development_kit.py)
    - テスト（使い方の実例。`test_string_input_returns_prediction_result` /
      `test_batch_of_strings` / `test_shared_session_id_from_inference_args`）:
      [`sdks/python/apache_beam/ml/inference/agent_development_kit_test.py`](https://github.com/apache/beam/blob/master/sdks/python/apache_beam/ml/inference/agent_development_kit_test.py)
- `RunInference` 全般のサンプル集:
  [`sdks/python/apache_beam/examples/inference`](https://github.com/apache/beam/tree/master/sdks/python/apache_beam/examples/inference)
- pydoc: <https://beam.apache.org/releases/pydoc/current/apache_beam.ml.inference.agent_development_kit.html>
- Beam ML / LLM ガイド: <https://beam.apache.org/documentation/ml/large-language-modeling/>

### ADK（Agent Development Kit）

- ドキュメント: <https://google.github.io/adk-docs/>
- Python: <https://github.com/google/adk-python> / Go: <https://github.com/google/adk-go>
- サンプル集: <https://github.com/google/adk-samples>
- Google サービス統合一覧: <https://adk.dev/integrations/?topic=google>

### Dataflow ML（RunInference / remote inference）

- Dataflow ML ドキュメント: <https://docs.cloud.google.com/dataflow/docs/machine-learning>
- サンプル一覧（Colab 手順あり）:
  <https://docs.cloud.google.com/dataflow/docs/machine-learning/ml-about>
- remote inference notebook（Vertex AI / 外部エンドポイント呼び出し）:
  <https://docs.cloud.google.com/dataflow/docs/notebooks/custom_remote_inference>
- codelab（Beam + Dataflow でリアルタイム AI/ML 評価）:
  <https://codelabs.developers.google.com/beam-ai-evaluation-pipeline>

### エンドツーエンド・デモ（CQ + Pub/Sub SMT + ADK の 3 機能横断）

- 公式 codelab（Next '26）:
  <https://codelabs.developers.google.com/next26/bigquery-adk-event-driven-agents>
- GitHub: [`GoogleCloudPlatform/devrel-demos` → `data-analytics/event_driven_agents_demo`](https://github.com/GoogleCloudPlatform/devrel-demos/tree/main/data-analytics/event_driven_agents_demo)
  （`agent/` `setup/` `simulator/` 構成。実在確認済み）。詳細は
  [03-bigquery-continuous-queries-stateful/](../03-bigquery-continuous-queries-stateful/README.md) を参照。

## 制約・注意

- `ADKAgentModelHandler` は新しい API。Preview 相当として扱い、引数・挙動は最新版で確認する。
- エージェントがシリアライズ不可能な状態を持つ場合は **callable（lambda）でラップ** して
  ワーカー上で遅延生成する（pydoc の指示）。
- 1 イベント = 1 エージェント実行が基本。スループットは `max_batch_size` 等とワーカー数で調整。
- LLM 呼び出しは外部 quota / レイテンシに律速される。Dataflow の autoscaling と合わせて設計する。

## 関連リンク

- 公式ブログ（Next '26 総括、Dataflow agentic の一次情報）:
  <https://cloud.google.com/blog/products/data-analytics/streaming-ai-news-from-next26>
- Apache Beam RunInference: <https://beam.apache.org/documentation/ml/about-ml/>
- Dataflow（製品トップ）: <https://cloud.google.com/products/dataflow>
