# プロトコル変更ログ

最終更新: 2026-03-15

各プロトコル・Google Cloud サブモジュールの主要な変更点をまとめたドキュメント。

---

## プロトコル (Protocols)

### A2A (Agent-to-Agent)

**現行バージョン**: v1.0.0 (2026-03-12)

#### v1.0.0 の主要な変更点

- **正式リリース**: v1.0.0-rc から v1.0.0 への昇格
- **仕様リファクタ**: アプリケーションプロトコル定義とトランスポートマッピングの分離
- **Push Notification 統合**: `TaskPushNotificationConfig` と `PushNotificationConfig` の統合 (#1500)
- **フィールドリネーム**: `SendMessageConfiguration.blocking` → `return_immediately` (#1507)
- **HTTP エラーマッピング**: `google.rpc.Status` (AIP-193) 準拠の HTTP+JSON エラーマッピング (#1600)
- **LF パッケージプレフィックス**: LF パッケージプレフィックス追加 (#1474)
- **Extension ガバナンス**: Extension ガバナンスドキュメント追加
- **In-Task Authorization**: タスク内認可の詳細拡張
- **SDK 後方互換性**: SDK が後方互換可能な設計に

#### 破壊的変更（v1.0.0-rc → v1.0.0）

| 変更 | 影響 |
|------|------|
| Push Notification Config 統合 (#1500) | `TaskPushNotificationConfig`/`PushNotificationConfig` の統合 |
| 重複 ID 削除 (#1487) | create task push config リクエストの構造変更 |
| `ListTaskPushNotificationConfigs` 複数形化 (#1486) | メソッド名変更 |
| `blocking` → `return_immediately` (#1507) | `SendMessageConfiguration` フィールド名変更 |
| 仕様リファクタ | プロトコル定義とトランスポートの分離 |

#### 破壊的変更（v0.3.0 → v1.0.0）

| 変更 | 影響 |
|------|------|
| ID形式簡素化: 複合ID → 単純UUID/リテラル (#1389) | リクエストID形式の変更 |
| Enum フォーマット: `lowercase` → `SCREAMING_SNAKE_CASE` (#1384) | 全Enum値の変更 |
| HTTP URL簡素化: `/v1/` プレフィックス削除 | エンドポイント URL の変更 |
| Well-Known URI: `agent.json` → `agent-card.json` (#841) | エンドポイント URL の変更 |
| OAuth implicit/password フロー削除 (#1303) | 認証フロー変更 |
| Push Notification Config 統合 (#1500) | 構造変更 |

#### 参考リンク

- [A2A Specification](https://github.com/a2aproject/A2A)

---

### A2UI (Agent-to-User Interface)

**現行バージョン**: v0.9 (2026-01-22)

#### v0.9 の主要な変更点

- **Prompt First 設計**: 構造化出力優先からプロンプト埋め込み優先へ哲学変更
- **Web Renderers Data Model**: Web レンダラー向けデータモデルの完全実装 (#606)
- **メッセージタイプ刷新**:
    - `beginRendering` → `createSurface`
    - `surfaceUpdate` → `updateComponents`
    - 新規: `updateDataModel`, `deleteSurface`
- **コンポーネント構造簡素化**: キーベースラッパーからフラット構造へ
- **モジュラースキーマ**: `common_types.json`, `server_to_client.json`, `standard_catalog.json` に分割
- **Theme プロパティ**: `styles` → `theme` にリネーム
- **統一カタログ**: コンポーネントと関数を単一カタログに統合
- **Enum Case 標準化**: `lowerCamelCase` への統一 (#639)
- **UI Validation Events**: TextField でバリデーションイベント発火 (#609)

#### 未リリースの変更点

- **MCP Apps 統合**: A2UI に MCP Apps を統合 (#748)
- **McpApps A2UI コンポーネント**: MCP Apps 用コンポーネント導入 (#801)
- **React レンダラー**: React レンダラー実装 (#542)
- **Generic Binder**: web_core v0.9 Generic Binder とリファクタ (#848)
- **Basic Catalog Zod スキーマ**: Zod ベースのカタログスキーマ
- **Gallery App 仕様**: Gallery App 仕様とレンダラーガイドの精緻化 (#821)
- **assemble_catalog.py**: 新カタログ組み立てスクリプト (#817)
- **ミニマルカタログ**: 最小構成のカタログ追加 (#732)
- **サーバーケイパビリティスキーマ**: トランスポート非依存の機能交換用スキーマ (#731)
- **フレームワーク非依存データレイヤー**: Web コアライブラリのフレームワーク非依存データレイヤー実装
- **カタログリネーム**: `standard_catalog` → `basic_catalog` にリネーム
- **CallFunctionMessage**: `CallFunctionMessage` と `functionResponse` の追加

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

#### 未リリースの変更点

- **CODEOWNERS 設定**: ファウンディングメンテナーの定義
- **ガバナンスモデル改訂**: ガバナンス構造の見直し

#### SEP（仕様拡張提案）進行中

- **Webhook Signing with Replay Protection**: Webhook 署名とリプレイ攻撃防止
- **Delegated Authentication**: エージェントからマーチャントへの認証委譲
- **Payment Intent**: capture vs authorize の支払い意図拡張
- **Discovery Well-Known Document**: ディスカバリー用 Well-Known ドキュメント
- **MCP Transport Binding**: Agentic Checkout 向け MCP トランスポートバインディング
- **Mandatory Idempotency Requirements**: 冪等性の要件と保証 (#121)
- **Post-Purchase Lifecycle Tracking**: リッチな購入後ライフサイクル追跡 (#106)
- **Seller-Backed Payment**: セラー独自決済方式サポート (#114)
- **Payment Handler Display Order**: マーチャント推奨順序 (#133)

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

#### 未リリースの変更点

- **CoderForge-Preview データセット**: 新規データセット追加
- **Nemotron Terminal Corpus**: 新規データセット追加

#### 参考リンク

- [ADP Protocol](https://github.com/neulab/agent-data-protocol)

---

### AG-UI (Agent-User Interaction Protocol)

**現行バージョン**: 継続的デプロイ（バージョンタグなし）

#### 主要な変更点

- **Claude Agent SDK 統合**: Claude Agent SDK インテグレーション追加 (#916)
- **Langroid 統合**: Langroid フレームワーク統合と Dojo デモアプリ統合
- **Bedrock Converse API 互換性**: LangGraphAgent での Bedrock Converse API 互換性修正 (#1300)
- **langgraph python v0.0.26**: LangGraph Python リリース (#1301)
- **Dojo CopilotKit パッケージ統合**: 不要な `@copilotkitnext/*` 依存削除
- **LRO ツールコール ID リマッピング**: SSE ストリーミングでの Long-Running Operations ツールコール ID リマッピング
- **REASONING イベント移行**: `THINKING_*` イベントから `REASONING_*` イベントへの移行（LangGraph）
- **A2UI チャット統合**: `injectA2UITool` オプション付き A2UI チャット統合 (#1177)
- **Reasoning Spec**: 推論仕様追加 (#1050)
- **マルチモーダル仕様**: multimodal spec 追加 (#1084)
- **Ruby SDK**: フルプロトコル実装 (#865)
- **Dart SDK v0.1.0**: フルプロトコル実装
- **Kotlin SDK v0.2.7**: バージョン更新 (#1103)
- **NX 移行**: Turbo から NX へビルドシステム移行 (#1092)
- **フレームワーク統合**: LangGraph, Mastra, CrewAI 対応
- **状態管理**: JSON Patch デルタ (RFC 6902) サポート

#### 参考リンク

- [AG-UI Protocol](https://github.com/ag-ui-protocol/ag-ui)

---

### AgentSkills

**現行バージョン**: 継続的デプロイ（バージョンタグなし）

**管理**: Anthropic

#### 主要な変更点

- **ベストプラクティスガイド**: スキル作成者向けベストプラクティスガイド追加 (#224)
- **説明最適化ガイド**: スキル説明の最適化ガイド追加
- **スキル評価ガイド**: スキル評価方法のガイド追加
- **統合ガイダンス**: 統合ガイダンスドキュメント追加
- **仕様ドキュメント整理**: 仕様ドキュメントのクリーンアップと改善
- **Apache 2.0 ライセンス**: トップレベル LICENSE 追加 (#122)
- **CONTRIBUTING.md**: コントリビューションガイド追加
- **スクリプト利用ガイド**: スキル作成者向け "Using scripts" ガイド追加 (#196)

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

**現行バージョン**: 2025-11-25

#### 主要な変更点

- **ブログサイト改善**: モバイルレイアウト、SEO改善、スタイリング修正
- **Claude クライアント機能サポート更新**: Claude クライアントの機能サポート情報更新
- **SDK 階層評価**: Python SDK Tier 1, C# SDK Tier 1, Go SDK Tier 1, Java SDK Tier 2, Swift SDK Tier 3, PHP SDK Tier 3 の評価追加
- **Extensions トップレベルタブ**: Extensions を専用ページ付きトップレベルタブに昇格 (#2263)
- **デザイン原則ページ**: コミュニティセクションにデザイン原則ページ追加 (#2303)
- **MCP Apps サポート拡大**: Claude Desktop, ChatGPT, MCPJam, Postman, VSCode, goose, Copilot でのクライアントサポート
- **実験的タスク機能**: アプリケーション駆動タスクアーキテクチャ、ポーリング付き状態追跡
- **セキュリティ強化**: 外部認証サポート付き認可仕様の強化、GitHub Security Advisories 統合
- **OpenID Connect Discovery 1.0**: 認可サーバーディスカバリー対応
- **アイコンサポート**: ツール、リソース、リソーステンプレート、プロンプトにアイコン追加
- **Extensions フレームワーク** (SEP-2133, Final): 拡張機能ケイパビリティのスキーマ追加
- **SSRF セキュリティ**: SSRF 対策ドキュメント追加
- **MCP Apps CSP**: アンバンドルアセット向け Content Security Policy 要件文書化

#### 参考リンク

- [MCP Specification](https://spec.modelcontextprotocol.io/)

---

### MCP-Apps

**現行バージョン**: v1.2.2 (2026-03-12)

#### v1.2.x の主要な変更点

- **Zod v4 互換性修正**: `zod/v4` からのインポート修正（SDK の Zod API と一致） (#548)
- **react-with-deps バンドル修正**: SDK+zod を react-with-deps に正しくバンドル (#539)
- **E2E セキュリティテスト改善**: frames[] トラバーサルによる no-op セキュリティインジェクションテスト修正 (#540)
- **npm ci キャッシュ改善**: CI パフォーマンス改善
- **ListServerResources / readServerResource API**: 新規 API 追加
- **セキュリティドキュメント・SEO改善**: セキュリティガイダンスとSEO最適化
- **テーマ対応ロゴ**: `picture` 要素によるテーマ対応ロゴ (#545)

#### v1.1.x の主要な変更点

- **downloadFile 機能**: App → AppBridge 統合テスト付き `downloadFile` 機能追加
- **PDF Server 強化**: 堅牢なパスバリデーション、フォルダ/ファイルルートサポート、ドメイン許可リスト廃止・HTTPS 必須化
- **MCPB パッケージング**: pdf-server 用 MCPB パッケージングと Claude Code プラグイン
- **SECURITY.md 追加**: GitHub Security Advisories ガイダンス (#472)

#### 参考リンク

- [MCP-Apps](https://github.com/anthropics/mcp-apps)

---

### MCP-UI

**現行バージョン**: client/v7.0.0 (2026-03-12)

#### v7.0.0 の主要な変更点

- **レガシー仕様削除**: レガシー仕様の完全削除（**破壊的変更**） (#185)
- **メジャーバージョンバンプ**: 破壊的変更に伴うバージョンバンプ (#187)

#### 破壊的変更

| バージョン | 変更 |
|-----------|------|
| v7.0.0 | レガシー仕様の完全削除 |
| v6.0.0 | 廃止コンテンツタイプ削除、MIMEタイプ変更 |
| v5.0.0 | `delivery` → `encoding`、`flavor` → `framework` |

#### 参考リンク

- [MCP-UI](https://github.com/MCP-UI-Org/mcp-ui)

---

### OpenResponses

**現行バージョン**: 継続的デプロイ（バージョンタグなし）

#### 主要な変更点

- **Red Hat コミュニティ追加**: Red Hat ロゴ追加
- **コアメンテナーリスト更新**: メンテナー管理改善
- **Llama Stack 統合**: Llama Stack インテグレーション追加 (#29)
- **Databricks コミュニティ追加**: コミュニティセクションにロゴ追加
- **logprobs オプション化**: logprobs をオプショナルに変更 (#45)
- **API命名修正**: `Createresponse` → `createResponse` (#40)
- **CLI コンプライアンステスト**: `bin/compliance-test.ts` 追加
- **Bun 移行**: Node から Bun へパッケージマネージャー変更

#### 参考リンク

- [OpenResponses](https://github.com/openrouter/openresponses)

---

### UCP (Universal Commerce Protocol)

**現行バージョン**: v2026-01-23

#### v2026-01-23 後の改善

- **Eligibility Claims & Verification**: 適格性主張と検証コントラクト (#250)
- **Authorization & Abuse Signals**: 認可と不正利用シグナル（**破壊的変更**） (#203)
- **Discount Capability 拡張**: カートへの割引機能拡張 (#246)
- **Catalog Search & Lookup**: 製品ディスカバリー用カタログ検索・参照機能 (#55)
- **Business Logic エラーレスポンス**: checkout/cart のビジネスロジックエラーレスポンス
- **`reverse_domain_name` 独立型化**: スタンドアロン型への昇格 (#260)
- **Transition Schema 修正**: UCP transition schema のグレースフルな活用修正 (#196)
- **Checkout ID 非推奨化**: update リクエストで `checkout_id` を `deprecated_required_to_omit` に (#145)
- **`available_instruments`**: payment handler configurations に `available_instruments` 追加 (#187)
- **Checkout.com パートナー追加**: エンドースドパートナーに Checkout.com 追加

#### v2026-01-23 の主要な変更点

- **リクエスト/レスポンス署名**: UCP プロトコルの暗号署名機能
- **EC カラースキーム**: 埋め込みチェックアウトの `ec_color_scheme` クエリパラメータ (#157)
- **ECP サポート**: E-Commerce Connector Protocol、チェックアウトごとのトランスポート設定
- **Cart Capability**: バスケット構築機能 (#73)
- **Context Intent フィールド**: intent フィールド追加、非識別制約明確化 (#95)

#### 破壊的変更

| 変更 | 影響 |
|------|------|
| Authorization & Abuse Signals (#203) | 認可シグナルの構造変更 |
| Checkout スキーマリファクタ (#100) | チェックアウトスキーマの構造変更 |
| Payments/Services/Capabilities 統一階層化 (#49) | 決済・サービス・能力の統一構造へ |
| `_meta.ucp.profile` 非推奨 | 標準メタデータへの移行 |

#### 参考リンク

- [UCP Protocol](https://github.com/anthropics/UCP)

---

### webmcp-tools

**現行バージョン**: 継続的デプロイ（バージョンタグなし）

**管理**: Google Chrome Labs

#### 主要な変更点

- **WebMCP 型共有**: WebMCP 型を共有ロケーションに移動
- **webmcp-maze デモ**: 新規迷路デモプロジェクト追加
- **WebMCP Flow**: アーキテクチャダイアグラムビルダー追加
- **Mystery Doors デモ**: 宣言的・命令的パターンのデモ
- **マルチバックエンドサポート**: 異なるバックエンドのサポート追加
- **Vercel AI SDK 移行**: 実験的マルチステップツール実行付き Vercel AI SDK への移行
- **Pizza-maker デモ**: Pizza-maker デモとベーシック WebMCP zaMaker Evals 追加
- **Industry Vertical Evals**: ヘルスケア、不動産、商業、旅行の業界別評価追加
- **Chrome Extension v1.6**: 拡張機能バージョン更新 (#14)
- **Model Context Tool Inspector**: サブモジュールとして追加

#### 参考リンク

- [webmcp-tools](https://github.com/AugmentedWeb/webmcp-tools)

---

### x402 (Internet Native Payments)

**現行バージョン**: Go v2.4.1 / Python v2.3.0 / TypeScript Core v2.5.0

#### 未リリースの変更点

- **ERC-7710 サポート**: exact_evm スキームでの ERC-7710 サポート仕様 (#732)
- **Signed Offer & Receipt Extension**: オプショナルな署名付きオファー＆レシート拡張（ドラフト） (#935)
- **Express スタイルルートパラメータ**: `:param` 形式の動的ルートパラメータサポート (#1313)
- **Polygon メインネット**: CDP Facilitator に Polygon メインネットサポート追加 (#1564)
- **Permit2 / Extensions SDK 改善**: Permit2 と Extensions SDK の改善 (#1487)
- **Stellar ブロックチェーンサポート**: Stellar サポートドキュメント追加

#### Go v2.4.x の主要な変更点

- **ルート設定バリデーション**: 初期化時のルート設定検証 (#1364)
- **リトライ with Exponential Backoff**: `GetSupported` の 429 レスポンスに対する指数バックオフリトライ (#1357)
- **ERC20 Gas Sponsorship 拡張**: ガススポンサーシップ拡張実装 (#1336)

#### Python v2.3.0 の主要な変更点

- **MCP Transport 統合の安定化**: Python MCP トランスポートの安定化
- **camelCase シリアライゼーション修正**: 仕様準拠の camelCase 出力がデフォルト化 (#1122)

#### TypeScript Core v2.5.x の主要な変更点

- **PAYMENT-RESPONSE ヘッダー**: 決済失敗レスポンスに `PAYMENT-RESPONSE` ヘッダー追加 (#1128)
- **ERC20 Gas Sponsorship 拡張**: ガススポンサーシップ拡張実装 (#1328)
- **Permit2 アップグレード**: 最新コントラクト状態に合わせた permit2 実装更新 (#1325)

#### エコシステムパートナー（新規追加）

- WalletIQ, Stakevia, Obol, Augur, Agent Health Monitor
- Tollbooth（OSS x402 API ゲートウェイ）, Kurier, Laso Finance, xpay Facilitator
- DJD Agent Score, QuantumShield API, V402Pay
- MerchantGuard, x402engine, RelAI Facilitator
- Foldset, Moltalyzer, clawdvine, AsterPay, Agnic.AI, Postera

#### 参考リンク

- [x402 Protocol](https://github.com/x402-protocol/x402)

---

## Google Cloud / ADK

### ADK Python

**現行バージョン**: v1.27.1 (2026-03-13)

#### v1.27.1 の主要な変更点

- **LlmAgent 修正**: バージョンフィールド欠落による LlmAgent 作成問題の修正ロールバック

#### v1.27.0 の主要な変更点

**[Core]**

- **A2A リクエストインターセプター**: `RemoteA2aAgent` に A2A リクエストインターセプター導入
- **UiWidget**: `EventActions` に UiWidget 追加（実験的 UI Widgets 機能）
- **AuthProviderRegistry**: `CredentialManager` 内のプラガブル認証統合
- **Durable Runtime**: 永続ランタイムサポート
- **SchemaUnion 出力スキーマ**: LLM Agent で全 `types.SchemaUnion` を `output_schema` としてサポート

**[Models]**

- **Anthropic PDF サポート**: Anthropic LLM で PDF ドキュメントサポート
- **Anthropic ストリーミング**: Anthropic モデルのストリーミングサポート
- **LiteLLM 出力スキーマ**: LiteLLM モデルでツールと出力スキーマの同時使用対応

**[Tools]**

- **GCS Skills**: Skills の GCS ファイルシステムサポート（テキスト・PDF、サンプルエージェント付き）
- **MCP App UI Widgets**: MCPTool で MCP App UI ウィジェットサポート
- **BigQuery Dataplex Catalog 検索ツール**: BigQuery ADK に追加
- **RunSkillScriptTool**: SkillToolset に追加
- **ADK ツール in SkillToolset**: SkillToolset の `additional_tools` フィールドで ADK ツールサポート
- **BashTool**: スキルツールセットに BashTool 追加
- **Bigtable クラスタメタデータツール**: 新規追加
- **OpenAPIToolset `preserve_property_names`**: プロパティ名保持オプション追加

**[Optimization]**

- **`adk optimize` コマンド**: 最適化コマンド追加
- **GEPA Root Agent Prompt Optimizer**: ルートエージェントプロンプトオプティマイザー
- **LocalEvalService 連携**: 最適化インフラと LocalEvalService 間のインターフェース

**[Observability]**

- **`gen_ai.agent.version` スパン属性**: 新規追加
- **`gen_ai.tool.definitions`**: 実験的セマンティック規約にツール定義追加
- **`gen_ai.client.inference.operation.details` イベント**: 実験的セマンティック規約
- **ツール実行エラーコード**: OpenTelemetry スパンにキャプチャ

**[Web]**

- **HITL 改善**: Long-Running Functions にチャット内直接レスポンス
- **アーティファクトレンダリング**: 再開時のアーティファクトレンダリング

**[Integrations]**

- **BigQuery プラグイン強化**: fork safety, auto views, trace continuity
- **LangChain / CrewAI 統合**: integrations フォルダに移動
- **A2A 実装刷新**: `A2aAgentExecutor` と `RemoteA2aAgent` の新実装

#### v1.26.0 の主要な変更点

- **Agent Registry**: ADK にエージェントレジストリ追加
- **Skills 仕様準拠**: Agent Skills 仕様のバリデーション、エイリアス、スクリプト、自動インジェクション対応
- **A2A インターセプター**: `A2aAgentExecutor` にインターセプターフレームワーク追加
- **Apigee LLM 統合**: `/chat/completions` 統合とストリーミングサポート
- **User Personas**: 評価フレームワークにユーザーペルソナ導入
- **ID Token サポート**: OAuth2 credentials でのネイティブ `id_token` サポート
- **OpenTelemetry トレースコンテキスト**: MCP ツール呼び出しに追加
- **トークンコンパクション改善**: イントラ呼び出しコンパクションとリクエスト前トークンコンパクション

#### 破壊的変更

| 変更 | 影響 |
|------|------|
| credential manager が `tool_context` を受け取るよう変更 (v1.24.0) | `callback_context` から `tool_context` への引数変更 |
| OpenTelemetry BigQuery プラグイントレーシング移行 (v1.23.0) | カスタム ContextVar からの移行 |

#### 参考リンク

- [ADK Python](https://github.com/google/adk-python)

---

### ADK Go

**現行バージョン**: v0.6.0

#### v0.6.0 の主要な変更点

- **Apigee モデル**: Apigee モデルサポート追加 (#639)
- **RemoteAgent パーツ変換拡張ポイント**: RemoteAgent パーツ変換の拡張ポイント (#627)
- **pathPrefix 設定**: API ランチャーに pathPrefix 設定追加 (#616)
- **Runner オプション**: `WithStateDelta` 追加 (#615)
- **ExampleTool ファクトリ**: 設定可能な ExampleTool ファクトリ追加 (#612)
- **Replay プラグイン**: リプレイプラグイン追加 (#618)
- **GitHub Actions Node 24 互換性**: CI 更新 (#642)

#### v0.5.0 の主要な変更点

- **OpenTelemetry Semconv Tracing**: セマンティック規約に基づくトレーシング完全実装
- **Debug Endpoints v2**: GCP quota/resource project バリデーション付きデバッグエンドポイント
- **Retry and Reflect プラグイン**: リトライ・リフレクションプラグイン追加
- **Logging プラグイン**: ロギングプラグイン追加
- **Preload Memory ツール**: メモリプリロードサポート

#### 未リリースの変更点

- **Debug テレメトリリファクタ**: トレースアクセスの最適化 (#593)
- **OTel 構造化ロギング**: 構造化ロギング追加 (#552)
- **Debug Endpoints adk-web 統合**: デバッグエンドポイントの adk-web 統合 (#597)
- **A2A アーティファクトモード**: 非パーシャルイベントごとのアーティファクト (#599)

#### 参考リンク

- [ADK Go](https://github.com/google/adk-go)

---

### ADK JS

**現行バージョン**: v0.2.4

#### v0.2.4 の主要な変更点

- **A2A 統合**: CLI オプションによる A2A 経由のエージェント提供 (#188)
- **A2A Agent Card**: A2A エージェントカード追加 (#187)
- **A2A Agent Executor**: A2A エージェントエグゼキューター実装
- **トークンベースコンテキストコンパクション**: トークンベースのコンテキスト圧縮 (#191)
- **ADK API サーバーランダムポート**: フリーポートでの起動オプション (#197)
- **セッション DB 初期化修正**: 初期化時の既存テーブル全削除問題の修正 (#195)
- **A2A VideoMetadata サポート**: パーツ変換時の VideoMetadata 対応 (#198)
- **テスト API サーバーヘルパー**: 統合テスト用ヘルパー追加 (#185)
- **MikroORM リファクタリング**: セッションサービスのリファクタ

#### v0.4.0 の主要な変更点

- **Database Session Service**: データベースセッションサービス追加
- **ApigeeLlm**: TypeScript ADK に Apigee LLM 追加
- **ESM ネイティブ CLI**: CommonJS から ESM への移行
- **FileArtifactService**: ファイルアーティファクトサービス追加
- **A2A ↔ GenAI パーツ変換**: A2A と GenAI 間のパーツ変換ユーティリティ

#### 参考リンク

- [ADK JS](https://github.com/google/adk-js)

---

### Agent Starter Pack

**現行バージョン**: v0.39.2 (2026-03-13)

#### v0.39.x の主要な変更点

- **GKE デプロイターゲット**: GKE をデプロイターゲットとして追加 (#833)
- **CLI ウェルカムバナー刷新**: ASP ロゴ付きウェルカムバナーのリデザイン (#860)
- **プロトタイプモード改善**: デフォルトで `deployment_target='none'` (#855)
- **GKE Cloud SQL サポート修正**: GKE Cloud SQL サポートの修正 (#874)
- **enhance 失敗修正**: プロトタイプからデプロイターゲットへの enhance 失敗修正 (#872)
- **agentic_rag Vector Search 修正**: テンプレートバグ修正 (#866)

#### v0.38.0 の主要な変更点

- **enhance コマンド改善**: バグ修正と UX 改善
- **Gemini 3 Flash Preview**: 評価ジャッジモデルとして統合
- **Vertex AI Search/Vector Search**: agentic_rag モジュール向けデータコネクター追加

#### 参考リンク

- [Agent Starter Pack](https://github.com/GoogleCloudPlatform/agent-starter-pack)

---

### Cloud Run MCP

**現行バージョン**: v1.10.0

#### v1.10.0 の主要な変更点

- **cloud-run-mcp クライアント**: OSS Run MCP からのデプロイ用クライアント追加 (#242)
- **Ingress ポリシー環境変数**: 環境変数によるイングレスポリシー設定 (#243)
- **アーティファクトダウンロードリファクタ**: 再利用可能なダウンロードロジック (#240)
- **Run v1 クライアント**: googleapis ベースの Run v1 クライアント追加 (#236)
- **統合テスト拡充**: Java, Node.js, Python プロジェクトの統合テスト追加 (#235, #237, #239)
- **Hono 4.12.7**: 依存関係更新

#### v1.9.0 の主要な変更点

- **依存関係更新**: Hono v4.12.0、AJV v8.18.0、fast-xml-parser 更新

#### 参考リンク

- [Cloud Run MCP](https://github.com/GoogleCloudPlatform/cloud-run-mcp)

---

### gcloud-mcp

**現行バージョン**: gcloud-mcp-v0.5.3 / storage-mcp-v0.3.3 / observability-mcp-v0.2.3

#### 主要な変更点

- **backupdr-mcp v0.1.0**: Backup DR MCP サーバー新規追加 (#372, #380)
- **googleapis v171**: 依存関係更新 (#361)
- **MCP SDK v1.26.0**: SDK 更新 (#362)
- **storage-mcp v0.3.3**: ストレージコンポーネント更新 (#358)
- **observability-mcp v0.2.3**: オブザーバビリティコンポーネント更新 (#357)
- **Windows 互換性**: リファクタリング (#342)
- **フィルタリング精度**: 改善 (#320)

#### 参考リンク

- [gcloud-mcp](https://github.com/googleapis/gcloud-mcp)

---

### GKE MCP

**現行バージョン**: v0.9.0

#### v0.9.0 の主要な変更点

- **GKE Workload Security スキル**: ワークロードセキュリティ管理 (#172)
- **クラスタ作成ベストプラクティス**: ドキュメント追加 (#177)
- **Go 依存関係更新**: Go 1.25.6 へ更新 (#176)

#### 未リリースの変更点

- **Docker イメージサポート**: Docker イメージのサポート追加 (#183)
- **Go 1.25.7**: Go バージョン更新 (#182)

#### 参考リンク

- [GKE MCP](https://github.com/googleapis/gke-mcp)

---

### Google Analytics MCP

**現行バージョン**: v0.2.0

#### v0.2.0 の主要な変更点

- **ADK スキーマ型修正**: null 型の除去修正
- **pipx 対応**: サーバーの pipx 利用対応
- **nox 2026 対応**: nox 依存関係更新

#### v0.1.1 の主要な変更点

- **`list_property_annotations`**: 新ツール追加
- **`run_report` 日付範囲スキーマ修正**: Codex CLI での失敗修正 (#67)

#### 未リリースの破壊的変更

| 変更 | 影響 |
|------|------|
| パッケージ名を `analytics-mcp` にリネーム (#44) | インストールコマンドの変更が必要 |

#### 参考リンク

- [Google Analytics MCP](https://github.com/googleanalytics/google-analytics-mcp)

---

### MCP (Google Cloud)

#### 主要な変更点

- **Gemini 3.1 Pro Preview**: ルートエージェントモデルを gemini-3.1-pro-preview に更新
- **デモ動画リンク**: README にデモ動画リンク追加
- **Cloud Data MCP サンプル**: DK と Cloud SQL リモート MCP のラボ追加
- **Chrome DevTools サーバー**: 新規 MCP サーバー追加

#### 参考リンク

- [Google Cloud MCP](https://github.com/google/mcp)

---

### MCP Security

**現行バージョン**: secops-v0.7.0 (2026-03-14)

#### v0.7.0 の主要な変更点

- **Rule Exclusions 管理ツール**: ルール除外管理ツール追加 (#242)

#### v0.6.0 の主要な変更点

- **Investigation 管理ツール**: 調査管理ツール追加 (#220)
- **Watchlist 管理ツール**: ウォッチリスト管理ツール追加 (#222)
- **Advanced Rule Operations**: 高度なルール操作追加 (#229)
- **キュレーテッドルール管理ツール**: retrohunt とアラート検索ツール追加 (#227)
- **Remote MCP サーバー**: リモート MCP サーバー実装とドキュメント (#215)
- **Gemini CLI 拡張**: google-secops Gemini CLI extension 追加

#### 参考リンク

- [MCP Security](https://github.com/google/mcp-security)

---

### GenAI Toolbox

**現行バージョン**: v0.29.0 (2026-03-13)

#### v0.29.0 の主要な変更点

- **プリビルトツールセット再構成**: AlloyDB, Spanner, Dataplex, OSS-DB, CloudSQL, BigQuery, Firestore のプリビルトツールセットを再構成（**破壊的変更**）
- **テレメトリメトリクス更新**: セマンティック規約に合わせた更新（**破壊的変更**）
- **User Agent メタデータ**: エンベディング生成とスキル生成に User Agent メタデータ追加
- **`additional-notes` フラグ**: generate skills コマンドに追加
- **カスタム OAuth ヘッダー名**: BigQuery 用カスタム OAuth ヘッダー名サポート
- **MongoDB ツールアノテーション**: LLM 理解向上のためのツールアノテーション追加
- **Serverless Spark ツール**: `get_session_template`, `list/get sessions` 追加

#### v0.28.0 の主要な変更点

- **動的リロードポーリング**: 動的リロードにポーリングシステム追加
- **Dataproc ソースとツール**: Dataproc ソースおよびクラスタ/ジョブの一覧・取得ツール
- **PostgreSQL pgx クエリ実行モード**: 設定可能なクエリ実行モード
- **Redis TLS サポート**: Redis 接続の TLS サポート追加
- **Looker テスト・ビュー作成**: Get All LookML Tests、Run LookML Tests、Create View From Table ツール追加
- **Looker ディレクトリ管理**: ディレクトリの一覧・作成・削除ツール
- **Oracle DML 有効化**: Oracle DML 操作の有効化と配列型エラー修正
- **必須パラメータ null バリデーション**: 明示的 null 値の必須バリデーション強制
- **UI ツールリストパネル**: リサイズ可能に

#### v0.27.0 の主要な変更点

- **設定ファイル v2**: 設定ファイルフォーマットの v2 更新（**破壊的変更**）
- **CLI 直接ツール呼び出し**: CLI からのツール直接実行サポート
- **Agent Skills 生成**: ツールセットからのエージェントスキル自動生成
- **CockroachDB 統合**: cockroach-go による統合
- **AlloyDB Omni データプレーンツール**: 新規追加

#### 破壊的変更

| 変更 | 影響 |
|------|------|
| プリビルトツールセット再構成 (v0.29.0) | AlloyDB, Spanner 等のツールセット構造変更 |
| テレメトリメトリクス更新 (v0.29.0) | テレメトリ形式の変更 |
| 設定ファイル v2 (v0.27.0, #2369) | 設定ファイルフォーマットの変更が必要 |
| Tool naming validation (v0.26.0, #2305) | ツール名の検証強制化 |

#### 参考リンク

- [GenAI Toolbox](https://github.com/googleapis/genai-toolbox)

---

## 注目ポイント

### 破壊的変更一覧

| 対象 | 変更内容 | 対応優先度 |
|------|---------|-----------|
| **A2A** | v1.0.0: Push Notification Config 統合、`blocking`→`return_immediately`、仕様リファクタ | 高 |
| **GenAI Toolbox** | v0.29.0: プリビルトツールセット再構成、テレメトリメトリクス更新 | 高 |
| **MCP-UI** | v7.0.0: レガシー仕様の完全削除 | 高 |
| **UCP** | Authorization & Abuse Signals の構造変更 | 高 |
| **GenAI Toolbox** | v0.27.0: 設定ファイル v2 | 高 |
| **ACP** | v2026-01-30: Payment Handlers Framework 導入 | 高 |
| **ADK Python** | v1.24.0: credential manager 引数変更 | 中 |
| **Google Analytics MCP** (未リリース) | パッケージ名 `analytics-mcp` にリネーム | 低 |

### メジャーアップデート

1. **A2A v1.0.0** - 正式リリース、仕様リファクタ、Push Notification統合、HTTP エラーマッピング改善
2. **ADK Python v1.27.1** - A2Aインターセプター、Anthropicストリーミング、UiWidget、`adk optimize`コマンド、GCS Skills
3. **ADK Go v0.6.0** - Apigeeモデル、RemoteAgentパーツ変換拡張、Replayプラグイン
4. **ADK JS v0.2.4** - A2A統合、トークンベースコンテキストコンパクション
5. **GenAI Toolbox v0.29.0** - プリビルトツールセット再構成（破壊的）、MongoDB/Serverless Sparkツール
6. **MCP-UI v7.0.0** - レガシー仕様削除（破壊的）
7. **MCP-Apps v1.2.2** - Zod v4互換性、ListServerResources API
8. **MCP Security secops-v0.7.0** - Rule Exclusions管理ツール
9. **Agent Starter Pack v0.39.2** - GKEデプロイターゲット、CLIバナー刷新
10. **Cloud Run MCP v1.10.0** - クライアント追加、統合テスト拡充
11. **gcloud-mcp** - backupdr-mcp v0.1.0 新規追加
12. **x402 Python v2.3.0** - MCP Transport安定化
13. **Google Analytics MCP v0.2.0** - ADKスキーマ修正、pipx対応

### 新規プロトコル統合

1. **AG-UI + Claude Agent SDK** - Claude Agent SDK インテグレーション (#916)
2. **AG-UI + Langroid** - Langroid フレームワーク統合
3. **A2UI + MCP Apps** - A2UI に MCP Apps を統合 (#748)
4. **gcloud-mcp + Backup DR** - backupdr-mcp v0.1.0 新規サーバー

### セキュリティ更新

- **MCP Security v0.7.0**: Rule Exclusions 管理ツール追加
- **MCP**: ブログサイトSEO改善、クライアント機能サポート更新
- **Cloud Run MCP v1.10.0**: Hono 4.12.7 依存関係更新
- **ADK Python v1.27.0**: AuthProviderRegistry、OpenTelemetry ツール実行エラーコードキャプチャ
- **x402**: ERC-7710 サポート仕様、Signed Offer & Receipt Extension（ドラフト）
