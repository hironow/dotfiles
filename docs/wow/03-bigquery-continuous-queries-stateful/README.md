# BigQuery Continuous Queries — Stateful Data Processing (Preview)

**Always-running SQL** processes data arriving in BigQuery in real time and writes results to
BigQuery tables, Pub/Sub, Bigtable, or Spanner. The highlight in the article is that **stateful
processing (JOINs, aggregations, and tumbling windows) is available in Preview**.

- Continuous queries themselves: existing feature
- **Stateful operations (JOIN / aggregations / windowing): Preview**
- Overview: <https://docs.cloud.google.com/bigquery/docs/continuous-queries-introduction>
- Examples: <https://docs.cloud.google.com/bigquery/docs/continuous-queries>

## Fact-check

- The article's claims — "support for aggregate functions, tumbling windows, and JOIN processing" (translated),
  "computing 30-minute averages" (translated), "correlating events across different streams" (translated),
  "direct generative AI integration such as AI.GENERATE_TEXT" (translated), and "reverse ETL to Bigtable,
  Spanner, and Pub/Sub" (translated) — **all match official docs**.
- **The Preview label is accurate** (the stateful operations section carries a Pre-GA banner;
  feedback address `bq-continuous-queries-feedback@google.com`).

## What makes it "stateful"

- **Stateless functions**: Process each row independently (transformations, JSON manipulation,
  generative AI calls, etc.).
