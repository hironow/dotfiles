# プロトコル変更ログ

最終更新: 2026-01-25

各プロトコル・Google Cloud サブモジュールの主要な変更点をまとめたドキュメント。

---

## プロトコル (Protocols)

### A2A (Agent-to-Agent)

**現行バージョン**: v0.4.0

#### 主要な変更点

- **OAuth 2.0 近代化**: implicit/password フロー削除、device code/PKCE 追加、mTLS サポート
- **タスクリスト機能**: `tasks/list` メソッドでページネーション付きタスク取得・フィルタリング
- **スキルセキュリティ**: Skills が Security 要件を指定可能に
- **Agent Card 署名**: 署名検証サポート追加
- **マルチプッシュ通知**: タスクごとに複数のプッシュ通知設定が可能に
- **gRPC/REST定義**: プロトコルに両方の定義を追加

#### 破壊的変更

| 変更 | 影響 |
|------|------|
| `extendedAgentCard` → `AgentCapabilities` に移動 | Agent Card 構造の変更 |
| Well-Known URI: `agent.json` → `agent-card.json` | エンドポイント URL の変更 |
| HTTP binding URL から `/v1` 削除 | API パス変更 |

#### 参考リンク

- [A2A Specification](https://github.com/a2aproject/A2A)

---

### A2UI (Agent-to-User Interface)

**現行バージョン**: v0.9

#### 主要な変更点

- **A2UI over MCP サンプル**: MCP 上での A2UI 実装例を追加
- **TypeScript クラス分離**: Angular 実装間で共有される TypeScript クラスを分離
- **Python SDK CI**: a2ui-agent Python SDK の CI セットアップ
- **アクセシビリティ**: 標準カタログのコンポーネントにアクセシビリティ属性追加
- **メソッドリネーム**: `attachDataModel` → `sendDataModel`
- **テーマシステム**: `styles` → `theme` にリネーム

#### 参考リンク

- [A2UI Specification](https://github.com/anthropics/A2UI)

---

### ACP (Agentic Commerce Protocol)

**現行バージョン**: 2026-01-22 (YYYY-MM-DD バージョニング)

**管理**: OpenAI & Stripe

#### 主要な変更点

- **Enhanced Checkout Capabilities**: チェックアウト機能の大幅強化
- **3DS サポート**: 3D Secure による消費者認証
- **アフィリエイト帰属**: 第三者パブリッシャーへのクレジット帰属
- **Intent Traces**: 構造化されたキャンセルコンテキスト
- **リスクシグナル**: 不正防止のためのリスク情報
- **マルチ通貨**: presentment currency 対応
- **新配送タイプ**: Pickup、Local Delivery

#### 破壊的変更

| 変更 | 影響 |
|------|------|
| `items` → `line_items` | Create/Update リクエストのフィールド名変更 |
| `currency` 必須化 | create リクエストで必須フィールドに |
| `quantity` 移動 | Item → LineItem レベルへ |
| `full_name` 代替追加 | buyer name フィールドの柔軟化 |

#### 参考リンク

- [ACP Protocol](https://agenticcommerce.dev)

---

### ADP (Agent Data Protocol)

**現行バージョン**: 初期リリース

**管理**: CMU NeuLab

#### 主要な変更点

- **データセットサポート**:
    - SWE-Playground Trajectories
    - Toucan-1.5M
    - mini-coder trajectories
- **MCP 統合**: エージェントツーリング連携
- **マルチエージェント対応**: OpenHands, SWE-agent, AgentLab
- **Pydantic 型安全性**: スキーマ検証強化
- **TextObservation**: オプションの `name` フィールド追加

#### 参考リンク

- [ADP Protocol](https://github.com/neulab/agent-data-protocol)

---

### AG-UI (Agent-User Interaction Protocol)

**現行バージョン**: v0.0.43

#### 主要な変更点

- **Strands 統合**: `tool_stream_event` でステート出力
- **Go SDK**: core/types Message を使用したイベント対応
- **ADK ミドルウェア v0.4.2**: partial event の function calls をスキップ
- **コンテキストサポート**: `RunAgentInput.context` 実装
- **思考イベント変換**: 思考パーツを THINKING イベントに変換
- **セキュリティ修正**: Snyk による脆弱性4件修正
- **Android/Kotlin**: A2UI-4K 0.8.1、AGP 8.12.0

#### 新規 SDK

- **Dart SDK v0.1.0** (2026-01-21)
- **Go SDK** (コミュニティ)

#### 参考リンク

- [AG-UI Protocol](https://github.com/ag-ui-protocol/ag-ui)

---

### AgentSkills

**現行バージョン**: 初期リリース

**管理**: Anthropic

#### 概要

エージェント能力のオープンフォーマット。「一度書いて、どこでも使う」アプローチ。

#### 主要な変更点

- **採用カルーセル更新**: 新パートナー追加
    - Ona, Roo Code, Autohand Code, Piebald, Command Code
    - Databricks, Mistral Vibe, pi

#### 参考リンク

- [AgentSkills](https://agentskills.io)

---

### AP2 (Agent Payments Protocol)

**現行バージョン**: v0.1.0

**管理**: Google Agentic Commerce

#### 主要な変更点

- **X402 決済**: x402 payment method 統合
- **PaymentReceipt**: トランザクション確認オブジェクト
- **Go サンプル**: スタンドアロン Go 実装例
- **ADK サンプル**: Gemini 2.5 Flash 対応サンプル

#### パートナー

- Global Payments, Tether, Solana, OKX

#### 参考リンク

- [AP2 Protocol](https://github.com/google-agentic-commerce/AP2)

---

### MCP (Model Context Protocol)

**現行バージョン**: 2025-11-25 (日付ベースバージョニング)

#### 主要な変更点

- **Core Maintainer 更新**: ブログポスト (2026-01-22)
- **OpenID Connect Discovery 1.0**: 認可サーバー検出 (#797)
- **アイコンサポート**: ツール/リソース/プロンプトにアイコン (SEP-973)
- **増分スコープ同意**: WWW-Authenticate ヘッダー対応 (SEP-835)
- **URL モード Elicitation**: URL 入力モード (SEP-1036)
- **サンプリングでのツール呼び出し**: `tools`/`toolChoice` パラメータ (SEP-1577)
- **Tasks (実験的)**: 永続的リクエスト追跡 (SEP-1686)
- **SDK 階層システム**: 明確な要件付き (SEP-1730)

#### ガバナンス

- 継承・修正手続きの確立 (SEP-2085)

#### 参考リンク

- [MCP Specification](https://spec.modelcontextprotocol.io/)

---

### MCP-UI

**現行バージョン**: v5.2.0

#### 主要な変更点

- **React レンダラー**: MCP Apps 用 React レンダラー
- **汎用メッセージレスポンス**: Generic messages response サポート
- **プロキシオプション**: externalUrl 用 proxy オプション
- **Remote-DOM**: content type サポート
- **URI 統合**: `ui://` と `ui-app://` の統合

#### 破壊的変更

| バージョン | 変更 |
|-----------|------|
| v5.0.0 | `delivery` → `encoding`、`flavor` → `framework` |
| v4.0.0 | エクスポート名変更 |
| v3.0.0 | 非推奨クライアント API 削除 |

#### 参考リンク

- [MCP-UI](https://github.com/idosal/mcp-ui)

---

### OpenResponses

**概要**: マルチプロバイダー対応の相互運用可能な LLM インターフェース仕様

#### 主要な変更点

- **NVIDIA ロゴ追加**: コミュニティセクション
- **ドキュメント修正**: タイポ修正 (PR #4)

#### 参考リンク

- [OpenResponses](https://github.com/openrouter/openresponses)

---

### UCP (Universal Commerce Protocol)

**概要**: 商取引相互運用性のためのオープンスタンダード

#### 主要な変更点

- **ECP サポート**: Embedded Commerce Protocol、delegation confirmation 対応
- **Per-checkout transport configs**: チェックアウトごとのトランスポート設定
- **`context` フィールド追加**: currency は output-only に
- **AP2 mandate**: Checkout オブジェクトの拡張として

#### 破壊的変更

| 変更 | 影響 |
|------|------|
| Complete checkout schema 採用 (#100) | スキーマ全面改訂 |
| `_meta.ucp.profile` 非推奨 (#89) | 標準 metadata へ移行 |

#### 参考リンク

- [UCP Protocol](https://github.com/anthropics/UCP)

---

### x402 (Internet Native Payments)

**現行バージョン**: npm @x402/next@v2.2.0 / PyPI v1.0.0

#### 主要な変更点

- **`onProtectedRequest` フック**: seller middleware 用クライアントフック (#1010)
- **`onPaymentRequired` フック**: クライアントサイドフック (#1012)
- **CloudFront/Lambda 例**: x402 seller middleware 実装例 (#980)
- **Mintlify 移行**: ドキュメント基盤移行 (#925)
- **Python SDK v2**: 新規 Python SDK (#841)
- **Go 実装**: facilitator エラーを定数化 (#993)

#### 新規エコシステムパートナー

- SocioLogic, SlinkyLayer, 1Pay.ing, x402r
- BlockRun.AI, SolPay, Kobaru Facilitator

#### 参考リンク

- [x402 Protocol](https://github.com/x402-protocol/x402)

---

## Google Cloud / ADK

### ADK Python

**現行バージョン**: v1.23.0

#### 主要な変更点

- **自動セッション作成**: セッションが存在しない場合は自動作成
- **`thinking_config`**: `generate_content_config` でサポート
- **CLI オプション**: `--disable_features`/`--enable_features`
- **`otel_to_cloud` フラグ**: Agent Engine デプロイ用
- **MCP ツール認証**: 認証サポート追加
- **カスタムメトリクス**: `adk eval` CLI でサポート
- **A2UI メッセージ変換**: A2A `DataPart` と ADK イベント間

#### 破壊的変更

| 変更 | 影響 |
|------|------|
| OpenTelemetry for BigQuery | カスタム `ContextVar` から OpenTelemetry に変更 |

#### 参考リンク

- [ADK Python](https://github.com/google/adk-python)

---

### ADK Go

**現行バージョン**: latest

#### 主要な変更点

- **MCP 再接続修正**: EOF エラー時の再接続 (#505)
- **長時間オペレーション**: A2A input-required task として処理 (#499)
- **プラグインサポート**: launcher config でプラグイン対応 (#503)
- **Ping ヘルスチェック**: MCP セッション再接続 (#417)
- **VertexAI セッションサービス**: 新規追加 (#235)
- **FilterToolset ヘルパー**: ツールセットフィルタリング (#489)

#### 参考リンク

- [ADK Go](https://github.com/google/adk-go)

---

### ADK JS

**現行バージョン**: v0.2.4

#### 主要な変更点

- **Agent graph 生成修正**: ADK web クラッシュ修正
- **CommonJS TypeError 修正**: `cloneDeep` の TypeError 解消
- **Built-in code executor**: `supportCfc` 条件下での割り当て
- **Gemini 3 モデル**: BuiltInCodeExecutor でサポート

#### 参考リンク

- [ADK JS](https://github.com/google/adk-js)

---

### Agent Starter Pack

**現行バージョン**: v0.31.7

#### 主要な変更点

- **`upgrade` コマンド**: 新バージョンへのプロジェクト更新
- **Agent Identity サポート**: Agent Engine デプロイ用 IAM
- **`aiplatform.user` ロール**: agent identity IAM 権限

#### 参考リンク

- [Agent Starter Pack](https://github.com/GoogleCloudPlatform/agent-starter-pack)

---

### Cloud Run MCP

**現行バージョン**: v1.7.0

#### 主要な変更点

- **トークンベースクライアント**: token-based clients サポート
- **クライアント生成リファクタ**: 生成処理の改善
- **SubmitBuild API**: ビルド時間の改善
- **MCP SDK 更新**: 1.24.3 → 1.25.2

#### 参考リンク

- [Cloud Run MCP](https://github.com/GoogleCloudPlatform/cloud-run-mcp)

---

### gcloud-mcp

**現行バージョン**: v0.5.3

#### 主要な変更点

- **googleapis v170**: 依存関係更新
- **MCP SDK v1.25.2**: SDK 更新
- **Windows 互換性**: リファクタリング (#342)
- **フィルタリング精度**: 改善 (#320)
- **設定ファイル**: allow/deny リスト対応 (#236)

#### 参考リンク

- [gcloud-mcp](https://github.com/googleapis/gcloud-mcp)

---

### GKE MCP

**現行バージョン**: v0.8.0

#### 主要な変更点

- **Workload Scaling Skill**: GKE ワークロードスケーリング (#168)
- **`create_cluster` ツール**: クラスタ作成機能 (#144)
- **`gke-inference-quickstart`**: 推論クイックスタートスキル (#148)
- **gosec セキュリティ修正**: 脆弱性対応

#### 参考リンク

- [GKE MCP](https://github.com/googleapis/gke-mcp)

---

### Google Analytics MCP

**現行バージョン**: v0.1.1

#### 主要な変更点

- **`list_property_annotations`**: 新ツール追加
- **google-analytics-data v0.20.0**: 依存関係更新
- **google-analytics-admin v0.27.0**: 依存関係更新

#### 参考リンク

- [Google Analytics MCP](https://github.com/googleanalytics/google-analytics-mcp)

---

### MCP (Google Cloud)

#### 主要な変更点

- **Chrome DevTools サーバー**: 新規 MCP サーバー追加
- **Go 言語拡張**: Go サポート
- **ドキュメントバッジ**: Blog, Codelab, Screencast

#### 参考リンク

- [Google Cloud MCP](https://github.com/google/mcp)

---

### MCP Security

**現行バージョン**: secops-v0.5.2

#### 主要な変更点

- **Remote MCP サポート**: リモート MCP 対応 (#215)
- **MREP URLs**: staging サーバー置換
- **`list_cases` → `list_rules`**: メソッド名変更
- **Setup Skills 分離**: クライアント固有設定

#### 参考リンク

- [MCP Security](https://github.com/google/mcp-security)

---

### GenAI Toolbox

**現行バージョン**: v0.26.0

#### 主要な変更点

- **Snowflake サポート**: Source と Tools (#858)
- **MCP specs 2025-11-25**: 最新仕様対応 (#2303)
- **`valueFromParam`**: Tool config サポート (#2333)
- **`embeddingModel`**: MCP handler でサポート (#2310)
- **Cloud SQL backup/restore**: ツール追加 (#2141, #2171)
- **`user-agent-metadata` フラグ**: 新規追加 (#2302)

#### 破壊的変更

| 変更 | 影響 |
|------|------|
| Tool naming validation (#2305) | ツール名の検証強制化 |
| cloudgda パラメータ更新 (#2288) | 説明・パラメータ名変更 |

#### 参考リンク

- [GenAI Toolbox](https://github.com/googleapis/genai-toolbox)

---

## 注目ポイント

### 破壊的変更一覧

| 対象 | 変更内容 | 対応優先度 |
|------|---------|-----------|
| **A2A** | `extendedAgentCard` → `AgentCapabilities`、Well-Known URI 変更 | 高 |
| **ACP** | `items` → `line_items`、`currency` 必須化 | 高 |
| **MCP-UI** | `delivery` → `encoding`、`flavor` → `framework` | 中 |
| **UCP** | checkout schema 全面改訂、`_meta.ucp.profile` 非推奨 | 高 |
| **ADK Python** | OpenTelemetry for BigQuery（ContextVar 廃止） | 中 |
| **GenAI Toolbox** | Tool naming validation 強制化 | 中 |

### 新規追加プロトコル

1. **ACP** - Agentic Commerce Protocol (OpenAI & Stripe)
2. **ADP** - Agent Data Protocol (CMU NeuLab)
3. **AgentSkills** - エージェント能力オープンフォーマット (Anthropic)
4. **AP2** - Agent Payments Protocol (Google)
5. **MCP-UI** - MCP Apps 用 React レンダラー

### セキュリティ更新

- **AG-UI**: Snyk 脆弱性4件修正
- **GKE MCP**: gosec セキュリティ修正
- **MCP Security**: Remote MCP サポート（MREP URLs）
