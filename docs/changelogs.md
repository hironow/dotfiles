# プロトコル変更ログ

最終更新: 2026-02-02

各プロトコル・Google Cloud サブモジュールの主要な変更点をまとめたドキュメント。

---

## プロトコル (Protocols)

### A2A (Agent-to-Agent)

**現行バージョン**: v0.4.0 (開発中、未タグ)
**最新タグ**: v0.3.0 (2025-07-30)

#### v0.4.0 の主要な変更点（開発中）

- **Task List Method**: `tasks/list` メソッドでページネーション付きタスク取得・フィルタリング (#831)
- **OAuth 2.0 近代化**: implicit/password フロー削除、device code/PKCE 追加 (#1303)
- **シンプルID構造**: 複雑なID構造からシンプルIDへ移行 (#1389)
- **American Spelling**: "cancelled" → "canceled" 統一 (#1283)
- **Part構造簡素化**: FilePart/DataPart のフラット化 (#1411)

#### 破壊的変更（v0.3.0 → v0.4.0）

| 変更 | 影響 |
|------|------|
| `extendedAgentCard` → `AgentCapabilities` に移動 (#1307) | Agent Card 構造の変更 |
| Well-Known URI: `agent.json` → `agent-card.json` (#841) | エンドポイント URL の変更 |
| 非複雑ID構造への移行 (#1389) | リクエストID形式の変更 |
| OAuth implicit/password フロー削除 (#1303) | 認証フロー変更 |
| Enum フォーマットをADR-001に準拠 (#1384) | ProtoJSON仕様変更 |
| `supportsAuthenticatedExtendedCard` → `supportsExtendedAgentCard` (#1222) | フィールド名変更 |

#### 参考リンク

- [A2A Specification](https://github.com/a2aproject/A2A)

---

### A2UI (Agent-to-User Interface)

**現行バージョン**: v0.9 (2026-01-21)

#### 主要な変更点

- **Prompt First 設計**: 構造化出力優先からプロンプト埋め込み優先へ哲学変更
- **メッセージタイプ刷新**:
  - `beginRendering` → `createSurface`
  - `surfaceUpdate` → `updateComponents`
  - 新規: `updateDataModel`, `deleteSurface`
- **コンポーネント構造簡素化**: キーベースラッパーからフラット構造へ
- **モジュラースキーマ**: `common_types.json`, `server_to_client.json`, `standard_catalog.json` に分割
- **Theme プロパティ**: `styles` → `theme` にリネーム
- **統一カタログ**: コンポーネントと関数を単一カタログに統合

#### 参考リンク

- [A2UI Specification](https://github.com/anthropics/A2UI)

---

### ACP (Agentic Commerce Protocol)

**現行バージョン**: 2026-01-30

**管理**: OpenAI & Stripe

#### 主要な変更点

- **Capability Negotiation**: エージェントとセラー間の機能ネゴシエーション
- **Payment Handlers Framework**: 構造化された支払いハンドラー（**破壊的変更**）
- **Extensions Framework**: オプション・コンポーザブルな拡張機能
- **Discount Extension**: リッチな割引コードサポート（初のACP拡張）

#### 破壊的変更

| 変更 | 影響 |
|------|------|
| Payment Handlers 導入 | 支払い方法IDから構造化ハンドラーへ移行必須 |
| `items` → `line_items` | Create/Update リクエストのフィールド名変更 |
| `currency` 必須化 | create リクエストで必須フィールドに |

#### 参考リンク

- [ACP Protocol](https://agenticcommerce.dev)

---

### ADP (Agent Data Protocol)

**現行バージョン**: 初期リリース

**管理**: CMU NeuLab

#### 主要な変更点

- **データセットサポート**: SWE-Playground Trajectories, Toucan-1.5M, mini-coder trajectories
- **MCP 統合**: エージェントツーリング連携
- **マルチエージェント対応**: OpenHands, SWE-agent, AgentLab
- **Pydantic 型安全性**: スキーマ検証強化

#### 参考リンク

- [ADP Protocol](https://github.com/neulab/agent-data-protocol)

---

### AG-UI (Agent-User Interaction Protocol)

**現行バージョン**: v0.0.43

#### 主要な変更点

- **ツール呼び出し重複排除**: 名前ベースから単一使用トラッキングへ (#1011)
- **LRO修正**: 再開可能エージェントの長時間操作修正
- **OpenResponses統合**: HFルーター、SSE/思考イベント、provider アーキテクチャ
- **HITL改善**: 再開可能エージェントパターン強化
- **Python 3.14サポート**: 新バージョン対応

#### ADK Middleware (0.4.2) 未リリース変更

- **破壊的**: AG-UI client tools が root agent toolset に自動追加されなくなる
- `RunAgentInput.context` ネイティブサポート
- Gemini 思考サマリーを THINKING イベントに変換

#### 参考リンク

- [AG-UI Protocol](https://github.com/ag-ui-protocol/ag-ui)

---

### AgentSkills

**現行バージョン**: 継続的デプロイ（バージョンタグなし）

**管理**: Anthropic

#### 主要な変更点

- **採用カルーセル大幅更新**: 15+ 新ロゴ追加
  - VT Code, Ona, Autohand Code, Roo Code, Mistral Vibe
  - pi, Firebender, Piebald, Command Code, Databricks
  - Mux, Agentman, TRAE, Spring AI
- **Windows インストール手順**: 追加
- **モバイル対応ドキュメント**: レスポンシブ改善

#### 参考リンク

- [AgentSkills](https://agentskills.io)

---

### AP2 (Agent Payments Protocol)

**現行バージョン**: v0.1.0 (2025-09-16)

**管理**: Google Agentic Commerce

#### 主要な変更点

- **PaymentReceipt**: トランザクション確認オブジェクト実装
- **X402 決済**: x402 payment method 統合（Python サンプル）
- **Go サンプル**: スタンドアロン Go 実装例
- **UCP 統合ドキュメント**: Universal Commerce Protocol 連携

#### パートナー

- Global Payments, Tether, Solana, OKX

#### 参考リンク

- [AP2 Protocol](https://github.com/google-agentic-commerce/AP2)

---

### MCP (Model Context Protocol)

**現行バージョン**: 2025-11-25 (1周年記念リリース)

#### 主要な変更点

- **Task-based Workflows** (SEP-1686): 実験的機能、状態追跡（working, input_required, completed等）
- **簡素化認可フロー** (SEP-991): URL ベースクライアント登録、DCR プロキシ不要に
- **Extensions Framework**: オプション・アディティブ・コンポーザブルな拡張
- **URL Mode Elicitation** (SEP-1036): ブラウザ経由の安全なクレデンシャル収集
- **Sampling with Tools** (SEP-1577): サンプリングリクエストでツール呼び出し
- **OAuth Client Credentials** (SEP-1046): M2M 認可サポート
- **SDK 階層システム** (SEP-1730): 明確な要件付き

#### 統計

- 58 メンテナー、2,900+ コントリビューター
- 2,000+ MCP サーバー登録
- 毎週 100+ 新コントリビューター

#### 参考リンク

- [MCP Specification](https://spec.modelcontextprotocol.io/)

---

### MCP-UI

**現行バージョン**: v6.0.0 (2026-01-26)

#### 主要な変更点

- **MCP Apps 移行**: `mcp-ui` → `mcp apps` への完全リブランディング
- **MIME タイプ変更**: コンテンツタイプ仕様更新
- **Claude サポート追加**: サポートホストに Claude 追加
- **React レンダラー**: MCP Apps 用 React レンダラー (v5.18.0)

#### 破壊的変更

| バージョン | 変更 |
|-----------|------|
| v6.0.0 | 廃止コンテンツタイプ削除、MIMEタイプ変更 |
| v5.0.0 | `delivery` → `encoding`、`flavor` → `framework` |

#### 参考リンク

- [MCP-UI](https://github.com/idosal/mcp-ui)

---

### OpenResponses

**現行バージョン**: v0.1.0 (プレリリース)

#### 主要な変更点

- **API命名修正**: `Createresponse` → `createResponse` (PR #40)
- **CLI コンプライアンステスト**: `bin/compliance-test.ts` 追加
- **llms.txt リファクタ**: コアコンセプト、API詳細、イベントフォーマット強化
- **Bun 移行**: Node から Bun へパッケージマネージャー変更

#### 参考リンク

- [OpenResponses](https://github.com/openrouter/openresponses)

---

### UCP (Universal Commerce Protocol)

**現行バージョン**: v2026-01-23

#### 主要な変更点

- **Cart Capability**: バスケット構築機能 (#73)
- **Context Intent フィールド**: intent フィールド追加、非識別制約明確化 (#95)
- **マルチ親スキーマ拡張**: 決定論的スキーマ解決 (#96)
- **UCP アノテーションスキーマ公開**: (#125)
- **uv 依存管理**: Python 依存管理を uv に移行 (#126)

#### 参考リンク

- [UCP Protocol](https://github.com/anthropics/UCP)

---

### x402 (Internet Native Payments)

**現行バージョン**: npm @x402/core@v2.1.0 / PyPI v1.0.0

#### 主要な変更点

- **Permit2 サポート**: クライアント、ファシリテーター、リソースサーバーSDK (#1031, #1038, #1041)
- **Python SDK v2**: 新規 Python SDK (#841)
- **Bazaar Extension**: 動的インポートと事前登録サポート (#956, #982)
- **Stellar/Algorand スキーム**: 新ネットワーク対応 (#941, #361)
- **SDK Hooks**: `onPaymentRequired`, `onProtectedRequest` フック (#1003, #1010, #1012)
- **MCP 統合**: x402MCPClient/Server、ミドルウェア、サンプル追加

#### 新規エコシステムパートナー

- Primer, Agently, ICPAY, SocioLogic, SlinkyLayer, 1Pay.ing
- BlockRun.AI, SolPay, Kobaru Facilitator

#### 参考リンク

- [x402 Protocol](https://github.com/x402-protocol/x402)

---

## Google Cloud / ADK

### ADK Python

**現行バージョン**: v1.23.0 (2026-01-22)

#### 主要な変更点

- **自動セッション作成**: セッションが存在しない場合は自動作成
- **`thinking_config`**: `generate_content_config` でサポート
- **CLI オプション**: `--disable_features`/`--enable_features`
- **MCP ツール認証**: 認証サポート追加
- **カスタムメトリクス**: `adk eval` CLI で `CustomMetricEvaluator` サポート
- **A2UI メッセージ変換**: A2A `DataPart` と ADK イベント間変換
- **AgentEngineSandboxCodeExecutor**: `@experimental` 削除、安定版に

#### 破壊的変更

| 変更 | 影響 |
|------|------|
| OpenTelemetry for BigQuery | カスタム `ContextVar` から OpenTelemetry に変更 |

#### 参考リンク

- [ADK Python](https://github.com/google/adk-python)

---

### ADK Go

**現行バージョン**: v0.4.0 (2026-01-30)

#### 主要な変更点

- **セッションイベントアクセス**: executor コールバックからセッションイベント取得
- **Human-in-the-Loop 確認**: エージェントループの確認メカニズム
- **プラグインシステム強化**: launcher config でプラグイン対応
- **FilterToolset ヘルパー**: ツールセットフィルタリング
- **OpenTelemetry 改善**: `gen_ai.conversation.id` を OTEL スパンに含める

#### バグ修正 (14件)

- MCP EOF エラー時の再接続修正
- 長時間オペレーションを A2A input-required タスクとして処理
- ストリーミングモードパラメータ修正
- 複数ツール呼び出し時の状態変更修正
- Web サーバーのグレースフルシャットダウン

#### 参考リンク

- [ADK Go](https://github.com/google/adk-go)

---

### ADK JS

**現行バージョン**: v0.3.0 (2026-01-30)

#### 主要な変更点

- **OpenTelemetry サポート**: Web サーバーでの観測性/テレメトリ
- **Zod v3/v4 互換性**: 両バージョンサポート
- **カスタムロガー**: `setLogger()` 関数追加
- **MCP ヘッダーオプション**: Session manager の headers オプション
- **Husky プリコミット**: ESLint/Prettier 統合

#### バグ修正

- ストリーミング処理修正
- rootAgent getter 修正（Python SDK と動作統一）

#### 参考リンク

- [ADK JS](https://github.com/google/adk-js)

---

### Agent Starter Pack

**現行バージョン**: v0.32.0

#### 主要な変更点

- **display_name サポート**: langgraph を custom_a2a にリブランド (#737)
- **upgrade コマンド**: 新バージョンへのプロジェクト更新 (#719)
- **Go サポート**: upgrade コマンドで Go 対応 (#730)
- **--set-secrets オプション**: deploy コマンドに追加 (#734)
- **Agent Identity 修正**: display_name 渡し修正 (#739)
- **aiplatform.user ロール**: agent identity IAM 権限修正 (#727)

#### 参考リンク

- [Agent Starter Pack](https://github.com/GoogleCloudPlatform/agent-starter-pack)

---

### Cloud Run MCP

**現行バージョン**: v1.8.0 (2026-01-27)

#### 主要な変更点

- **OAuth URL サポート**: OAuth 関連の GET URL 追加
- **トークンベースクライアント**: token-based clients サポート (#206)
- **SubmitBuild API**: デプロイ/ビルド時間の改善 (#198)
- **クライアント生成リファクタ**: 生成処理の改善 (#201)
- **セキュリティ修正**: lodash 4.17.23 へアップグレード (#209)

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

**現行バージョン**: v0.8.0 (2026-01-20)

#### 主要な変更点

- **create_cluster ツール**: GKE クラスタ作成機能
- **GKE Inference Quickstart Skill**: AI/ML 推論ワークロード最適化
- **自動バージョンタグ**: CI/CD 改善
- **gosec セキュリティ修正**: 脆弱性対応
- **golangci-lint 統合**: コード品質リンティング
- **Dependabot 設定**: 自動依存関係更新

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

**現行バージョン**: v0.26.0 (2026-01-22)

#### 主要な変更点

- **User-Agent Metadata フラグ**: 新規追加 (#2302)
- **MCP specs 2025-11-25**: 最新仕様対応 (#2303)
- **`valueFromParam`**: Tool config サポート (#2333)
- **`embeddingModel`**: MCP handler でサポート (#2310)
- **BigQuery 設定可能化**: 最大行数設定 (#2262)
- **Cloud SQL backup/restore**: ツール追加

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
| **A2A** | 10+ 破壊的変更（v0.4.0開発中）: ID構造、OAuth、Enum等 | 高 |
| **ACP** | Payment Handlers Framework 導入 | 高 |
| **MCP-UI** | v6.0.0 で MCP Apps へ移行、MIME タイプ変更 | 高 |
| **AG-UI** | ADK Middleware で AG-UI tools 自動追加廃止 | 中 |
| **ADK Python** | OpenTelemetry for BigQuery（ContextVar 廃止） | 中 |
| **GenAI Toolbox** | Tool naming validation 強制化 | 中 |

### メジャーアップデート

1. **A2A v0.4.0** - 10+ 破壊的変更を含む大規模更新（開発中）
2. **MCP-UI v6.0.0** - MCP Apps へのリブランディング
3. **ADK Go v0.4.0** - プラグインシステム、14件のバグ修正
4. **ADK JS v0.3.0** - OpenTelemetry、Zod v3/v4 対応
5. **ACP 2026-01-30** - Payment Handlers、Extensions Framework

### セキュリティ更新

- **AG-UI**: aiohttp, urllib3, authlib, pyasn1, mcp, fastapi, starlette の脆弱性修正
- **GKE MCP**: gosec セキュリティ修正
- **Cloud Run MCP**: lodash 4.17.23 へアップグレード
- **MCP Security**: Remote MCP サポート（MREP URLs）
