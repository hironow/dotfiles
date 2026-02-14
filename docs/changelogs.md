# プロトコル変更ログ

最終更新: 2026-02-14

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
- **DeepLearning.AI コース**: README とドキュメントにコースリンク追加 (#1469)

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

#### 未リリースの変更点

- **スキーマパッケージング**: スキーマのパッケージングとランタイムローディング実装 (#555)
- **A2UI Validator**: ロードされたサンプルの検証機能 (#557)
- **Theme バリデーション**: カタログスキーマ参照によるテーマバリデーションリファクタ (#621)
- **TypeScript `declare` キーワード**: エクスポートインターフェースへの `declare` 追加 (#617, #616)
- **CODEOWNERS ファイル**: コードオーナーシップ定義 (#618)
- **Python バリデーション関数**: 基本的なバリデーション関数追加 (#624)

#### 参考リンク

- [A2UI Specification](https://github.com/anthropics/A2UI)

---

### ACP (Agentic Commerce Protocol)

**現行バージョン**: API Version 2026-01-30

**管理**: OpenAI & Stripe

#### v2026-01-30 の主要な変更点

- **Capability Negotiation**: エージェントとセラー間の機能ネゴシエーション
- **Payment Handlers Framework**: 構造化された支払いハンドラー（**破壊的変更**）
- **Extensions Framework**: オプション・コンポーザブルな拡張機能
- **Discount Extension**: リッチな割引コードサポート（初のACP拡張）

#### SEP（仕様拡張提案）進行中

- **Mandatory Idempotency Requirements**: 冪等性の要件と保証 (#121)
- **Post-Purchase Lifecycle Tracking**: リッチな購入後ライフサイクル追跡 (#106)
- **Seller-Backed Payment**: セラー独自決済方式サポート (#114)
- **Payment Handler Display Order**: マーチャント推奨順序 (#133)

#### v2026-01-16 の変更点

- **認証プロバイダ指定**: マーチャントによる `authentication_provider` 指定 (#80)
- **`merchant_id` 必須化**: `PaymentProvider` に必須フィールド追加
- **Adyen プロバイダ**: provider enum に追加

#### 破壊的変更

| 変更 | 影響 |
|------|------|
| Payment Handlers 導入 (v2026-01-30) | 支払い方法IDから構造化ハンドラーへ移行必須 |
| `items` → `line_items` | Create/Update リクエストのフィールド名変更 |
| `currency` 必須化 | create リクエストで必須フィールドに |
| `channel` フィールド削除 (#85) | `AuthenticationMetadata` からの削除 |
| `fulfillment_address` → `fulfillment_details` (v2025-12-12) | ネスト構造への変更 |
| `fulfillment_option_id` → `selected_fulfillment_options[]` (v2025-12-12) | 配列形式への変更 |

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

- **Gemini 3+ ストリーミング関数呼び出し**: ADK Middleware でのストリーミング関数呼び出し引数サポート (#1117)
- **Reasoning Spec**: 推論仕様追加 (#1050)
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
- **Memgraph Lab**: サポート機能リストに追加 (#2241)
- **DCR/CIMD フィルター**: Example Clients フィルタリング (#2079)

#### マイナーアップデート

- Stderr ロギング明確化（stdio transport）
- Implementation インターフェースにオプション `description` フィールド
- HTTP 403 Forbidden（無効な Origins）の明確化
- SSE ストリームポーリングサポート
- JSON Schema 2020-12 をデフォルトダイアレクトに
- RFC 9728 OAuth 2.0 Protected Resource Metadata 準拠
- Elicitation のプリミティブ型デフォルト値サポート
- Schema Reference の index-property-only 型スタイル改善
- 各言語向けロギングガイダンスのテーラリング (#1970)

#### 参考リンク

- [MCP Specification](https://spec.modelcontextprotocol.io/)

---

### MCP-UI

**現行バージョン**: server/v6.1.0, client/v6.1.0 (2026-02-13)

#### v6.1.0 の主要な変更点

- **Experimental Messages サポート**: 実験的メッセージ対応 (#176)

#### v6.0.x の主要な変更点

- **MCP Apps 移行**: `mcp-ui` → `mcp apps` への完全リブランディング (#172)
- **MIME タイプ変更**: コンテンツタイプ仕様更新
- **Claude サポート追加**: サポートホストに Claude 追加
- **React レンダラー**: MCP Apps 用 React レンダラー (#147)
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

- **logprobs オプション化**: logprobs をオプショナルに変更 (#45)
- **API命名修正**: `Createresponse` → `createResponse` (#40)
- **CLI コンプライアンステスト**: `bin/compliance-test.ts` 追加
- **llms.txt リファクタ**: コアコンセプト、API詳細、イベントフォーマット強化
- **Bun 移行**: Node から Bun へパッケージマネージャー変更

#### 参考リンク

- [OpenResponses](https://github.com/openrouter/openresponses)

---

### UCP (Universal Commerce Protocol)

**現行バージョン**: v2026-01-23

#### 主要な変更点

- **EC カラースキーム**: 埋め込みチェックアウトの `ec_color_scheme` クエリパラメータ (#157)
- **Technical Committee → Tech Council**: 名称変更 (#168)
- **Standard Errors**: エラー概念の標準化 (#147)
- **Affirm パートナー追加**: エンドースドパートナーに Affirm 追加 (#166)
- **エンドースドパートナー追加**: Block, Fiserv, Klarna, Splitit (#149)
- **UCP-Agent ヘッダー**: openapi.json に追加
- **Cart Capability**: バスケット構築機能 (#73)
- **Context Intent フィールド**: intent フィールド追加、非識別制約明確化 (#95)
- **マルチ親スキーマ拡張**: 決定論的スキーマ解決 (#96)
- **サービストランスポート定義**: 名前変更とバージョニング (#154)
- **Shopify TC 代表変更**: Lee Richmond → Aaron Glazer (#165)
- **スキーマ参照修正**: 全ドキュメントの壊れたスキーマ参照を修正 (#160)
- **ダイアグラム刷新**: ドキュメントダイアグラムの近代化 (#99)

#### 参考リンク

- [UCP Protocol](https://github.com/anthropics/UCP)

---

### webmcp-tools

**現行バージョン**: 継続的デプロイ（バージョンタグなし）

**管理**: Google Chrome Labs

#### 主要な変更点

- **Chrome Extension v1.6**: 拡張機能バージョン更新 (#14)
- **Address Form サンプル**: アドレスフォームのサンプル追加 (#13)
- **Enum Schema**: enum input schema に `type:string` 追加 (#11)
- **Tool Evals Constraints**: ツール評価の引数制約実装 (#10)
- **Model Context Tool Inspector**: サブモジュールとして追加

#### 参考リンク

- [webmcp-tools](https://github.com/AugmentedWeb/webmcp-tools)

---

### x402 (Internet Native Payments)

**現行バージョン**: Go v2.2.0 / Python v2.1.0 / TypeScript Core v2.3.1

#### v2.2.0 / v2.1.0 の主要な変更点

- **MCP Transport 統合**: x402 ペイメントプロトコルの MCP トランスポート統合（Go, Python, TypeScript）
- **MegaETH メインネット**: Chain ID 4326、USDM デフォルトステーブルコイン
- **SVM トランザクションユニーク性**: memo instruction にランダム nonce 追加で重複防止
- **Payment Identifier Extension SDK**: Python SDK 実装 (#1111)
- **E2E テスト**: MCP トランスポートの E2E テスト（TypeScript, Python, Go） (#1149)

#### TypeScript Core v2.3.x

- **Extension Hooks**: クライアント・サーバーの拡張性向上フック追加
- **Zod エクスポート**: 型バリデーション用 Zod エクスポート追加
- **Python 互換性**: Zod optional/any 型のnullable化

#### エコシステムパートナー（新規追加）

- MerchantGuard, x402engine, RelAI Facilitator, ouchanip, invy, KAMIYO
- Foldset, Moltalyzer, clawdvine (旧 imagine), AsterPay

#### 参考リンク

- [x402 Protocol](https://github.com/x402-protocol/x402)

---

## Google Cloud / ADK

### ADK Python

**現行バージョン**: v1.25.0 (2026-02-11)

#### v1.25.0 の主要な変更点

- **SkillToolset**: ADK にスキルツールセット追加、スキル命令の最適化対応
- **外部アクセストークン**: Google credentials で外部渡しアクセストークンサポート
- **`auto_create_session` フラグ**: `adk api_server` CLI 用
- **`/health` / `/version` エンドポイント**: ADK Web サーバー用
- **イベントデルタメモリ**: `add_events_to_memory` ファサード追加
- **トークン閾値コンパクション**: 呼び出し後のイベント保持付きコンパクション
- **MCP リソースロードツール**: MCP リソースの読み込みツール追加
- **Gemini LLM `base_url`**: Gemini LLM クラスに base_url オプション追加
- **適合性テストレポート**: `adk conformance test` コマンドにレポート生成追加
- **LiteLlm モデル拡張**: サポートモデルの拡張とレジストリテスト追加
- **Memory Bank**: Vertex AI Memory Bank の generate/create モード追加

#### v1.25.0 バグ修正

- **DatabaseSessionService**: レース条件修正、ストレージ更新時刻によるセッション再読み込み
- **MCP セッション**: イベントループ閉鎖バグ修正
- **ストリーミングレスポンス**: grounding/citation メタデータの伝搬修正
- **クレデンシャルキー**: 安定した生成とクロスユーザーリーク防止
- **LiteLlm**: 関数レスポンスの空パーツ認識修正、HTTP/HTTPS メディア URL 対応

#### v1.24.x の主要な変更点

- **Consolidated Event View**: Event タブ廃止、メッセージ行のクリック展開式に刷新
- **A2UI v0.8 統合**: ADK parts を標準カタログ準拠の UI コンポーネントとして自動レンダリング
- **キーボードナビゲーション**: 矢印キーによるアクセシビリティ向上
- **関数呼び出しツールチップ**: 引数・レスポンス・状態変更の詳細表示
- **エージェントオプティマイザ**: 最適化インターフェースの追加
- **ツールセット認証**: `McpToolset`, `OpenAPIToolset` 等で認証サポート
- **McpToolset リソースアクセス**: MCP リソースへのユーザーアクセスメソッド追加
- **OpenAPI ツール非同期化**: `RestApiTool` の非同期対応
- **ライブモードスレッド分離**: ツール実行を別スレッドで実行可能に

#### 破壊的変更

| 変更 | 影響 |
|------|------|
| credential manager が `tool_context` を受け取るよう変更 (v1.24.0) | `callback_context` から `tool_context` への引数変更 |

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

- **OpenTelemetry Semconv Tracing**: セマンティック規約に基づくトレーシング実装 (#548)
- **LLM Variant**: Gemini 2.5 以下の LLM バリアント対応 (#562)
- **TracerProvider**: OTEL 設定と初期化 (#524)
- **Function Call Modifier プラグイン**: 関数呼び出し変更プラグイン (#535)
- **Preload Memory ツール**: メモリプリロードサポート (#527)

#### バグ修正

- `long_running_function_ids` のイベント生成時の受け渡し修正 (#553)
- リモートエージェントの部分レスポンスによるデータ重複修正 (#545)
- `RequestConfirmation` で `SkipSummarization` 設定しエージェントループ停止 (#544)
- 集約テキスト・思考のクリア修正（非追記タスクアーティファクト更新時） (#555)
- temp state デルタのローカルセッション適用修正 (#537)

#### 参考リンク

- [ADK Go](https://github.com/google/adk-go)

---

### ADK JS

**現行バージョン**: v0.2.4

#### 未リリースの変更点

- **Event Case Conversion**: snake_case ↔ camelCase イベント変換ユーティリティ (#127)
- **`pauseOnToolCalls` 設定**: エージェント命名バリデーション緩和と新設定 (#140)
- **`getOrCreateSession` ヘルパー**: BaseSessionService に追加 (#138)
- **API エクスポート標準化**: AgentEvent 型の標準化 (#136)
- **ApigeeLlm**: TypeScript ADK に Apigee LLM 追加 (#125)
- **Session Service Registry**: CLI 連携 (#126)
- **ESM ネイティブ CLI**: CommonJS から ESM への移行 (#113)
- **CLI version コマンド**: バージョン表示機能 (#115)
- **state/stateデルタ対応**: API サーバーのリクエストボディパラメータ (#117)
- **`instanceof` 置換**: `isBaseTool`/`isLlmAgent` ヘルパー使用 (#116)

#### 参考リンク

- [ADK JS](https://github.com/google/adk-js)

---

### Agent Starter Pack

**現行バージョン**: v0.36.0

#### v0.36.0 の主要な変更点

- **smart-merge**: enhance コマンドにスマートマージ機能追加 (#784)
- **Java ADK ドキュメント更新**: ADK Java 向けドキュメント改善 (#785)
- **Zod バージョン整合**: TypeScript テンプレートで `@google/adk` 依存と Zod バージョンを整合 (#779)

#### v0.35.x の主要な変更点

- **TypeScript ADK テンプレート**: `adk_ts` テンプレート追加 (#731)
- **エージェント選択 UI 改善**: More Options サブメニューによる構造化 (#766)
- **none デプロイメントターゲット**: デプロイなしオプション追加

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
- **MCP SDK v1.26.0**: 依存関係更新 (#216)

#### セキュリティ修正

- hono パッケージの脆弱性修正 (#215)
- lodash 4.17.23 へアップグレード (#209)
- qs 6.14.2 へアップグレード (#218)

#### 参考リンク

- [Cloud Run MCP](https://github.com/GoogleCloudPlatform/cloud-run-mcp)

---

### gcloud-mcp

**現行バージョン**: gcloud-mcp-v0.5.3

#### 主要な変更点

- **googleapis v171**: 依存関係更新 (#361)
- **MCP SDK v1.26.0**: SDK 更新 (#362)
- **storage-mcp v0.3.3**: ストレージコンポーネント更新 (#358)
- **observability-mcp v0.2.3**: オブザーバビリティコンポーネント更新 (#357)
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

#### 参考リンク

- [MCP Security](https://github.com/google/mcp-security)

---

### GenAI Toolbox

**現行バージョン**: v0.27.0 (2026-02-12)

#### v0.27.0 の主要な変更点

- **設定ファイル v2**: 設定ファイルフォーマットの v2 更新（**破壊的変更**） (#2369)
- **OTEL Semantic Convention**: テレメトリの詳細更新 (#1987)
- **CLI 直接ツール呼び出し**: CLI からのツール直接実行サポート (#2353)
- **Agent Skills 生成**: ツールセットからのエージェントスキル自動生成 (#2392)
- **Cloud Logging Admin**: ソース・ツール・ドキュメント追加 (#2137)
- **CockroachDB 統合**: cockroach-go による統合 (#2006)
- **AlloyDB Omni データプレーンツール**: 新規追加 (#2340)
- **Tool Call エラーカテゴリ**: エラー分類追加 (#2387)
- **Looker Validate Project**: プロジェクトバリデーションツール (#2430)

#### v0.26.0 の主要な変更点

- **User-Agent Metadata フラグ**: 新規追加 (#2302)
- **MCP レジストリフラグ**: MCP registry サポート
- **MCP specs 2025-11-25**: 最新仕様対応 (#2303)
- **`valueFromParam`**: Tool config サポート (#2333)
- **`embeddingModel`**: MCP handler でサポート (#2310)
- **BigQuery 設定可能化**: 最大行数設定 (#2262)
- **Cloud SQL**: backup/restore ツール追加 (#2141, #2171)
- **Snowflake 統合**: ソースとツール統合 (#858)
- **複数 prebuilt 設定結合**: サポート (#2295)

#### 破壊的変更

| 変更 | 影響 |
|------|------|
| 設定ファイル v2 (#2369) | 設定ファイルフォーマットの変更が必要 |
| OTEL テレメトリ更新 (#1987) | テレメトリ形式の変更 |
| Tool naming validation (#2305) | ツール名の検証強制化 |
| cloudgda パラメータ更新 (#2288) | 説明・パラメータ名変更 |

#### 参考リンク

- [GenAI Toolbox](https://github.com/googleapis/genai-toolbox)

---

## 注目ポイント

### 破壊的変更一覧

| 対象 | 変更内容 | 対応優先度 |
|------|---------|-----------|
| **GenAI Toolbox** | v0.27.0: 設定ファイル v2、OTEL テレメトリ更新 | 高 |
| **A2A** | v1.0.0-rc: 非複雑ID構造、OAuth、Enum、Part簡素化等 | 高 |
| **ACP** | v2026-01-30: Payment Handlers Framework 導入、fulfillment 構造変更 | 高 |
| **MCP-UI** | v6.0.0 で MCP Apps へ移行、MIME タイプ変更 | 高 |
| **ADK Python** | v1.24.0: credential manager 引数変更 (`callback_context` → `tool_context`) | 高 |
| **GenAI Toolbox** | v0.26.0: Tool naming validation 強制化 | 中 |
| **Google Analytics MCP** (未リリース) | パッケージ名 `analytics-mcp` にリネーム | 低 |

### メジャーアップデート

1. **ADK Python v1.25.0** - SkillToolset、外部アクセストークン、MCP リソースロードツール
2. **GenAI Toolbox v0.27.0** - 設定ファイル v2（破壊的変更）、CLI 直接ツール呼び出し、Agent Skills 生成
3. **Agent Starter Pack v0.36.0** - smart-merge、Zod バージョン整合
4. **MCP-UI v6.1.0** - Experimental Messages サポート
5. **ACP v2026-01-30** - Capability Negotiation、Payment Handlers、Extensions Framework
6. **x402 v2.2.0/v2.1.0** - MCP Transport 統合、MegaETH、SVM ユニーク性向上

### 新規追加

1. **webmcp-tools** - Google Chrome Labs による Web MCP ツール（Chrome Extension、Tool Evals）

### セキュリティ更新

- **MCP**: SSRF 対策ドキュメント追加
- **Cloud Run MCP**: hono / lodash / qs の脆弱性修正
- **GKE MCP**: Workload Security スキル追加
- **MCP Security**: キュレーテッドルール管理ツール、gsutil 移行
- **ADK Python**: クレデンシャルキー生成の安定化とクロスユーザーリーク防止
