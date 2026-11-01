# Pub/Sub Bigtable Subscriptions（Preview）

Pub/Sub のメッセージを、**subscriber クライアントを書かずにそのまま Bigtable テーブルへ
書き込む** export subscription。記事の「カスタム ETL 不要」「サブミリ秒サービング向け」は
これを指す。

- Launch stage: **Preview**（Pre-GA。`gcloud beta` 系コマンド）
- 概要: <https://docs.cloud.google.com/pubsub/docs/bigtable-subscriptions>
- 作成手順: <https://docs.cloud.google.com/pubsub/docs/create-bigtable-subscription>

## ファクトチェック

- 記事の「Pub/Sub から Bigtable への直接書き込み」「カスタム ETL 不要」「リアルタイム
  サービング向け」は **公式と一致**。
- **Preview 表記は正しい**（公式ページに Pre-GA バナーあり）。
- 「サブミリ秒レイテンシ」は **Bigtable の読み取り** の特性を指す。書き込み経路は
  at-least-once で、重複排除はしない（後述）。

## 位置づけ（いつ使うか）

- メッセージを **追加処理なし or 軽い SMT 変換だけ** で Bigtable に入れたい → **Bigtable
  subscription**。
- 複雑な変換が必要 → **Dataflow + pull subscription** を推奨（公式が明記）。

