# BigQuery Continuous Queries — Stateful Data Processing（Preview）

**常駐し続ける SQL** で、BigQuery に着信したデータをリアルタイム処理し、結果を BigQuery
テーブル / Pub/Sub / Bigtable / Spanner に書き出す。記事の目玉は、その中の **stateful 処理
（JOIN・集約・タンブリングウィンドウ）が Preview で使えるようになった** 点。

- Continuous queries 自体: 既存機能
- **Stateful operations（JOIN / aggregations / windowing）: Preview**
- 概要: <https://docs.cloud.google.com/bigquery/docs/continuous-queries-introduction>
- 実装例: <https://docs.cloud.google.com/bigquery/docs/continuous-queries>

## ファクトチェック

- 記事の「集約関数・タンブリングウィンドウ・JOIN 処理対応」「30 分平均の計算」「異なる
  ストリーム間のイベント相関」「AI.GENERATE_TEXT 等の生成 AI 直接統合」「Bigtable / Spanner /
  Pub/Sub へのリバース ETL」は **すべて公式と一致**。
- 記事の **Preview 表記は正しい**（stateful operations セクションに Pre-GA バナーあり。
  フィードバック窓口 `bq-continuous-queries-feedback@google.com`）。

## 何が "stateful" なのか

- **stateless 関数**: 各行を独立処理（変換・JSON 操作・生成 AI 呼び出しなど）。
- **stateful 操作**: 複数行 / 時間区間にまたがる状態を保持して正確な結果を出す。Preview で
  使えるのは以下:
    - [JOINs](https://docs.cloud.google.com/bigquery/docs/continuous-query-joins)
      — 異なるストリームのイベントを相関
    - [Aggregations / windowing](https://docs.cloud.google.com/bigquery/docs/window-aggregations)
      — `TUMBLE`（タンブリングウィンドウ）で「5 分ごと」「30 分平均」等を算出

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

Legend / 凡例:

- stateless: 各行を独立処理（行をまたぐ状態を持たない）
- stateful: 行 / 時間区間にまたがる状態を保持する処理
- time: 時間軸
- e1..e8: 着信イベント（行）
- window N: タンブリングウィンドウ（固定長・非重複の区間）
- TUMBLE(5 min): 5 分ごとに区切る関数
- agg(wN): そのウィンドウの集約結果（COUNT / AVG / JOIN など）

## 入力データソース

continuous query が処理できるのは標準 BigQuery テーブルへの着信（Storage Write API /
`tabledata.insertAll` / batch load / `INSERT` DML / Pub/Sub BigQuery subscription /
Dataflow → BigQuery / Datastream append-only など）。

時間起点の制御には変更履歴 TVF を使う:

- `APPENDS(TABLE ..., start_timestamp)` — 指定時刻以降の追加行を処理
- `CHANGES(...)` — 追加 + 変更を処理（**stateful 操作とは併用不可**、Pub/Sub export 時のみ）

## 実装例

### 例 1: フィルタ + 変換して別テーブルへ（stateless）

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

### 例 2: 生成 AI を呼んで Pub/Sub へ export（リアルタイム生成）

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

### 例 3: JOIN + タンブリングウィンドウ集計（stateful、Preview の目玉）

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

## 使える AI / ML 関数

- 生成 AI: `AI.GENERATE` / `AI.GENERATE_TEXT`（BigQuery ML remote model 経由で Agent
  Platform モデルを呼ぶ）
- AI API: `ML.UNDERSTAND_TEXT` / `ML.TRANSLATE`（Cloud AI API の remote model）
- 前処理: `ML.NORMALIZER`
- remote model 作成:
  <https://docs.cloud.google.com/bigquery/docs/reference/standard-sql/bigqueryml-syntax-create-remote-model>

## 出力先（リバース ETL）

`EXPORT DATA` で **Pub/Sub / Bigtable / Spanner** に書き出せる（それ以外の宛先は不可）。分析
結果を低レイテンシのサービング系（Bigtable / Spanner）へ書き戻す reverse ETL が代表用途。

## 制約・落とし穴（重要）

- **実行時間上限**: ユーザーアカウント実行は **最大 2 日**、サービスアカウント実行は **最大
  150 日**。到達するとジョブは失敗・停止する → 本番は SA 実行が前提。
- **watermark lag 48 時間** を超えると **ジョブ失敗**。`APPENDS` / `CHANGES` で停止時点から
  再開する設計にしておく。
- **実行中の SQL 変更不可**（止めて作り直す）。data canvas からは実行不可。
- stateful はサポート対象の JOIN / 集約 / windowing のみ。`PIVOT` / `UNPIVOT` /
  `TABLESAMPLE` / set 演算 / `SELECT DISTINCT` / `EXISTS` 子問い合わせ / 再帰 CTE / UDF /
  window function call / DDL / `INSERT` 以外の DML などは **不可**。
- データソース非対応: external table / information schema / Iceberg managed table /
  wildcard table / CDC upsert / materialized view / 一部 view。
- column-level / row-level security 非対応。
- リージョン: Bigtable / Spanner / Pub/Sub locational endpoint への export は、クエリ元
  BigQuery dataset と **同一リージョン境界** 内のリソースのみ（Pub/Sub global endpoint は例外）。
- `CHANGES` は stateful 操作と併用不可。

## エージェント連携（記事の "考えるデータ" の核）

- **autonomous agent triggering**: live stream の複雑イベントを検知して agentic pipeline を
  トリガー。
- **autonomous agent monitoring**: ADK の
  [BigQuery agent analytics plugin](https://adk.dev/integrations/bigquery-agent-analytics/)
  でエージェントの trace / tool 使用 / ログを BigQuery にストリームして可観測性を確保。

## 公式サンプル実装 / codelab（2026-06 実在確認済み）

### 目玉: イベント駆動データエージェント（CQ stateful + Pub/Sub SMT + ADK の E2E）

「Impossible Travel」異常を stateful continuous query で検知 → Pub/Sub（SMT で payload 整形）
→ Vertex AI Agent Engine 上の ADK エージェント（Gemini 2.5 Flash + `BigQueryToolset` +
`google_search`）が `FALSE_POSITIVE` / `ESCALATION_NEEDED` を判定、という **3 機能横断の
完成デモ**。所要 60 分・想定コスト $2 未満。

- 公式 codelab（Next '26）:
  <https://codelabs.developers.google.com/next26/bigquery-adk-event-driven-agents>
- 公式ブログ:
  [Building Event-Driven Data Agents with BigQuery, Pub/Sub, and ADK](https://cloud.google.com/blog/topics/developers-practitioners/building-event-driven-data-agents-with-bigquery-pubsub-and-adk)
- GitHub: [`GoogleCloudPlatform/devrel-demos` → `data-analytics/event_driven_agents_demo`](https://github.com/GoogleCloudPlatform/devrel-demos/tree/main/data-analytics/event_driven_agents_demo)
  （2026-06-08 にファイル構成を実在確認）
    - `setup/continuous_query.sql` — stateful CQ 定義（取引 × 顧客プロファイルの JOIN）
    - `setup/transform.yaml` + `setup/pubsub_to_adk_transform.js` — Pub/Sub SMT（JavaScript
      UDF）。BigQuery export の payload を unwrap・normalize して Agent Engine の envelope へ整形
    - `setup/setup_env.sh` / `load_historical_data.py` / `customer_profiles.csv` — 環境構築・履歴データ
    - `agent/adk_agent_app/agent.py` + `tools.py` — ADK エージェント（`gemini-2.5-flash` 既定 +
      `BigQueryToolset` + `google_search`）。`agent_runner.py` / `deploy_agent_script.py` で Agent Engine へ
    - `simulator/generate_events.py` — 合成トランザクション生成

### ADK × BigQuery のツール / 評価 / 可観測性

- ADK の BigQuery ツール: <https://google.github.io/adk-docs/tools/google-cloud/bigquery/>
- codelab（ADK + GenAI Eval で BigQuery エージェントを構築・評価）:
  <https://codelabs.developers.google.com/bigquery-adk-eval>
- BigQuery Agent Analytics:
  [公式ブログ](https://cloud.google.com/blog/products/data-analytics/introducing-bigquery-agent-analytics)
  / [codelab](https://codelabs.developers.google.com/adk-bigquery-agent-analytics-plugin)
- 参考（コミュニティ / 非公式・stateful CQ + ADK の Telco 監視事例）:
  [Stream processing with BigQuery STATEFUL continuous queries and ADK agents](https://medium.com/google-cloud/stream-processing-with-bigquery-stateful-continuous-queries-and-adk-agents-for-telco-network-97a3e6973c8e)

## 関連リンク

- 概要: <https://docs.cloud.google.com/bigquery/docs/continuous-queries-introduction>
- 実装: <https://docs.cloud.google.com/bigquery/docs/continuous-queries>
- JOINs: <https://docs.cloud.google.com/bigquery/docs/continuous-query-joins>
- windowing: <https://docs.cloud.google.com/bigquery/docs/window-aggregations>
- Pub/Sub へ export: <https://docs.cloud.google.com/bigquery/docs/export-to-pubsub>
- Bigtable へ export: <https://docs.cloud.google.com/bigquery/docs/export-to-bigtable>
- Spanner へ export（reverse ETL）: <https://docs.cloud.google.com/bigquery/docs/export-to-spanner>
