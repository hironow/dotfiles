# Dataflow Streaming Agents ("In-stream Agents" in the article)

Embed **an agent written with ADK (Agent Development Kit) as a single node** in a Dataflow
(managed Apache Beam runner) pipeline to run hundreds of agent sessions in parallel over
high-throughput streams. This is the actual mechanism behind what the article calls
"Dataflow — custom AI execution via In-stream Agents" (translated).

## Fact-check (most important)

- **"In-stream Agents" is not an official product name.** It is the article's loose translation, not
  an official SKU or feature name. The official phrasing (Google Cloud Blog, "Streaming AI news
  from Next '26") is **"event-driven autonomous agents in Dataflow"** / "treat agentic logic as a
  first-class citizen of Dataflow pipelines" (translated).
- **The actual implementation combines these three components**:
    1. Apache Beam's **`RunInference`** transform (GA, Beam 2.40.0+)
    2. The new **`ADKAgentModelHandler`** model handler (`apache_beam.ml.inference.agent_development_kit`)
    3. An agent defined with **ADK (Agent Development Kit)**
- The article's claim of "multi-data-source integration (Spanner / AlloyDB / BigQuery / GCS / Kafka)" (translated)
  is **accurate**. This builds on Beam's existing strength in I/O connectors and enrichment transforms.
- The `ADKAgentModelHandler` class exists in the current Apache Beam
  [pydoc](https://beam.apache.org/releases/pydoc/current/apache_beam.ml.inference.agent_development_kit.html).

## Why run agents on Dataflow

- **Scalability**: Preprocess and aggregate high-velocity events upstream in Dataflow, and run
  hundreds of agent sessions in parallel. The agent does not need to handle heavy I/O or batching.
- **"Action-ready" context**: Dataflow handles enrichment, joins, and formatting upstream,
  passing only action-ready inputs to the agent.
- **Unified engine**: Dataflow is positioned as a single serverless engine for batch, streaming,
  and agentic AI.

## `ADKAgentModelHandler` specification (verified against pydoc)

`apache_beam.ml.inference.agent_development_kit.ADKAgentModelHandler`

Constructor arguments:

- `agent`: An ADK `Agent` instance, or a **zero-argument callable** (wrap agents with
  non-serializable state in a lambda for lazy creation)
- `app_name`: ADK app name (default `'beam_inference'`)
- `session_service_factory`: Callable returning a `BaseSessionService` (optional)
- `min_batch_size` / `max_batch_size` / `max_batch_duration_secs` / `max_batch_weight`:
  Batch controls (optional)
- `element_size_fn`: Function returning element size (optional)

Main methods:

- `load_model()`: Initializes the ADK `Runner` on the worker
- `run_inference()`: Runs the agent on each element in the batch
- `get_metrics_namespace()`: Metrics namespace

Base class / return type: `ModelHandler` / `PredictionResult`.

## Verified minimal example

Minimal example from the docstring in Apache Beam source
(`sdks/python/apache_beam/ml/inference/agent_development_kit.py`, as of 2026-06). Pass an `LlmAgent`
directly to `ADKAgentModelHandler` and run it with `RunInference`.

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

- **Stateful multi-turn conversations**: Passing `session_id` via
  `RunInference(..., inference_args={"session_id": ...})` shares conversation history across
  elements with the same `session_id` (demonstrated by test
  `test_shared_session_id_from_inference_args`).

### Streaming application (Pub/Sub input)

To build a streaming setup, replace `beam.Create(...)` above with a Pub/Sub read and add upstream
enrichment. Run it on the Dataflow runner.

```python
with beam.Pipeline(options=pipeline_options) as p:
    (
        p
        | "Read"
        >> beam.io.ReadFromPubSub(subscription="projects/.../subscriptions/...")
        | "Prep" >> beam.Map(to_action_ready_context)  # Enrichment on the Dataflow side
        | "Agent" >> RunInference(ADKAgentModelHandler(agent=agent))
        | "Sink" >> beam.Map(dispatch_action)  # Send results downstream
    )
```

## Pipeline overview

```text
 Pub/Sub / Kafka --> Dataflow --> [ enrichment ] --> RunInference(ADKAgentModelHandler) --> action
   (events)          (Beam)        Spanner/AlloyDB/      ADK agent (gemini)                 Pub/Sub
                                   BigQuery/GCS lookup                                      / DB update
```

Legend:

- events: Incoming events (Pub/Sub / Kafka)
- enrichment: Context enrichment by looking up external data sources
- RunInference(ADKAgentModelHandler): Agent execution node
- ADK agent: Agent defined in ADK (such as Gemini)
- action: Agent decision (downstream action, DB update, notification, etc.)

## Related feature: Dataflow Unified Embeddings Sinks

Mentioned only briefly in the article, but part of the same Next '26 announcement. This sink
generates embeddings in-stream and materializes them to **Cloud Spanner (new vector search) or
AlloyDB**. Use it to keep an agent RAG's long-term memory up to date.

- Generate Vertex AI or Hugging Face embeddings with `MLTransform` (Beam 2.53.0+), or run local
  inference on models like `Gemma`.
- Reference: [Deploying EmbeddingGemma at scale with Dataflow](https://developers.googleblog.com/en/deploying-embeddinggemma-at-scale-with-dataflow/)

## Dataflow ML basics (prerequisites)

- `RunInference` (GA, Beam 2.40.0+): Embed inference simply by passing model configuration to a
  `ModelHandler`. Handlers exist for PyTorch, scikit-learn, TensorFlow, ONNX, TensorRT, Vertex AI
  endpoints, **ADK**, and more. Also supports multi-model keyed handlers and automatic model
  refresh (side input).
- `MLTransform` (Beam 2.53.0+): Consolidates preprocessing into one class.
- GPU/TPU support (H100; TPU v5e, v5p, and v6e; GPU autoscaling; right fitting).
- Supports both batch and streaming.

## Repositories, SDKs, and sample implementations

Verified to exist in 2026-06.

### Apache Beam (`ADKAgentModelHandler` core)

- Repository: <https://github.com/apache/beam> (product site <https://beam.apache.org/>)
- **Source files**:
    - Implementation: [`sdks/python/apache_beam/ml/inference/agent_development_kit.py`](https://github.com/apache/beam/blob/master/sdks/python/apache_beam/ml/inference/agent_development_kit.py)
    - Tests (usage examples: `test_string_input_returns_prediction_result`,
      `test_batch_of_strings`, `test_shared_session_id_from_inference_args`):
      [`sdks/python/apache_beam/ml/inference/agent_development_kit_test.py`](https://github.com/apache/beam/blob/master/sdks/python/apache_beam/ml/inference/agent_development_kit_test.py)
- General `RunInference` examples:
  [`sdks/python/apache_beam/examples/inference`](https://github.com/apache/beam/tree/master/sdks/python/apache_beam/examples/inference)
- pydoc: <https://beam.apache.org/releases/pydoc/current/apache_beam.ml.inference.agent_development_kit.html>
- Beam ML / LLM guide: <https://beam.apache.org/documentation/ml/large-language-modeling/>

### ADK (Agent Development Kit)

- Docs: <https://google.github.io/adk-docs/>
- Python: <https://github.com/google/adk-python> / Go: <https://github.com/google/adk-go>
- Samples: <https://github.com/google/adk-samples>
- Google service integrations: <https://adk.dev/integrations/?topic=google>

### Dataflow ML (RunInference / remote inference)

- Dataflow ML docs: <https://docs.cloud.google.com/dataflow/docs/machine-learning>
- Samples (includes Colab steps):
  <https://docs.cloud.google.com/dataflow/docs/machine-learning/ml-about>
- Remote inference notebook (calling Vertex AI / external endpoints):
  <https://docs.cloud.google.com/dataflow/docs/notebooks/custom_remote_inference>
- Codelab (real-time AI/ML evaluation with Beam + Dataflow):
  <https://codelabs.developers.google.com/beam-ai-evaluation-pipeline>

### End-to-end demo (across CQ, Pub/Sub SMT, and ADK)

The codelab and GitHub repository are listed under
[Official samples in 03](../03-bigquery-continuous-queries-stateful/README.md#official-sample-implementations-and-codelabs).

## Constraints and caveats

- `ADKAgentModelHandler` is a new API. Treat it as Preview-equivalent and check the latest version
  for arguments and behavior.
- The baseline is one agent execution per event. Tune throughput with `max_batch_size` (and similar
  options) plus worker count.
- External quotas and latency bottleneck LLM calls. Design this alongside Dataflow autoscaling.

## Related links

- Official blog (Next '26 summary, primary source for Dataflow agentic features):
  <https://cloud.google.com/blog/products/data-analytics/streaming-ai-news-from-next26>
- Apache Beam RunInference: <https://beam.apache.org/documentation/ml/about-ml/>
- Dataflow (product home): <https://cloud.google.com/products/dataflow>
