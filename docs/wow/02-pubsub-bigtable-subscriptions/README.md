# Pub/Sub Bigtable Subscriptions (Preview)

An export subscription that **writes Pub/Sub messages directly into a Bigtable table without
writing a subscriber client**. This is what the article refers to as "no custom ETL needed" (translated)
and "for sub-millisecond serving" (translated).

- Launch stage: **Preview** (Pre-GA; `gcloud beta` commands)
- Overview: <https://docs.cloud.google.com/pubsub/docs/bigtable-subscriptions>
- Creation steps: <https://docs.cloud.google.com/pubsub/docs/create-bigtable-subscription>

## Fact-check

- The article's claims of "direct writes from Pub/Sub to Bigtable" (translated), "no custom ETL needed" (translated),
  and "for real-time serving" (translated) **match official docs**.
- **The Preview label is accurate** (the official page has a Pre-GA banner).
- "Sub-millisecond latency" (translated) describes **Bigtable read performance**. The write path is
  at-least-once and performs no deduplication (details below).

## Positioning (when to use)

- Want to write messages to Bigtable **with no extra processing or only lightweight SMT transforms** ->
  **Bigtable subscription**.
- Need complex transformations -> **Dataflow + pull subscription** is recommended (explicitly stated in official docs).

> **Terminology note**: "Bigtable materialized views" (translated) in the original article's
> architecture diagram is a **separate feature** from Bigtable Subscriptions. Subscriptions write
> raw messages directly. The other feature is
> [Bigtable continuous materialized views](https://docs.cloud.google.com/bigtable/docs/continuous-materialized-views),
> which are **SQL-defined background aggregation views** (incrementally aggregating incoming data,
> propagating updates and deletes, eventually consistent).

## Prerequisites

- The destination Bigtable table must **already exist**.
- The table must **have a `data` column family**.
- Also create a **`pubsub_metadata` column family** if writing metadata (optional).

## Implementation: end-to-end example (gcloud)

> These steps are an example to learn the behavior. Test them in a disposable verification project.
> Change production GCP only via OpenTofu and PRs (IaC policy).

```bash
# 1. Bigtable instance
gcloud bigtable instances create my-instance --display-name="My instance" \
  --cluster-config=id=my-cluster-1,zone=ZONE,nodes=1

# 2. Table with the data column family
gcloud bigtable instances tables create table-1 \
  --instance=my-instance \
  --column-families=data

# 3. topic
gcloud pubsub topics create topic-1

# 4. Bigtable subscription (Preview = beta)
gcloud beta pubsub subscriptions create bigtable-sub \
  --topic=topic-1 \
  --bigtable-table=projects/PROJECT_ID/instances/my-instance/tables/table-1

# 5. publish
gcloud pubsub topics publish topic-1 --message='{"name":"Alice"}'
```

Verify in the Bigtable Studio query editor:

```sql
SELECT _key, JSON_VALUE(CAST(data[''] AS STRING), '$.name') AS name FROM table-1;
```

### Key flags

- `--bigtable-write-metadata`: Writes message metadata to the `pubsub_metadata` family.
- `--bigtable-app-profile-id=APP_PROFILE`: App profile to use. **Requires single-cluster routing.**
  Uses the default app profile if omitted.
- `--bigtable-service-account-email`: Service account used for writing. Defaults to the Pub/Sub service agent if omitted.

## Write layout

- **Message data**: Written as a single cell of **`BYTES` type** under the **empty string (`""`)
  column qualifier** in the `data` family. Cell timestamp = the message's **publish time**.
- **Row key**: `projects/PROJECT_NUMBER/subscriptions/SUBSCRIPTION_ID#SALT_PREFIX#MESSAGE_ID`
  (concatenation of subscription ID, salt prefix, and message ID). The salt prefix spreads hotspots.
- **Metadata** (when `--bigtable-write-metadata` is set; `pubsub_metadata` family): String-typed
  `subscription_name`, `message_id`, and `attributes` (JSON).

```text
Bigtable table : 1 message = 1 row

 row key = projects/<PROJECT_NUMBER>/subscriptions/<SUB_ID>#<SALT>#<MESSAGE_ID>
   |
   +-- column family "data"                +-- column family "pubsub_metadata" (optional)
   |     qualifier ""  = <message BYTES>   |     subscription_name = <String>
   |     cell ts       = publish time      |     message_id        = <String>
   |                                       |     attributes        = <JSON String>
   v                                       v
 (always written)                        (only with --bigtable-write-metadata)
```

Legend:

- row key: Row key (concatenation of subscription ID, salt prefix, and message ID; salt spreads hotspots)
- column family "data": Required family storing the message body
- qualifier "": Empty-string column qualifier (holds the single body cell)
- message BYTES: Body stored as BYTES
- cell ts: Cell timestamp (= message publish time)
- column family "pubsub_metadata": Metadata family (written only when `--bigtable-write-metadata` is specified)

## Combining with SMT

Bigtable subscriptions **can be combined with SMTs**. You can run lightweight formatting (PII
masking, field removal, labeling via AI Inference, etc.) in an SMT before materializing to
Bigtable. The article's pattern of "storing vector embeddings in Bigtable for semantic search" (translated)
can be built by chaining an AI Inference SMT (embedding model) into a Bigtable subscription.

## Delivery semantics and failure handling

- **At-least-once**. If you need strict deduplication, deduplicate downstream in Bigtable or use
  Dataflow's exactly-once processing.
- On write failure, the message is nacked and retried. After repeated failures, if a **dead-letter
  topic** is configured, the message is forwarded there. DLT messages carry the failure reason in the
  `CloudPubSubDeadLetterSourceDeliveryErrorMessage` attribute.
- While Pub/Sub cannot write to Bigtable, it applies backoff similar to push backoff.

## IAM

- Grant **Bigtable User (`roles/bigtable.user`)** to the Pub/Sub service agent
  (`service-PROJECT_NUMBER@gcp-sa-pubsub.iam.gserviceaccount.com`) at the project or instance level.
- For finer control, specify a user-managed SA (`--bigtable-service-account-email`). That SA needs
  Bigtable User, the Pub/Sub service account needs `iam.serviceAccounts.getAccessToken`, and the
  creator needs `iam.serviceAccounts.actAs`.

## Constraints and pitfalls

- The subscription does not create the table or the `data` family ([Prerequisites](#prerequisites)).
- Region / quota: Per-region quotas apply to Bigtable subscriber throughput.
- No strict ordering or deduplication (at-least-once).
- Troubleshooting:
  <https://docs.cloud.google.com/pubsub/docs/troubleshoot-bigtable-subscriptions>

## Sample implementations (verified 2026-06)

Bigtable subscriptions require no subscriber code (everything is done in gcloud or the Console).
There is no dedicated app sample; the official
[creation steps](https://docs.cloud.google.com/pubsub/docs/create-bigtable-subscription) used above
serve as the example. Python samples for publishing and related operations are below.

- Pub/Sub Python samples:
  [`GoogleCloudPlatform/python-docs-samples` -> `pubsub/cloud-client`](https://github.com/GoogleCloudPlatform/python-docs-samples/tree/main/pubsub/cloud-client)
  / [`GoogleCloudPlatform/cloud-pubsub-samples-python`](https://github.com/GoogleCloudPlatform/cloud-pubsub-samples-python)
- Reference (**community / unofficial**; Pub/Sub-to-Bigtable via Cloud Functions, predating the
  subscription feature):
  [`krapes/pubsub_bigtable`](https://github.com/krapes/pubsub_bigtable)

## Related links

- Choosing a subscription type: <https://docs.cloud.google.com/pubsub/docs/subscriber>
- Bigtable overview: <https://docs.cloud.google.com/bigtable/docs/overview>