- **Stateful operations**: Maintain state across multiple rows or time intervals to compute accurate
  results. Available in Preview:
    - [JOINs](https://docs.cloud.google.com/bigquery/docs/continuous-query-joins)
      — correlate events across different streams
    - [Aggregations / windowing](https://docs.cloud.google.com/bigquery/docs/window-aggregations)
      — use `TUMBLE` (tumbling windows) to compute values such as "every 5 minutes" or "30-minute averages"

```text
stateless : 1 row in -> 1 row out (no memory across rows)

  row1 -> out1     row2 -> out2     row3 -> out3

stateful : TUMBLE keeps state per fixed, non-overlapping window

  time -->  e1  e2       e3   e4        e5   e6 e7        e8
          |-------------|-------------|-------------|-------------|
          |  window 1   |  window 2   |  window 3   |  window 4   |  TUMBLE(5 min)
          |-------------|-------------|-------------|-------------|
                |             |             |             |
                v             v             v             v
             agg(w1)       agg(w2)       agg(w3)       agg(w4)       COUNT / AVG / JOIN
```

Legend:

- stateless: Processes each row independently (no state carried across rows)
- stateful: Maintains state across rows or time intervals
- time: Time axis
- e1..e8: Incoming events (rows)
- window N: Tumbling window (fixed-length, non-overlapping interval)
- TUMBLE(5 min): Function that partitions data into 5-minute intervals
- agg(wN): Aggregation result for that window (COUNT, AVG, JOIN, etc.)

## Input data sources

Continuous queries process incoming data written to standard BigQuery tables (via Storage Write API,
`tabledata.insertAll`, batch loads, `INSERT` DML, Pub/Sub BigQuery subscriptions, Dataflow -> BigQuery,
Datastream append-only, etc.).

Use change-history TVFs to control the starting timestamp:

- `APPENDS(TABLE ..., start_timestamp)` — processes rows appended at or after the specified timestamp
- `CHANGES(...)` — processes inserts and updates (Pub/Sub export only; **cannot be combined with stateful operations**)

## Implementation examples

### Example 1: Filter and transform into another table (stateless)

```sql
INSERT INTO `myproject.real_time_taxi_streaming.transformed_taxirides`
SELECT
  timestamp, meter_reading, ride_status, passenger_count,
  ST_Distance(
    ST_GeogPoint(pickup_longitude, pickup_latitude),
    ST_GeogPoint(dropoff_longitude, dropoff_latitude)) AS euclidean_trip_distance,
  SAFE_DIVIDE(meter_reading, passenger_count) AS cost_per_passenger
FROM APPENDS(
  TABLE `myproject.real_time_taxi_streaming.taxirides`,
  CURRENT_TIMESTAMP() - INTERVAL 10 MINUTE)
WHERE ride_status = 'dropoff';
```

### Example 2: Call generative AI and export to Pub/Sub (real-time generation)

```sql
EXPORT DATA OPTIONS (
  format = 'CLOUD_PUBSUB',
  uri = 'https://pubsub.googleapis.com/projects/myproject/topics/taxi-real-time-rides') AS (
  SELECT
    TO_JSON_STRING(STRUCT(ride_id, timestamp, latitude, longitude, prompt, result)) AS message
  FROM AI.GENERATE_TEXT(
    MODEL `myproject.real_time_taxi_streaming.taxi_ml_generate_model`,
    (
      SELECT timestamp, ride_id, latitude, longitude,
        CONCAT('Generate an ad based on the current latitude of ',
               latitude, ' and longitude of ', longitude) AS prompt
      FROM APPENDS(
        TABLE `myproject.real_time_taxi_streaming.taxirides`,
        CURRENT_TIMESTAMP() - INTERVAL 10 MINUTE)
      WHERE ride_status = 'enroute'
    ),
    STRUCT(50 AS max_output_tokens, 1.0 AS temperature, 40 AS top_k, 1.0 AS top_p)) AS ml_output
);
```

### Example 3: JOIN and tumbling-window aggregation (stateful, Preview highlight)

```sql
INSERT INTO `real_time_taxi_streaming.neighborhood_taxi_health`
WITH potential_matches AS (
  SELECT
    requests._CHANGE_TIMESTAMP AS bq_changed_ts,
    requests.geohash, requests.latitude, requests.longitude,
    ST_DISTANCE(
      ST_GEOGPOINT(requests.longitude, requests.latitude),
      ST_GEOGPOINT(taxis.longitude, taxis.latitude)) AS distance_in_meters
  FROM APPENDS(TABLE `real_time_taxi_streaming.ride_requests`,
              CURRENT_TIMESTAMP() - INTERVAL 10 MINUTE) AS requests
  INNER JOIN APPENDS(TABLE `real_time_taxi_streaming.taxirides`,
              CURRENT_TIMESTAMP() - INTERVAL 10 MINUTE) AS taxis
    ON requests.geohash = taxis.geohash
  WHERE taxis.ride_status = 'available'
    AND taxis._CHANGE_TIMESTAMP
        BETWEEN (requests._CHANGE_TIMESTAMP - INTERVAL 5 MINUTE) AND requests._CHANGE_TIMESTAMP
)
SELECT
  window_end, geohash,
  COUNT(*) AS taxi_demand_volume,
  ROUND(AVG(distance_in_meters), 2) AS avg_proximity_meters,
  ROUND(MIN(distance_in_meters), 2) AS min_proximity_meters,
  ROUND(MAX(distance_in_meters), 2) AS max_proximity_meters,
  ROUND(STDDEV(distance_in_meters), 2) AS proximity_stddev
FROM TUMBLE(TABLE potential_matches, "bq_changed_ts", INTERVAL 5 MINUTE)
GROUP BY window_end, geohash;
```

## Available AI and ML functions

- Generative AI: `AI.GENERATE` / `AI.GENERATE_TEXT` (calls Agent Platform models via BigQuery ML
  remote models)
- AI APIs: `ML.UNDERSTAND_TEXT` / `ML.TRANSLATE` (Cloud AI API remote models)
- Preprocessing: `ML.NORMALIZER`
- Creating a remote model:
  <https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/bigqueryml-syntax-create-remote-model>

## Destinations (reverse ETL)

`EXPORT DATA` writes to **Pub/Sub, Bigtable, or Spanner** (no other destinations are supported).
A typical use case is reverse ETL, writing analytical results back to low-latency serving systems
(Bigtable or Spanner).

- [Export to Pub/Sub](https://docs.cloud.google.com/bigquery/docs/export-to-pubsub)
- [Export to Bigtable](https://docs.cloud.google.com/bigquery/docs/export-to-bigtable)
- [Export to Spanner](https://docs.cloud.google.com/bigquery/docs/export-to-spanner)

## Constraints and pitfalls (important)

- **Max execution time**: **Up to 2 days** when run by a user account, and **up to 150 days** when
  run by a service account. Once reached, the job fails and stops — use a service account in production.
- Exceeding a **48-hour watermark lag** causes the **job to fail**. Design `APPENDS` / `CHANGES` to
  resume from where the job stopped.
- **SQL cannot be modified while running** (stop and recreate the job). Cannot be run from Data Canvas.
- Stateful queries allow only supported JOINs, aggregations, and windowing. `PIVOT`, `UNPIVOT`,
  `TABLESAMPLE`, set operations, `SELECT DISTINCT`, `EXISTS` subqueries, recursive CTEs, UDFs,
  window function calls, DDL, and DML other than `INSERT` are **unsupported**.
- Unsupported data sources: external tables, information schema, Iceberg managed tables,
  wildcard tables, CDC upserts, materialized views, and some views.
- Column-level and row-level security are unsupported.
- Region: Exports to Bigtable, Spanner, or Pub/Sub locational endpoints must target resources within
  the **same region boundary** as the source BigQuery dataset (Pub/Sub global endpoints are an exception).
- `CHANGES` cannot be used with stateful operations ([Input data sources](#input-data-sources)).

## Agent integration (core of "thinking data" (translated) in the article)

- **Autonomous agent triggering**: Detects complex events in live streams to trigger agentic pipelines.
- **Autonomous agent monitoring**: Streams agent traces, tool usage, and logs to BigQuery for
  observability using ADK's
  [BigQuery agent analytics plugin](https://adk.dev/integrations/bigquery-agent-analytics/).

## Official sample implementations and codelabs

Verified to exist on 2026-06-08.

### Highlight: Event-driven data agent (E2E across stateful CQ, Pub/Sub SMT, and ADK)

Detects "Impossible Travel" anomalies with a stateful continuous query -> Pub/Sub (payload formatted
via SMT) -> an ADK agent on Vertex AI Agent Engine (Gemini 2.5 Flash + `BigQueryToolset` +
`google_search`) classifies `FALSE_POSITIVE` or `ESCALATION_NEEDED`. This **complete demo spans all
three features**. Takes ~60 minutes and costs under $2.

- Official codelab (Next '26):
  <https://codelabs.developers.google.com/next26/bigquery-adk-event-driven-agents>
- Official blog:
  [Building Event-Driven Data Agents with BigQuery, Pub/Sub, and ADK](https://cloud.google.com/blog/topics/developers-practitioners/building-event-driven-data-agents-with-bigquery-pubsub-and-adk)
- Key files in GitHub [`GoogleCloudPlatform/devrel-demos` -> `data-analytics/event_driven_agents_demo`](https://github.com/GoogleCloudPlatform/devrel-demos/tree/main/data-analytics/event_driven_agents_demo):
    - `setup/continuous_query.sql` — stateful CQ definition (JOIN between transactions and customer profiles)
    - `setup/transform.yaml` + `setup/pubsub_to_adk_transform.js` — Pub/Sub SMT (JavaScript UDF)
      that unwraps and normalizes the BigQuery export payload into the Agent Engine envelope
    - `setup/setup_env.sh` / `load_historical_data.py` / `customer_profiles.csv` — environment setup and historical data
    - `agent/adk_agent_app/agent.py` + `tools.py` — ADK agent (`gemini-2.5-flash` default +
      `BigQueryToolset` + `google_search`); deployed to Agent Engine with `agent_runner.py` / `deploy_agent_script.py`
    - `simulator/generate_events.py` — synthetic transaction generator

### ADK and BigQuery tools, evaluation, and observability

- ADK BigQuery tools: <https://google.github.io/adk-docs/tools/google-cloud/bigquery/>
- Codelab (build and evaluate a BigQuery agent with ADK + GenAI Eval):
  <https://codelabs.developers.google.com/bigquery-adk-eval>
- BigQuery Agent Analytics:
  [official blog](https://cloud.google.com/blog/products/data-analytics/introducing-bigquery-agent-analytics)
  / [codelab](https://codelabs.developers.google.com/adk-bigquery-agent-analytics-plugin)
- Reference (community / unofficial; Telco monitoring case using stateful CQ + ADK):
  [Stream processing with BigQuery STATEFUL continuous queries and ADK agents](https://medium.com/google-cloud/stream-processing-with-bigquery-stateful-continuous-queries-and-adk-agents-for-telco-network-97a3e6973c8e)
