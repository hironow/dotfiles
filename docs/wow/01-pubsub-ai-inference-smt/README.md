# Pub/Sub AI Inference SMT (GA)

Pub/Sub calls model inference **directly on each flowing message without an external intermediate
service** and attaches the result to the message. SMT stands for Single Message Transform.

- Launch stage: **GA (General Availability)**
- Official docs: <https://docs.cloud.google.com/pubsub/docs/smts/ai-inference-smt>
- SMT overview: <https://docs.cloud.google.com/pubsub/docs/smts/smts-overview>

## Fact-check

- The article's claims of "direct model invocation inside Pub/Sub streaming" (translated), "Gemini
  Enterprise Agent Platform support" (translated), and "NLP / fraud detection / semantic search" (translated)
  **match official use cases** (official docs list real-time enrichment, simplified AI pipelines,
  reduced latency, and enhanced flow control).
- **The GA label is accurate** (the official blog post "Streaming AI news from Next '26" explicitly
  states GA).
- "Gemini Enterprise Agent Platform" is a **rebrand of Vertex AI** (renamed around Next '26).
  Official docs write "Agent Platform (previously Vertex AI)". IAM roles and APIs keep the old names
  (`Vertex AI ...` / `aiplatform.*`).

## Two types of SMT

| Type | Purpose | Official docs |
|---|---|---|
| **AI Inference** | Runs inference on an Agent Platform model and attaches the result to the message | [ai-inference-smt](https://docs.cloud.google.com/pubsub/docs/smts/ai-inference-smt) |
| **JavaScript UDF** | Transforms or filters using any JS function (returning `null` drops the message) | [udfs-overview](https://docs.cloud.google.com/pubsub/docs/smts/udfs-overview) |

Both **can be chained**. A typical pattern is: format for model input with a UDF -> AI Inference
-> post-process with a UDF.

## Topic SMT vs. Subscription SMT

- **Topic SMT**: Runs **before** Pub/Sub stores the message. The result is **shared across all subscribers**.
- **Subscription SMT**: Runs **just before** delivery. The result applies **only to that subscription**.

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

Legend:

- Topic SMT: Topic-side transform (runs once before storage; shared by all subscribers)
- Subscription SMT: Subscription-side transform (runs just before delivery; applies only to that sub)
- stored: Saved to Pub/Sub internal storage
- sub: Subscription
- subscriber: Subscriber application

## Implementation: minimal steps (gcloud)

> These steps are an example to learn the behavior. Test them in a disposable verification project.
> Change production GCP only via OpenTofu and PRs (IaC policy).

### 1. Transform definition file (YAML)

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

- `endpoint` format:
    - Model Garden (MaaS) models:
      `projects/PROJECT/locations/LOCATION/publishers/PUBLISHER/models/MODEL_NAME`
    - Self-deployed models: `projects/PROJECT/locations/LOCATION/endpoints/ENDPOINT`
- `unstructuredInference.parameters` specifies model parameters merged into each message (optional).
- `service_account_email` can also be set (optional; defaults to the Pub/Sub service agent).

### 2. Create a topic and subscription to test

```bash
# Create a topic
gcloud pubsub topics create TOPIC_ID

# Create a subscription with AI Inference SMT (extend ack-deadline since inference takes up to 60s)
gcloud pubsub subscriptions create TOPIC_ID-sub \
  --ack-deadline=600 \
  --topic TOPIC_ID \
  --message-transforms-file ai-smt.yaml

# Publish a prompt in Chat Completions API format
gcloud pubsub topics publish TOPIC_ID --message=$'{
  "model":"google/gemini-2.5-flash","messages":[{
    "role": "user",
    "content": "Explain how AI works in a few words"
    }]
  }'

# Pull the message with the inference result attached
gcloud pubsub subscriptions pull TOPIC_ID-sub
```

To attach to a topic, run `gcloud pubsub topics create TOPIC_ID --message-transforms-file ai-smt.yaml`.

## Input and output formats

- **Input**: Message data is a **JSON string sent to the model**. The SMT merges `parameters` and
  sends it. Pub/Sub does not validate the input, so valid formatting is the caller's responsibility.
- **Output**: On success, wraps the original message in this structure:

```json
{
  "original_message": { ORIGINAL_MESSAGE },
  "model_output": { INFERENCE_RESULT }
}
```

## APIs invoked (by model type)

| Model | API invoked |
|---|---|
| Self-deployed (all types) | `rawPredict` |
| Gemini foundational (e.g., `gemini-3.0-pro`) | Chat Completions API |
| Other Gemini (e.g., embeddings) | `rawPredict` |
| Anthropic / Mistral / AI21 | `rawPredict` |
| Other MaaS | Chat Completions API |

Compatible MaaS models include Gemini 2.0/2.5/3 series, Claude (Sonnet/Opus/Haiku 4 series), Llama
3.3/4, Mistral, DeepSeek, Qwen3, GPT-OSS, and various embeddings. Some models (such as certain
embedding-2, Veo, Lyria, and latest thinking models) are **unsupported**. Check the official page
for the current compatibility table.

## IAM

- Operator: `roles/pubsub.editor` (permission to create topics and subscriptions).
- Permissions on the Agent Platform endpoint for the service account invoking inference:
    - Permissions: `aiplatform.endpoints.get` / `aiplatform.endpoints.predict`
    - Role to grant: **Vertex AI Service Agent** if using the Pub/Sub service agent, or **Vertex AI
      User** if using a custom SA.

## Flow control (useful for "fraud detection" (translated) etc. in the article)

To avoid overloading endpoints, Pub/Sub **automatically adjusts the request rate** based on latency
and quota (unsupported when using the unary pull API). You do not need to build your own
backpressure logic.

> **Terminology note**: "Elastic Inference Queue" in the original article does not appear in official
> docs. It appears to be a slide paraphrase of this **flow control (automatic rate adjustment)**
> feature. Do not search for an API or setting under that name.

## Constraints and pitfalls

- At most **one AI Inference SMT** per topic or subscription.
- **Private endpoints are unsupported** (place self-deployed models on a public Agent Platform endpoint).
- **Global endpoints** work only for Gemini foundation models. All others require a regional endpoint.
- **No client-side batching** (1 message = 1 inference request). Asynchronous batch inference is also unsupported.
- Inference must finish **within 60 seconds**. Exceeding this triggers a delivery timeout, retries,
  and eventually routes to the dead-letter topic. **Configure a dead-letter topic when using a
  subscription SMT.**
- The final message size (original + inference output) must stay within Pub/Sub's message size limit.
- **Region constraints**: For a topic SMT, the endpoint's region must fall within the topic's message
  storage policy. When attached to an export subscription (BigQuery or Cloud Storage), it must match
  the destination resource's region. Locational endpoints are recommended for pull.

## Error handling

- **Topic SMT errors**: The entire publish fails and returns an error to the publisher (if even one
  message in a batch fails, **the entire batch fails**).
- **Subscription SMT errors**: Can be forwarded to a dead-letter topic.
- Monitoring: `topic/message_transform_latencies` (status / filtered labels) and `topic/byte_cost`
  (`operation_type` / `response_code`).

## Official sample implementations

- Python samples (`pubsub_v1` client; SMTs use `MessageTransform` and `JavaScriptUDF` types):
  [`GoogleCloudPlatform/python-docs-samples` -> `pubsub/cloud-client`](https://github.com/GoogleCloudPlatform/python-docs-samples/tree/main/pubsub/cloud-client)
- SMT validation and testing steps (validate before creating a topic or subscription):
  [create-topic-smt](https://docs.cloud.google.com/pubsub/docs/smts/create-topic-smt) /
  [create-subscription-smt](https://docs.cloud.google.com/pubsub/docs/smts/create-subscription-smt)
- End-to-end demo example using a **UDF SMT** (not AI Inference SMT) to format payloads:
  [`devrel-demos` -> `data-analytics/event_driven_agents_demo` `setup/`](https://github.com/GoogleCloudPlatform/devrel-demos/tree/main/data-analytics/event_driven_agents_demo)
  (details in [03-bigquery-continuous-queries-stateful/](../03-bigquery-continuous-queries-stateful/README.md))

## Related links

Based on the official docs as of 2026-06.

- SMT announcement blog:
  <https://cloud.google.com/blog/products/data-analytics/pub-sub-single-message-transforms>
- Choosing between topic and subscription SMTs:
  <https://docs.cloud.google.com/pubsub/docs/smts/choose-smts>
- Pub/Sub release notes: <https://docs.cloud.google.com/pubsub/docs/release-notes>
- Deep-dive article (Medium / Google Cloud Community):
  <https://medium.com/google-cloud/deep-dive-into-google-cloud-pub-sub-single-message-transforms-and-ai-inference-baa920d8103a>
