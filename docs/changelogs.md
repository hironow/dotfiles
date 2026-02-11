# プロトコル変更ログ

最終更新: 2026-02-11

各プロトコル・Google Cloud サブモジュールの主要な変更点をまとめたドキュメント。

---

## プロトコル (Protocols)

### A2A (Agent-to-Agent)

**現行バージョン**: v1.0.0-rc (Release Candidate)
**前回タグ**: v0.3.0 (2025-07-30)

#### v1.0.0-rc の主要な変更点

- **ガバナンス文書化**: GOVERNANCE.md 追加、プロジェクトガバナンス体制の明文化
- **タイムスタンプ処理**: HTTP クエリパラメータでのタイムスタンプ処理を明確化
- **メッセージング・アーティファクト**: 処理仕様の明確化
- **非複雑ID構造**: リクエストのシンプルID移行（破壊的変更）
- **SDK後方互換性**: SDKレベルでの後方互換サポート追加
- **American Spelling**: "cancelled" → "canceled" 統一 (#1283)
- **Part構造簡素化**: FilePart/DataPart のフラット化
- **仕様ドキュメント改善**: Proto Table表示のライブラリ活用 (#1427)、MTLS スキーマ修正 (#1462)、ストリーミング例修正 (#1458)
- **v0.3.0→v1.0 変更ドキュメント**: 移行ガイド追加 (#1436)

#### v0.4.0 の主要な変更点

- **Task List Method**: `tasks/list` メソッドでページネーション付きタスク取得・フィルタリング (#831)
- **OAuth 2.0 近代化**: implicit/password フロー削除、device code/PKCE 追加 (#1303)

#### 破壊的変更（v0.3.0 → v1.0.0-rc）

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
**開発中**: v0.10

#### v0.9 の主要な変更点

- **Prompt First 設計**: 構造化出力優先からプロンプト埋め込み優先へ哲学変更
- **メッセージタイプ刷新**:
  - `beginRendering` → `createSurface`
  - `surfaceUpdate` → `updateComponents`
  - 新規: `updateDataModel`, `deleteSurface`
- **コンポーネント構造簡素化**: キーベースラッパーからフラット構造へ
- **モジュラースキーマ**: `common_types.json`, `server_to_client.json`, `standard_catalog.json` に分割
- **Theme プロパティ**: `styles` → `theme` にリネーム
- **統一カタログ**: コンポーネントと関数を単一カタログに統合

#### v0.10 開発中の変更点

- **v0.10 仕様フォーク**: v0.9 をベースにv0.10仕様の開発開始
- **名前付きパラメータ関数検証**: バリデーション追加
- **バージョンフィールド**: 仕様にバージョンフィールド追加
- **Client/Server リスト実装**: 双方向のリスト機能
- **Windows対応**: Window コマンド構文修正
- **新サンプル**: contact-lookup, orchestrator, rizzcharts
- **仕様 v0.8.2 更新**: multiselect でのフィルタリングと型サポート (#604)
- **正規表現サポート**: textfield コンポーネントの regex バリデーション (#605)
- **コンポーネントショーケース**: 標準カタログのコンポーネント一覧エージェント (#596)
- **gsutil 移行**: `gsutil` → `gcloud storage` コマンド移行 (#610)

#### 参考リンク

- [A2UI Specification](https://github.com/anthropics/A2UI)

---

### ACP (Agentic Commerce Protocol)

**現行バージョン**: 継続的デプロイ（バージョンタグなし）

**管理**: OpenAI & Stripe

#### 主要な変更点

- **Capability Negotiation**: エージェントとセラー間の機能ネゴシエーション
- **Payment Handlers Framework**: 構造化された支払いハンドラー（**破壊的変更**）
- **Extensions Framework**: オプション・コンポーザブルな拡張機能
- **Discount Extension**: リッチな割引コードサポート（初のACP拡張）
- **3DS 認証フロー**: 3D Secure 認証フローのサンプル追加 (#78)
- **バージョンミスマッチエラー**: `supported_versions` フィールド追加 (#99)
- **`intervention_required`**: MessageError タイプに追加 (#118)
- **認証プロバイダ指定**: マーチャントによる `authentication_provider` 指定 (#80)
- **B2B 小数数量**: 小数点付き数量サポート (#3)
- **PR バリデーター**: PR タイトル・説明のバリデーション自動化 (#126)

#### 破壊的変更

| 変更 | 影響 |
|------|------|
| Payment Handlers 導入 | 支払い方法IDから構造化ハンドラーへ移行必須 |
| `items` → `line_items` | Create/Update リクエストのフィールド名変更 |
| `currency` 必須化 | create リクエストで必須フィールドに |
| `channel` フィールド削除 (#85) | `AuthenticationMetadata` からの削除 |

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

**現行バージョン**: 継続的デプロイ（バージョンタグなし）

#### 主要な変更点

- **Kotlin SDK v0.2.7**: バージョン更新、macOS ランナーでの公開 (#1103)
- **Ruby SDK**: フルプロトコル実装 (#865)
- **マルチモーダル仕様**: multimodal spec 追加 (#1084)
- **NX 移行**: Turbo から NX へビルドシステム移行 (#1092)
- **tsdown ビルド**: ビルドツール更新 (#1071)
- **stream FastAPI 修正**: ストリーム再生成修正 (#1098)
- **ミドルウェアドキュメント改善**: ヘルパーガイダンス追加
- **Dart SDK v0.1.0**: フルプロトコル実装、SSEストリーミング、イベントハンドリング
- **ツール呼び出し重複排除**: 名前ベースから単一使用トラッキングへ (#1011)
- **フレームワーク統合**: LangGraph, Mastra, CrewAI 対応
- **状態管理**: JSON Patch デルタ (RFC 6902) サポート

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

- **Apache 2.0 ライセンス**: トップレベル LICENSE 追加 (#122)
- **採用カルーセル更新**: Qodo, VT Code, Ona, Autohand Code, Roo Code, Mistral Vibe, pi, Firebender, Piebald, Command Code, Databricks, Mux 追加
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

- Global Payments, Tether, Solana, OKX, Kite AI, Nexi

#### 参考リンク

- [AP2 Protocol](https://github.com/google-agentic-commerce/AP2)

---

### MCP (Model Context Protocol)

**現行バージョン**: 2025-11-25-RC

#### 主要な変更点

- **OpenID Connect Discovery 1.0**: 認可サーバーディスカバリー対応
- **アイコンサポート**: ツール、リソース、リソーステンプレート、プロンプトにアイコン追加
- **インクリメンタルスコープ同意**: `WWW-Authenticate` ヘッダー経由
- **ツール命名ガイダンス**: ツール名の規約追加
- **EnumSchema 拡張**: titled/untitled、single-select/multi-select enum 対応
- **URL Mode Elicitation** (SEP-1036): ブラウザ経由の安全なクレデンシャル収集
- **Sampling with Tools** (SEP-1577): サンプリングリクエストで `tools`/`toolChoice` パラメータ
- **OAuth Client ID Metadata Documents**: クライアント登録用
- **実験的タスク機能**: 持続的リクエストのポーリング付き状態追跡
- **OAuth Client Credentials** (SEP-1046): M2M 認可サポート
- **SDK 階層システム** (SEP-1730): 明確な要件付き
- **ガバナンス構造化**: Working Groups / Interest Groups フレームワーク
- **Extensions フレームワーク** (SEP-2133, Final): 拡張機能ケイパビリティのスキーマ追加、ドキュメント整備
- **MCP Apps サポート拡大**: Claude Desktop, MCPJam, Postman, VSCode, goose でのクライアントサポート
- **ガバナンス継承手続き** (SEP-2085, Final): ガバナンスの承継と修正手続き
- **SSRF セキュリティ**: SSRF 対策ドキュメント追加
- **MCP Apps CSP**: アンバンドルアセット向け Content Security Policy 要件文書化
- **Sampling ツールスコープ**: サンプリング `tools` がリクエストスコープであることを明確化
- **UI バンドル不要**: UI をシングルファイルにバンドルする必要がないことを明確化

#### マイナーアップデート

- Stderr ロギング明確化（stdio transport）
- Implementation インターフェースにオプション `description` フィールド
- HTTP 403 Forbidden（無効な Origins）の明確化
- SSE ストリームポーリングサポート
- JSON Schema 2020-12 をデフォルトダイアレクトに
- RFC 9728 OAuth 2.0 Protected Resource Metadata 準拠
- Elicitation のプリミティブ型デフォルト値サポート
- Schema Reference の index-property-only 型スタイル改善

#### 参考リンク

- [MCP Specification](https://spec.modelcontextprotocol.io/)

---

### MCP-UI

**現行バージョン**: v6.0.1 (2026-02-06)

#### 主要な変更点

- **MCP Apps 移行**: `mcp-ui` → `mcp apps` への完全リブランディング
- **MIME タイプ変更**: コンテンツタイプ仕様更新
- **Claude サポート追加**: サポートホストに Claude 追加
- **React レンダラー**: MCP Apps 用 React レンダラー (v5.18.0)
- **リンティング強制**: コード品質チェックの自動化 (#174)

#### 破壊的変更

| バージョン | 変更 |
|-----------|------|
| v6.0.0 | 廃止コンテンツタイプ削除、MIMEタイプ変更 |
| v5.0.0 | `delivery` → `encoding`、`flavor` → `framework` |

#### 参考リンク

- [MCP-UI](https://github.com/MCP-UI-Org/mcp-ui)

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

- **エンドースドパートナー追加**: Block, Fiserv, Klarna, Splitit
- **UCP-Agent ヘッダー**: openapi.json に追加
- **Cart Capability**: バスケット構築機能 (#73)
- **Context Intent フィールド**: intent フィールド追加、非識別制約明確化 (#95)
- **マルチ親スキーマ拡張**: 決定論的スキーマ解決 (#96)
- **UCP アノテーションスキーマ公開**: (#125)
- **uv 依存管理**: Python 依存管理を uv に移行 (#126)
- **2層エラーハンドリング**: UCP ネゴシエーション失敗の処理改善
- **Biome リンティング**: gitignore 対応
- **サービストランスポート定義**: 名前変更とバージョニング (#154)
- **Shopify TC 代表変更**: Lee Richmond → Aaron Glazer (#165)

#### 参考リンク

- [UCP Protocol](https://github.com/anthropics/UCP)

---

### x402 (Internet Native Payments)

**現行バージョン**: v1 / PyPI v1.0.0

#### 主要な変更点

- **MCP Go 統合**: x402 MCP サーバーの Go 実装 (#1132)
- **MCP Python SDK サブモジュール**: Python SDK への MCP 統合 (#1131)
- **MCP ペイメント選択修正**: MCP ラッパーでの支払い要件選択修正 (#1130)
- **Hedera HTS FT**: exact payment scheme 実装 (#792)
- **CloudFront Lambda Edge**: CDP ファシリテーター認証 (#1102)
- **MegaETH メインネット**: EVM サポート追加 (#1089)
- **payment-identifier 拡張**: ドキュメント追加 (#1097)
- **429 リトライロジック**: `HTTPFacilitatorClient.getSupported()` のレート制限対応 (#1094)
- **Go SDK エラーハンドリング刷新**: panic から適切なエラーハンドリングへリファクタ
- **Permit2 exact EVM**: Go SDK でのアップグレード
- **SIWX Extension**: Sign-In with X サポート
- **Solana スループット改善**: memo ベースのユニーク性による決済スループット向上
- **Permit2 サポート**: クライアント、ファシリテーター、リソースサーバーSDK (#1031, #1038, #1041)
- **Python SDK v2**: 新規 Python SDK (#841)
- **SDK Hooks**: `onPaymentRequired`, `onProtectedRequest` フック (#1003, #1010, #1012)

#### エコシステムパートナー

- Primer, Agently, ICPAY, SocioLogic, SlinkyLayer, 1Pay.ing
- BlockRun.AI, SolPay, Kobaru Facilitator
- auor.io, zauth, 0xmeta.ai
- AsterPay, dTelecom STT, Moltalyzer, x402lint, Foldset, clawdvine

#### 参考リンク

- [x402 Protocol](https://github.com/x402-protocol/x402)

---

## Google Cloud / ADK

### ADK Python

**現行バージョン**: v1.24.1 (2026-02-06)

#### v1.24.x の主要な変更点

- **Consolidated Event View**: Event タブ廃止、メッセージ行のクリック展開式に刷新
- **A2UI v0.8 統合**: ADK parts を標準カタログ準拠の UI コンポーネントとして自動レンダリング
- **キーボードナビゲーション**: 矢印キーによるアクセシビリティ向上
- **関数呼び出しツールチップ**: 引数・レスポンス・状態変更の詳細表示
- **エージェントオプティマイザ**: 最適化インターフェースの追加
- **ツールセット認証**: `McpToolset`, `OpenAPIToolset` 等で認証サポート (#798f65d)
- **McpToolset リソースアクセス**: MCP リソースへのユーザーアクセスメソッド追加
- **OpenAPI ツール非同期化**: `RestApiTool` の非同期対応
- **ライブモードスレッド分離**: ツール実行を別スレッドで実行可能に

#### 未リリースの変更点

- **外部アクセストークン**: Google credentials で外部渡しアクセストークンサポート
- **`auto_create_session` フラグ**: `adk api_server` CLI 用
- **`/health` / `/version` エンドポイント**: ADK Web サーバー用
- **イベントデルタメモリ**: `add_events_to_memory` ファサード追加
- **トークン閾値コンパクション**: 呼び出し後のイベント保持付きコンパクション
- **ストリーミングレスポンス**: grounding/citation メタデータの伝搬修正

#### v1.23.0 の主要な変更点

- **自動セッション作成**: セッションが存在しない場合は自動作成
- **`thinking_config`**: `generate_content_config` でサポート
- **CLI オプション**: `--disable_features`/`--enable_features`
- **MCP ツール認証**: 認証サポート追加
- **カスタムメトリクス**: `adk eval` CLI で `CustomMetricEvaluator` サポート
- **A2UI メッセージ変換**: A2A `DataPart` と ADK イベント間変換
- **AgentEngineSandboxCodeExecutor**: `@experimental` 削除、安定版に
- **JSON スキーマサポート**: ツール宣言で複数ツールタイプ対応
- **`otel_to_cloud` フラグ**: `adk deploy agent_engine` コマンド用

#### 破壊的変更

| 変更 | 影響 |
|------|------|
| credential manager が `tool_context` を受け取るよう変更 (v1.24.0) | `callback_context` から `tool_context` への引数変更 |
| OpenTelemetry for BigQuery (v1.23.0) | カスタム `ContextVar` から OpenTelemetry に変更 |

#### 参考リンク

- [ADK Python](https://github.com/google/adk-python)

---

### ADK Go

**現行バージョン**: v0.4.0 (2026-01-30)

#### v0.4.0 の主要な変更点

- **`WithContext` メソッド**: `agent.InvocationContext` でコンテキスト変更 (#526)
- **Human-in-the-Loop 確認**: MCP ツールセットでの確認メカニズム (#523)
- **Load Memory ツール**: メモリ検索ツール追加 (#497)
- **セッションイベントアクセス**: executor コールバックからセッションイベント取得 (#521)
- **カスタムパートコンバーター**: ADK Executor 対応 (#512)
- **プラグインシステム強化**: launcher config でプラグイン対応
- **FilterToolset ヘルパー**: ツールセットフィルタリング
- **OpenTelemetry 改善**: `gen_ai.conversation.id` を OTEL スパンに含める

#### 未リリースの変更点

- **OpenTelemetry TracerProvider**: OTEL 設定と初期化 (#524)
- **Function Call Modifier プラグイン**: 関数呼び出し変更プラグイン (#535)
- **Preload Memory ツール**: メモリプリロードサポート (#527)
- **Logging プラグイン**: ロギングプラグイン追加 (#534)
- **コンソールリファクタ**: コンソール UI 改善 (#533)
- **テレメトリ移行**: 旧テレメトリからの移行 (#529)

#### バグ修正

- `long_running_function_ids` のイベント生成時の受け渡し修正 (#553)
- リモートエージェントの部分レスポンスによるデータ重複修正 (#545)
- `RequestConfirmation` で `SkipSummarization` 設定しエージェントループ停止 (#544)
- InvocationId の重複時置換修正 (#525)
- MCP EOF エラー時の再接続修正 (#505)
- temp state デルタのローカルセッション適用修正 (#537)

#### 参考リンク

- [ADK Go](https://github.com/google/adk-go)

---

### ADK JS

**現行バージョン**: v0.3.0 (2026-01-30)

#### v0.3.0 の主要な変更点

- **OpenTelemetry サポート**: Web サーバーでの観測性/テレメトリ
- **Zod v3/v4 互換性**: 両バージョンサポート
- **カスタムロガー**: `setLogger()` 関数追加
- **MCP ヘッダーオプション**: Session manager の headers オプション（レガシー `header` は非推奨）
- **コードエグゼキューター**: LlmAgent でのコード実行統合
- **Gemini 3 モデルサポート**: BuiltInCodeExecutor 対応
- **Husky プリコミット**: ESLint/Prettier 統合、API キー露出防止

#### 未リリースの変更点

- **ESM ネイティブ CLI**: CommonJS から ESM への移行 (#113)
- **セッションサービスレジストリ**: CLI 連携 (#126)
- **CLI version コマンド**: バージョン表示機能 (#115)
- **state/stateデルタ対応**: API サーバーのリクエストボディパラメータ (#117)
- **`instanceof` 置換**: `isBaseTool`/`isLlmAgent` ヘルパー使用 (#116)
- **MCP SDK v1.26.0**: バンプ (#112)
- **インテグレーションテスト**: テストインフラ整備 (#100)

#### 参考リンク

- [ADK JS](https://github.com/google/adk-js)

---

### Agent Starter Pack

**現行バージョン**: v0.35.1

#### v0.35.x の主要な変更点

- **TypeScript ADK テンプレート**: `adk_ts` テンプレート追加 (#731)
- **エージェント選択 UI 改善**: More Options サブメニューによる構造化 (#766)
- **none デプロイメントターゲット**: デプロイなしオプション追加
- **deploy/backend ターゲット除外**: deployment_target=none 時の Makefile 修正 (#773)

#### v0.34.0 の主要な変更点

- **GEMINI.md 言語別**: 言語ごとの GEMINI.md 生成
- **eval evalsets**: 評価データセットサポート
- **CI/CD ランナー修正**: `--auto-approve` 時の `cicd_runner` デフォルト値修正 (#770)

#### v0.33.x の主要な変更点

- **Java ADK テンプレート**: `adk_java` テンプレート追加 (v0.33.0)
- **Auto-approve / CLI オーバーライド改善**: enhance コマンドの修正 (#745)
- **Spring Boot Starter**: Java 25 互換性テストバージョン修正 (#753)

#### 参考リンク

- [Agent Starter Pack](https://github.com/GoogleCloudPlatform/agent-starter-pack)

---

### Cloud Run MCP

**現行バージョン**: v1.8.0 (2026-01-27)

#### 主要な変更点

- **OAuth サポート**: OAuth 認証統合 (#214)
- **OAuth URL サポート**: OAuth 関連の GET URL 追加
- **トークンベースクライアント**: token-based clients サポート (#206)
- **SubmitBuild API**: デプロイ/ビルド時間の改善 (#198)
- **クライアント生成リファクタ**: 生成処理の改善 (#201)

#### セキュリティ修正

- hono パッケージの脆弱性修正 (#215)
- lodash 4.17.23 へアップグレード (#209)

#### 参考リンク

- [Cloud Run MCP](https://github.com/GoogleCloudPlatform/cloud-run-mcp)

---

### gcloud-mcp

**現行バージョン**: gcloud-mcp-v0.5.3

#### 主要な変更点

- **googleapis v171**: 依存関係更新
- **MCP SDK v1.26.0**: SDK 更新
- **observability-mcp v0.2.3**: オブザーバビリティコンポーネント更新
- **storage-mcp v0.3.2**: ストレージコンポーネント更新
- **Windows 互換性**: リファクタリング (#342)
- **フィルタリング精度**: 改善 (#320)
- **設定ファイル**: allow/deny リスト対応 (#236)

#### 参考リンク

- [gcloud-mcp](https://github.com/googleapis/gcloud-mcp)

---

### GKE MCP

**現行バージョン**: v0.9.0

#### v0.9.0 の主要な変更点

- **GKE Workload Security スキル**: ワークロードセキュリティ管理 (#172)
- **クラスタ作成ベストプラクティス**: ドキュメント追加 (#177)
- **Go 依存関係更新**: Go 1.25.6 へ更新 (#176)

#### v0.8.0 の主要な変更点

- **ComputeClasses スキル**: ComputeClasses 作成スキル (#175)
- **GIQ V1 更新**: GIQ ツール指示を V1 gcloud コマンドに更新 (#174)
- **GKE Workload Scaling スキル**: ワークロードスケーリング (#168)
- **create_cluster ツール**: GKE クラスタ作成機能とスキル (#144)
- **GKE Inference Quickstart Skill**: AI/ML 推論ワークロード最適化 (#148)
- **gosec セキュリティ修正**: 脆弱性対応 (#167)
- **golangci-lint 統合**: CI統合でのコード品質リンティング (#151)
- **セキュリティポリシー**: SECURITY.md 追加 (#149)

#### 参考リンク

- [GKE MCP](https://github.com/googleapis/gke-mcp)

---

### Google Analytics MCP

**現行バージョン**: v0.1.1

#### 主要な変更点

- **`list_property_annotations`**: 新ツール追加
- **`run_report` 日付範囲スキーマ修正**: Codex CLI での失敗修正 (#67)
- **google-analytics-data v0.20.0**: 依存関係更新
- **google-analytics-admin v0.27.0**: 依存関係更新

#### 未リリースの破壊的変更

| 変更 | 影響 |
|------|------|
| パッケージ名を `analytics-mcp` にリネーム (#44) | インストールコマンドの変更が必要 |

#### 参考リンク

- [Google Analytics MCP](https://github.com/googleanalytics/google-analytics-mcp)

---

### MCP (Google Cloud)

#### 主要な変更点

- **Cloud Data MCP サンプル**: DK と Cloud SQL リモート MCP のラボ追加
- **Chrome DevTools サーバー**: 新規 MCP サーバー追加
- **Go 言語拡張**: Go サポート
- **README 強化**: バッジとデモ詳細の追加

#### 参考リンク

- [Google Cloud MCP](https://github.com/google/mcp)

---

### MCP Security

**現行バージョン**: secops-v0.5.2

#### 主要な変更点

- **キュレーテッドルール管理ツール**: Chronicle 検出ルールの管理ツール追加、ページネーションガイダンス
- **Gemini CLI 拡張**: google-secops Gemini CLI extension、スキルとドキュメント追加
- **スキル再構成**: runbook をスキルにインライン化、setup スキルをクライアント別に分離
- **Adaptive Execution ドキュメント**: 追加
- **gsutil 移行**: `gsutil` → `gcloud storage` コマンド移行
- **Remote MCP サポート**: リモート MCP 対応 (#215)
- **MREP URLs**: staging サーバー置換
- **`list_cases` → `list_rules`**: メソッド名変更

#### 参考リンク

- [MCP Security](https://github.com/google/mcp-security)

---

### GenAI Toolbox

**現行バージョン**: v0.26.0 (2026-01-22)

#### 主要な変更点

- **User-Agent Metadata フラグ**: 新規追加 (#2302)
- **MCP レジストリフラグ**: MCP registry サポート
- **MCP specs 2025-11-25**: 最新仕様対応 (#2303)
- **`valueFromParam`**: Tool config サポート (#2333)
- **`embeddingModel`**: MCP handler でサポート (#2310)
- **BigQuery 設定可能化**: 最大行数設定 (#2262)
- **Cloud SQL**: backup/restore/clone ツール追加 (#2141, #2171, #1845)
- **Snowflake 統合**: ソースとツール統合 (#858)
- **PostgreSQL**: stats, roles, replication 等の新ツール
- **Looker**: OAuth 対応強化、Validate Project ツール (#2430)
- **Oracle OCI/Wallet**: サポート
- **MariaDB ソース**: 統合追加
- **Spanner**: list graphs サポート
- **Serverless Spark**: `create_spark_batch`/`create_pyspark_batch` ツール
- **複数 prebuilt 設定結合**: サポート (#2295)

#### 未リリースの変更点

- **設定ファイル v2**: 設定ファイルフォーマットの v2 更新（**破壊的変更**） (#2369)
- **CLI 直接ツール呼び出し**: CLI からのツール直接実行サポート (#2353)
- **Agent Skills 生成**: ツールセットからのエージェントスキル自動生成 (#2392)
- **Tool インターフェース変更**: `ParseParams()` 削除、`GetParameters()` 追加 (#2374, #2375)
- **AlloyDB Omni データプレーンツール**: 新規追加 (#2340)
- **Cloud Logging Admin**: ソース・ツール・ドキュメント追加 (#2137)
- **マネージドコネクションプーリング**: ドキュメント追加 (#2425)
- **LangChain 前後処理ドキュメント**: Python 向けドキュメント (#2378)

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
| **A2A** | v1.0.0-rc: 非複雑ID構造、OAuth、Enum、Part簡素化等 | 高 |
| **ACP** | Payment Handlers Framework 導入、`channel` フィールド削除 | 高 |
| **MCP-UI** | v6.0.0 で MCP Apps へ移行、MIME タイプ変更 | 高 |
| **ADK Python** | v1.24.0: credential manager 引数変更 (`callback_context` → `tool_context`) | 高 |
| **AG-UI** | ADK Middleware で AG-UI tools 自動追加廃止 | 中 |
| **ADK Python** | v1.23.0: OpenTelemetry for BigQuery（ContextVar 廃止） | 中 |
| **GenAI Toolbox** | Tool naming validation 強制化 | 中 |
| **GenAI Toolbox** (未リリース) | 設定ファイル v2、Tool インターフェース変更 | 中 |
| **Google Analytics MCP** (未リリース) | パッケージ名 `analytics-mcp` にリネーム | 低 |

### メジャーアップデート

1. **ADK Python v1.24.1** - A2UI v0.8 統合、ツールセット認証、Consolidated Event View
2. **Agent Starter Pack v0.35.1** - TypeScript ADK テンプレート追加、エージェント選択 UI 改善
3. **GKE MCP v0.9.0** - Workload Security スキル追加
4. **A2A v1.0.0-rc** - 仕様ドキュメント改善、v0.3.0→v1.0 移行ガイド
5. **AG-UI** - Kotlin SDK v0.2.7、Ruby SDK 追加、マルチモーダル仕様
6. **x402** - MCP Go/Python 統合拡大、Hedera HTS・MegaETH 対応
7. **MCP** - SSRF セキュリティ文書、MCP Apps CSP 要件追加

### セキュリティ更新

- **MCP**: SSRF 対策ドキュメント追加
- **Cloud Run MCP**: hono パッケージ脆弱性修正
- **GKE MCP**: Workload Security スキル追加
- **MCP Security**: キュレーテッドルール管理ツール、gsutil 移行
- **ADK Python**: URI 内センシティブ情報のログ出力リダクション、クレデンシャルキー生成の安定化