> **用語注意**: 元記事のアーキ図にある「Bigtable のマテリアライズドビュー」は、Bigtable
> Subscriptions とは **別の機能**。こちらは raw メッセージを直接書き込む。あちらは
> [Bigtable continuous materialized views](https://docs.cloud.google.com/bigtable/docs/continuous-materialized-views)
> という **SQL 定義の背景集約ビュー**（着信データを増分集約し、update / delete も伝播、
> eventually consistent）。

## 前提条件

- 書き込み先 Bigtable テーブルが **既に存在** すること。
- テーブルに **`data` という column family が必須**。
- メタデータも書くなら **`pubsub_metadata` column family** も用意（任意）。

## 実装：エンドツーエンド例（gcloud）

> この手順は挙動を学ぶための例である。使い捨ての検証用プロジェクトで試す。
> 本番の GCP は OpenTofu と PR でだけ変える（IaC 方針）。

```bash
# 1. Bigtable インスタンス
gcloud bigtable instances create my-instance --display-name="My instance" \
  --cluster-config=id=my-cluster-1,zone=ZONE,nodes=1

# 2. data column family つきテーブル
gcloud bigtable instances tables create table-1 \
  --instance=my-instance \
  --column-families=data

# 3. topic
gcloud pubsub topics create topic-1

# 4. Bigtable subscription（Preview = beta）
gcloud beta pubsub subscriptions create bigtable-sub \
  --topic=topic-1 \
  --bigtable-table=projects/PROJECT_ID/instances/my-instance/tables/table-1

# 5. publish
gcloud pubsub topics publish topic-1 --message='{"name":"Alice"}'
```

Bigtable Studio の query editor で確認:

```sql
SELECT _key, JSON_VALUE(CAST(data[''] AS STRING), '$.name') AS name FROM table-1;
```

### 主なフラグ

- `--bigtable-write-metadata`: メッセージメタデータを `pubsub_metadata` family に書く。
- `--bigtable-app-profile-id=APP_PROFILE`: 使用する app profile。**single-cluster routing
  必須**。未指定ならデフォルト app profile。
- `--bigtable-service-account-email`: 書き込み用 SA。未指定なら Pub/Sub service agent。

## 書き込みレイアウト

- **メッセージ data**: `data` family の **空文字列（`""`）column qualifier** に **`BYTES`
  型** で 1 セル。cell timestamp = メッセージの **publish time**。
- **row key**: `projects/PROJECT_NUMBER/subscriptions/SUBSCRIPTION_ID#SALT_PREFIX#MESSAGE_ID`
  （subscription ID + salt prefix + message ID の連結）。salt prefix がホットスポットを散らす。
- **メタデータ**（`--bigtable-write-metadata` 時、`pubsub_metadata` family）: String 型の
  `subscription_name`（subscription 名）/ `message_id`（メッセージ ID）/ `attributes`
  （メッセージ属性の JSON）。

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

Legend / 凡例:

- row key: 行キー（subscription ID + salt prefix + message ID の連結。salt がホットスポット分散）
- column family "data": メッセージ本体を入れる必須ファミリ
- qualifier "": 空文字列のカラム修飾子（ここに本体 1 セル）
- message BYTES: 本体は BYTES 型で格納
- cell ts: セルのタイムスタンプ（= メッセージの publish time）
- column family "pubsub_metadata": メタデータ用ファミリ（`--bigtable-write-metadata` 指定時のみ）

## SMT との併用

Bigtable subscription は **SMT と組み合わせ可能**。軽い整形（PII マスク、フィールド削除、AI
Inference によるラベル付与など）を SMT で済ませてから Bigtable に materialize できる。記事の
「ベクトル埋め込みを Bigtable に取得してセマンティック検索」は、AI Inference SMT（embedding
モデル）→ Bigtable subscription の組み合わせで実現できる構図。

## 配信セマンティクスと失敗処理

- **at-least-once**。厳密な重複排除が要るなら、Bigtable 側で downstream 重複処理を入れるか、
  Dataflow の exactly-once 処理を使う。
- 書き込み失敗時はメッセージを nack → 再送。一定回数失敗かつ **dead-letter topic** 設定済みなら
  そこへ転送。DLT メッセージには失敗理由が属性
  `CloudPubSubDeadLetterSourceDeliveryErrorMessage` で付く。
- Pub/Sub が Bigtable に書けない間は push backoff 類似のバックオフがかかる。

## IAM

- Pub/Sub service agent（`service-PROJECT_NUMBER@gcp-sa-pubsub.iam.gserviceaccount.com`）に
  **Bigtable User（`roles/bigtable.user`）** を付与（プロジェクト or インスタンス単位）。
- よりきめ細かくするなら user-managed SA を指定（`--bigtable-service-account-email`）。その SA に
  Bigtable User、Pub/Sub service account に `iam.serviceAccounts.getAccessToken`、作成者に
  `iam.serviceAccounts.actAs` が必要。

## 制約・落とし穴

- テーブルと `data` family は subscription が作らない（[前提条件](#前提条件)）。
- リージョン / quota: Bigtable subscriber スループットにリージョン単位の quota あり。
- 厳密な順序保証・重複排除はない（at-least-once）。
- トラブルシュート:
  <https://docs.cloud.google.com/pubsub/docs/troubleshoot-bigtable-subscriptions>

## サンプル実装（2026-06 確認）

Bigtable subscription は subscriber コードを書かない（gcloud / Console で完結する）。
専用のアプリ実装サンプルはなく、上の実装例の出典である公式の
[作成手順](https://docs.cloud.google.com/pubsub/docs/create-bigtable-subscription) がサンプルになる。
publish 側や周辺操作の Python サンプルは以下。

- Pub/Sub Python サンプル群:
  [`GoogleCloudPlatform/python-docs-samples` → `pubsub/cloud-client`](https://github.com/GoogleCloudPlatform/python-docs-samples/tree/main/pubsub/cloud-client)
  / [`GoogleCloudPlatform/cloud-pubsub-samples-python`](https://github.com/GoogleCloudPlatform/cloud-pubsub-samples-python)
- 参考（**コミュニティ・非公式**。Cloud Functions 経由の Pub/Sub→Bigtable。subscription
  機能登場前の手法）:
  [`krapes/pubsub_bigtable`](https://github.com/krapes/pubsub_bigtable)

## 関連リンク

- subscription タイプの選び方: <https://docs.cloud.google.com/pubsub/docs/subscriber>
- Bigtable 概要: <https://docs.cloud.google.com/bigtable/docs/overview>
