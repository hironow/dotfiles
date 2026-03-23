---
title: "GenAI Toolbox v0.30.0 — migrate/serve サブコマンドと One Skill per Toolset の設計転換"
date: 2026-03-23
tags: [genai-toolbox, google-cloud, mcp, breaking-changes]
source: docs/changelogs.md
---

# GenAI Toolbox v0.30.0 — migrate/serve サブコマンドと One Skill per Toolset の設計転換

Google の GenAI Toolbox が v0.27.0 から v0.30.0 (2026-03-20) まで、わずか数週間で3回のメジャーリリースを重ねた。そのうち2回は破壊的変更を含む。この急速な進化が何を意味するのかを追う。

## 4バージョンで起きたこと

### v0.27.0 — 設定ファイル v2（破壊的）

最初の転換点は**設定ファイルフォーマット v2** (#2369) だった。CLI からのツール直接実行、**Agent Skills** の自動生成、**CockroachDB** 統合が入り、ツールボックスとしての方向性が明確になった。**AlloyDB Omni** データプレーンツールも追加されている。

v0.26.0 では **Tool naming validation** (#2305) が導入され、ツール名の検証が強制化された。この変更もアップグレード時に影響する可能性がある。

### v0.28.0 — データソースの拡大

v0.28.0 では以下のデータソース・ツールが追加された。

| 追加項目 | 詳細 |
|---------|------|
| Dataproc ソース | クラスタ/ジョブの一覧・取得ツール |
| PostgreSQL pgx | 設定可能なクエリ実行モード |
| Redis TLS | Redis 接続の TLS サポート |
| Looker テスト・ビュー | Get All LookML Tests, Run LookML Tests, Create View From Table |
| Looker ディレクトリ管理 | 一覧・作成・削除ツール |
| Oracle DML | DML 操作の有効化 |
| 動的リロードポーリング | 設定変更のポーリング検知 |

地味だが着実にデータソースカバレッジを広げるリリース。

### v0.29.0 — プリビルトツールセット再構成（破壊的）

ここが最大の転換。**AlloyDB**、**Spanner**、**Dataplex**、OSS-DB、**CloudSQL**、**BigQuery**、**Firestore**——すべての**プリビルトツールセット**が再構成された。**テレメトリメトリクス**もセマンティック規約に合わせて変更（破壊的変更）。**MongoDB** ツールアノテーション（LLM 理解向上）、**Serverless Spark** ツール（`get_session_template`, `list/get sessions`）も追加。generate skills コマンドに `additional-notes` フラグ、BigQuery 用カスタム OAuth ヘッダー名サポートも入った。

### v0.30.0 (2026-03-20) — One Skill per Toolset

そして最新の v0.30.0 (2026-03-20)。`migrate` と `serve` の2つの**サブコマンド**が追加され、ツールセットごとに1スキルという原則（**One Skill per Toolset**）が導入された。**Oracle DB** の MCP ツール対応、Looker `git_branch` ツール、Dataplex `search_entries` の**スコープサポート**も入る。パフォーマンス改善として span の遅延処理と **nil 安全性**改善も含まれる。

## 設計思想の変遷を読む

この4リリースを通して見えるのは、GenAI Toolbox が**汎用ツール集合体**から**構造化されたスキルフレームワーク**へ移行しているということだ。

v0.27.0 の **Agent Skills** 自動生成は伏線だった。v0.29.0 でツールセットを再構成し、v0.30.0 で「1ツールセット = 1スキル」を原則化した。これは **AgentSkills 仕様**との整合性を高める動きであり、MCP エコシステム全体での**スキル標準化**を見据えている。

## 破壊的変更への対応

v0.29.0 と v0.27.0 の両方で破壊的変更が入っているため、v0.26.x 以前からのアップグレードは計画的に行う必要がある。

| バージョン | 破壊的変更 | 対応方法 |
|-----------|-----------|---------|
| v0.26.0 | ツール名バリデーション強制化 (#2305) | ツール名の命名規則を確認 |
| v0.27.0 | 設定ファイル v2 (#2369) | `migrate` サブコマンド（v0.30.0）で移行 |
| v0.29.0 | プリビルトツールセット構造 | AlloyDB, Spanner, BigQuery 等のツールセット再設定 |
| v0.29.0 | テレメトリメトリクス | セマンティック規約に合わせた監視設定の更新 |

v0.30.0 で `migrate` サブコマンドが追加されたのは、まさにこの移行パスを公式に提供するためだろう。

## まとめ

GenAI Toolbox は「データベースに繋がる LLM ツール」から「エージェントスキルのフレームワーク」へ進化している。破壊的変更の頻度は高いが、それは設計が固まりつつある過渡期の証拠でもある。v0.30.0 の One Skill per Toolset は、この方向性のマイルストーンだ。

## 参考リンク

- [GenAI Toolbox](https://github.com/googleapis/genai-toolbox)
- [AgentSkills 仕様](https://agentskills.io)
