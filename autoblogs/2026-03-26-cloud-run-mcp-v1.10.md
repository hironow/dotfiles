---
title: "Cloud Run MCP v1.10.0 — Secrets Manager・並列ビルド・DeployCompose が示す MCP デプロイ基盤の進化"
date: 2026-03-26
tags: [cloud-run, mcp, gcp, deploy, compose, secrets-manager]
source: docs/changelogs.md
---

# Cloud Run MCP v1.10.0 — Secrets Manager・並列ビルド・DeployCompose が示す MCP デプロイ基盤の進化

Cloud Run MCP は v1.10.0 で**本格的なプロダクション運用基盤**への転換点を迎えた。2026-03-26 時点で、v1.10.0 のリリースに加えて Secrets Manager サポート・ボリュームマウント・並列ビルド・DeployCompose という未リリース変更群が積み上がっている。これらの変更が示す**アーキテクチャの方向性**と、MCP エコシステムにおける Cloud Run MCP の設計思想を分析する。

## v1.10.0 の意味——クライアント分離とテスト基盤の確立

### cloud-run-mcp クライアントの分離

v1.10.0 で追加された **cloud-run-mcp クライアント**（#242）は、OSS Run MCP からのデプロイ用クライアントを分離した設計変更だ。「クライアント」という概念の導入は、サーバー（MCP サーバー本体）とクライアント（デプロイを起動する側）の責務分離を明確にする。

この分離は MCP エコシステム全体の方向性と整合する。MCP 2025-11-25 では **Extensions フレームワーク**（SEP-2133, Final）が追加され、機能ケイパビリティのスキーマ化が進んでいる。クライアントがサーバーのケイパビリティを問い合わせながらデプロイ戦略を選択する——これが Cloud Run MCP が目指す設計だ。

### Ingress ポリシーの環境変数化（#243）

**Ingress ポリシー環境変数**（#243）による設定は、**インフラストラクチャ as コード**の文脈で重要な変更だ。ハードコードされたポリシーをコード変更なしに変更できることで、同一のデプロイアーティファクトを複数環境（開発・ステージング・本番）で使い回せる。

| 環境 | Ingress ポリシー例 | 変更前の問題 |
|------|----------------|------------|
| 開発 | all（全許可） | コード変更が必要 |
| ステージング | internal-and-cloud-load-balancing | コード変更が必要 |
| 本番 | internal（内部のみ） | コード変更が必要 |
| 変更後 | 環境変数で制御 | コード変更不要 |

### 統合テストの多言語対応（#235, #237, #239）

v1.10.0 で追加された **Java、Node.js、Python プロジェクトの統合テスト**（#235, #237, #239）は、Cloud Run MCP が **言語非依存のデプロイ基盤** として成熟したことを示す。MCP ツールを通じて Cloud Run にデプロイされるアプリは、単一言語に限定されない——この前提の下でテスト基盤を整備している。

## 未リリース変更群——v1.10.0 以降の進化方向

### Secrets Manager サポート

**Secrets Manager サポート**（compose デプロイメントでの Secrets Manager サポート）は、エンタープライズ運用における最重要機能だ。Cloud Run で機密情報を扱う場合、以下の選択肢が存在する：

```yaml
# Before: 環境変数への平文埋め込み（非推奨）
env:
  - name: DB_PASSWORD
    value: "plaintext-secret"

# After (Secrets Manager 統合後): Secret Manager 参照
env:
  - name: DB_PASSWORD
    valueFrom:
      secretKeyRef:
        name: db-password-secret
        key: latest
```

Secrets Manager 統合は、ADK Python v1.27.3 の**任意モジュールインポート防止**や v1.27.4 の**LiteLLM 脆弱バージョン除外**と同じ文脈に置かれる。**エージェントが外部と接触する機会を増やす機能拡張と並走したセキュリティ強化**という方向性だ。

### ボリュームマウントサポート

**ボリュームマウント機能**は、Cloud Run でステートフルなワークロードを扱う際に不可欠だ。MCP ツールが扱うデータ——PDF ドキュメント（MCP-Apps v1.3.1）、GCS Skills（ADK Python v1.27.0）、GenAI Toolbox のデータソース——は、ボリュームマウントを通じて永続的に扱える。

| ボリュームタイプ | ユースケース | MCP エコシステムとの関係 |
|--------------|-----------|---------------------|
| Cloud Storage Fuse | 大規模ドキュメント処理 | ADK Python GCS Skills との統合 |
| Secret Manager | 認証情報の安全な管理 | ADK Python v1.27.3 セキュリティ強化 |
| NFS | 共有ファイルシステム | マルチエージェント間データ共有 |
| In-memory | 高速一時領域 | ストリーミング処理の中間バッファ |

### 並列ビルド——デプロイ速度の設計思想

**並列ビルド**（run compose での並列ビルドサポート）は、**開発者体験の改善**という観点で重要だ。

AG-UI v0.0.48 の**並列 LRO ツールコール**（2026-03-24）と ADK Go v1.0.0 以降の**Progressive SSE ストリーミングと並列関数実行**が示す「並列処理による体験品質向上」の哲学は、デプロイ基盤にも適用される。複数のコンテナイメージを並列にビルドすることで、マルチサービス構成のデプロイ時間を短縮する。

### DeployCompose——Docker Compose から Cloud Run への移行

**DeployCompose 機能**は、Cloud Run MCP の設計において最も重要な変更の一つだ。Docker Compose 形式の設定を Cloud Run にそのままデプロイする能力は、**ローカル開発とクラウドデプロイの境界を消す**設計思想を体現する。

```
Docker Compose 設定
    |
    | DeployCompose
    v
Cloud Run サービス群
    |
    +-- Service A (MCP サーバー)
    +-- Service B (エージェントバックエンド)
    +-- Service C (データベースプロキシ)
```

Legend / 凡例:

- DeployCompose: Docker Compose 定義を Cloud Run にデプロイする変換レイヤー
- MCP サーバー: Model Context Protocol を実装したサービス
- エージェントバックエンド: ADK Python/Go/JS を使用したエージェント実装

この設計は、**Agent Starter Pack v0.39.6**（2026-03-25）で追加された **GKE デプロイターゲット**（#833）と対比して読むべきだ。GKE が Kubernetes ベースの複雑なオーケストレーションを提供するのに対し、Cloud Run MCP は Compose の簡潔さを保ちながらサーバーレスデプロイを実現する。

## v1.9.0 から v1.10.0 へ——依存関係の継続的更新

v1.9.0 での Hono v4.12.0、AJV v8.18.0、fast-xml-parser 更新は、v1.10.0 の Hono 4.12.7 への継続更新と合わせて、**依存関係の積極的な管理**という方針を示している。

| 依存関係 | v1.9.0 | v1.10.0 | 方向性 |
|--------|--------|---------|--------|
| Hono | v4.12.0 | 4.12.7 | セキュリティパッチ継続適用 |
| AJV | v8.18.0 | 継続 | スキーマバリデーション安定化 |
| googleapis | v171（gcloud-mcp）| 継続 | Google Cloud API 追従 |

MCP SDK v1.26.0（gcloud-mcp での採用）との整合性を保ちながら、フレームワーク依存関係を最新に保つ——この姿勢は、**サプライチェーンセキュリティ**の観点からも重要だ。

## Cloud Run MCP と GKE MCP の設計対比

2026-03-23 にリリースされた **GKE MCP v0.10.0** との設計対比は、Google Cloud MCP エコシステムの全体像を理解する上で有益だ。

| 観点 | Cloud Run MCP v1.10.0 | GKE MCP v0.10.0 |
|------|---------------------|----------------|
| デプロイ単位 | サービス（コンテナ単位） | ワークロード（Pod/Deployment） |
| スケーリング | 自動スケールインゼロ | GKE Workload Scaling スキル |
| セキュリティ | Ingress ポリシー、Secrets Manager | GKE Workload Security スキル (#172) |
| イメージ管理 | Golden Image Finder なし | Golden Image Finder スキル |
| 言語対応 | Java, Node.js, Python（#235, #237, #239） | Go/TS（GKE E2E テスト、未リリース） |
| コンポーズ対応 | DeployCompose（未リリース） | なし |

GKE MCP が「**Kubernetes ネイティブのインフラ管理**」を志向するのに対し、Cloud Run MCP は「**シンプルなコンテナデプロイの自動化**」を志向する。この分業は、ADK Python（高機能・複雑）と ADK Go（高性能・シンプル）の関係に似ている。

## MCP エコシステムにおける Cloud Run MCP の戦略的位置

Cloud Run MCP が担うのは、**MCP サーバー自体のデプロイと管理**だ。これは他の MCP サーバー（GKE MCP、gcloud-mcp、GenAI Toolbox など）と異なる特殊な位置付けだ。

MCP サーバーを MCP で管理するという再帰的な構造：

| レイヤー | ツール | バージョン |
|--------|--------|-----------|
| MCP クライアント | Claude Desktop, VSCode, goose | 2025-11-25 仕様準拠 |
| MCP サーバー管理 | Cloud Run MCP | v1.10.0 |
| MCP サーバー群 | gcloud-mcp, GKE MCP, GenAI Toolbox | v0.5.3, v0.10.0, v0.30.0 |
| 基盤エージェント | ADK Python, ADK Go, ADK JS | v1.27.4, v1.0.0, v0.2.4 |
| エージェントプロトコル | A2A, AG-UI | v1.0.0, v0.0.48 |

Secrets Manager サポート・ボリュームマウント・並列ビルド・DeployCompose は、このレイヤー全体を実用的に動かすための**インフラ基盤の充実**を意味する。

## まとめ

Cloud Run MCP v1.10.0 は、クライアント分離（#242）・Ingress ポリシー環境変数化（#243）・多言語統合テスト（#235, #237, #239）という実装の成熟を示している。未リリースの Secrets Manager サポート・ボリュームマウント・並列ビルド・DeployCompose は、**MCP デプロイ基盤がプロダクション運用の要件を本格的に満たす方向**への進化を示す。

ADK Python v1.27.4（2026-03-24）のセキュリティ強化、GKE MCP v0.10.0（2026-03-23）のスキル拡充、Agent Starter Pack v0.39.6（2026-03-25）のデプロイターゲット追加——これらと並走する Cloud Run MCP の進化は、**Google Cloud MCP エコシステム全体のプロダクション化**という方向性を整理すると一貫している。DeployCompose は、その方向性の象徴的な機能だ。

## 参考リンク

- [Cloud Run MCP](https://github.com/GoogleCloudPlatform/cloud-run-mcp)
- [GKE MCP](https://github.com/googleapis/gke-mcp)
- [Agent Starter Pack](https://github.com/GoogleCloudPlatform/agent-starter-pack)
- [gcloud-mcp](https://github.com/googleapis/gcloud-mcp)
