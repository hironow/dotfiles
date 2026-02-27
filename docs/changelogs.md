# プロトコル変更ログ

最終更新: 2026-02-27

各プロトコル・Google Cloud サブモジュールの主要な変更点をまとめたドキュメント。

---

## プロトコル (Protocols)

### A2A (Agent-to-Agent)

**現行バージョン**: v1.0.0-rc (Release Candidate, 2026-01-29)

#### v1.0.0-rc の主要な変更点

- **ガバナンス文書化**: GOVERNANCE.md 追加、プロジェクトガバナンス体制の明文化
- **マルチテナンシー**: gRPC リクエストにネイティブ `tenant` フィールド追加
- **プロトコルバージョニング**: 各 `AgentInterface` が独自のプロトコルバージョンを指定
- **mTLS セキュリティ**: SecuritySchemes に mTLS 追加、Agent Card 検証用 JWS 署名
- **拡張カード取得**: `GetExtendedAgentCard` メソッド追加（旧 `getAuthenticatedExtendedCard`）
- **タスクタイムスタンプ**: Task オブジェクトに `createdAt`/`lastModified` フィールド追加
- **Extensions サポート**: メッセージ・アーティファクトに `extensions[]` 配列追加
- **Task List Method**: `tasks/list` メソッドでカーソルベースページネーション付きタスク取得・フィルタリング (#831)
- **OAuth 2.0 近代化**: implicit/password フロー削除、Device Code (RFC 8628)/PKCE 追加 (#1303)
- **3プロトコルバインディング**: REST, gRPC, JSON-RPC の等価仕様の正式策定
- **American Spelling**: "cancelled" → "canceled" 統一 (#1283)
- **Part構造簡素化**: FilePart/DataPart のフラット化
- **仕様ドキュメント改善**: Proto Table表示のライブラリ活用 (#1427)、MTLS スキーマ修正 (#1462)、ストリーミング例修正 (#1458)
- **v0.3.0→v1.0 変更ドキュメント**: 移行ガイド追加 (#1436)
- **DeepLearning.AI コース**: README とドキュメントにコースリンク追加 (#1469)

#### RC後の改善

- **仕様修正**: reserved フィールド削除、タグ順序修正
- **ドキュメント**: What's New in V1、life-of-a-task 例の追加
- **ビルド改善**: Go 1.25 互換性対応

#### 破壊的変更（v0.3.0 → v1.0.0-rc）

| 変更 | 影響 |
|------|------|
| ID形式簡素化: 複合ID (`tasks/{taskId}`) → 単純UUID/リテラル (#1389) | リクエストID形式の変更 |
| Enum フォーマット: `lowercase` → `SCREAMING_SNAKE_CASE` (例: `"completed"` → `"TASK_STATE_COMPLETED"`) (#1384) | 全Enum値の変更 |
| HTTP URL簡素化: `/v1/` プレフィックス削除 (例: `/v1/message:send` → `/message:send`) | エンドポイント URL の変更 |
| Well-Known URI: `agent.json` → `agent-card.json` (#841) | エンドポイント URL の変更 |
| `protocolVersion` が `AgentInterface` に移動 | Agent Card 構造の変更 |
| カーソルベースページネーション（ページベースから変更） | ListTasks API の変更 |
| Message `kind` フィールド削除（JSONメンバーベース判別へ） | メッセージ構造の変更 |
| OAuth implicit/password フロー削除 (#1303) | 認証フロー変更 |
| Push Notification: `config` → `configs`（複数形） | フィールド名変更 |
| `extendedAgentCard` → `AgentCapabilities` に移動 (#1307) | Agent Card 構造の変更 |

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

- **フレームワーク非依存データレイヤー**: Web コアライブラリのフレームワーク非依存データレイヤー実装
- **カタログリネーム**: `standard_catalog` → `basic_catalog` にリネーム
- **CallFunctionMessage**: `CallFunctionMessage` と `functionResponse` の追加
- **エージェント開発ガイド**: Agent SDK を活用したエージェント開発ガイド
- **スキーマパッケージング**: スキーマのパッケージングとランタイムローディング実装 (#555)
- **A2UI Validator**: ロードされたサンプルの検証機能 (#557)
- **Theme バリデーション**: カタログスキーマ参照によるテーマバリデーションリファクタ (#621)
- **TypeScript `declare` キーワード**: エクスポートインターフェースへの `declare` 追加 (#617, #616)
- **CODEOWNERS ファイル**: コードオーナーシップ定義 (#618)
- **Python バリデーション関数**: 基本的なバリデーション関数追加 (#624)
- **カタログドキュメント**: スキーマベースバリデーション付きカタログドキュメント追加

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

#### 参考リンク

- [ADP Protocol](https://github.com/neulab/agent-data-protocol)

---

### AG-UI (Agent-User Interaction Protocol)

**現行バージョン**: 継続的デプロイ（バージョンタグなし）

#### 主要な変更点

- **LRO ツールコール ID リマッピング**: SSE ストリーミングでの Long-Running Operations ツールコール ID リマッピング
- **REASONING イベント移行**: `THINKING_*` イベントから `REASONING_*` イベントへの移行（LangGraph）
- **AG2 Dojo 統合**: AG2 Dojo インテグレーション追加 (#1121)
- **Python UV 移行**: 大半の Python パッケージが UV パッケージマネージャーに移行 (#1130)
- **adk-middleware v0.5.0**: ミドルウェアリリース (#1125)
- **Gemini 3+ ストリーミング関数呼び出し**: ADK Middleware でのストリーミング関数呼び出し引数サポート (#1117)
- **CI パフォーマンス改善**: CI plus ultra 速度改善 (#1144)
- **Reasoning Spec**: 推論仕様追加 (#1050)
- **Kotlin SDK v0.2.7**: バージョン更新、macOS ランナーでの公開 (#1103)
- **Ruby SDK**: フルプロトコル実装 (#865)
- **マルチモーダル仕様**: multimodal spec 追加 (#1084)
- **NX 移行**: Turbo から NX へビルドシステム移行 (#1092)
- **Dart SDK v0.1.0**: フルプロトコル実装、SSEストリーミング、イベントハンドリング
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
- **CONTRIBUTING.md**: コントリビューションガイド追加
- **採用カルーセル更新**: Laravel Boost, Emdash, OpenHands, Junie, Qodo, VT Code, Ona, Autohand Code, Roo Code, Mistral Vibe, pi, Firebender, Piebald, Command Code, Databricks, Mux 追加
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

**現行バージョン**: 2025-11-25

#### 主要な変更点

- **SDK 階層評価**: Python SDK Tier 1, C# SDK Tier 1, Java SDK Tier 2, Swift SDK Tier 3, PHP SDK Tier 3 の評価追加
- **MCP Apps Copilot 統合**: Copilot での MCP Apps クライアントサポート
- **ext-apps ドキュメント URL 更新**: 新サブドメインへの移行
- **実験的タスク機能**: アプリケーション駆動（リクエスター駆動）タスクアーキテクチャ、ポーリング付き状態追跡
- **タスクライフサイクル**: "Getting Tasks"/"Polling Tasks" ガイダンス、TTL 明確化
- **セキュリティ強化**: 外部認証サポート付き認可仕様の強化、GitHub Security Advisories 統合
- **OpenID Connect Discovery 1.0**: 認可サーバーディスカバリー対応
- **アイコンサポート**: ツール、リソース、リソーステンプレート、プロンプトにアイコン追加
- **インクリメンタルスコープ同意**: `WWW-Authenticate` ヘッダー経由
- **ツール命名ガイダンス**: ツール名の規約追加
- **EnumSchema 拡張**: titled/untitled、single-select/multi-select enum 対応
- **URL Mode Elicitation** (SEP-1036): ブラウザ経由の安全なクレデンシャル収集
- **Sampling with Tools** (SEP-1577): サンプリングリクエストで `tools`/`toolChoice` パラメータ
- **OAuth Client ID Metadata Documents**: クライアント登録用
- **OAuth Client Credentials** (SEP-1046): M2M 認可サポート
- **SDK 階層システム** (SEP-1730): 明確な要件付き
- **ガバナンス構造化**: Working Groups / Interest Groups フレームワーク
- **Extensions フレームワーク** (SEP-2133, Final): 拡張機能ケイパビリティのスキーマ追加
- **MCP Apps サポート拡大**: Claude Desktop, ChatGPT, MCPJam, Postman, VSCode, goose, Copilot でのクライアントサポート
- **ガバナンス継承手続き** (SEP-2085, Final): ガバナンスの承継と修正手続き
- **SSRF セキュリティ**: SSRF 対策ドキュメント追加
- **MCP Apps CSP**: アンバンドルアセット向け Content Security Policy 要件文書化
- **Implementation `description`**: Implementation インターフェースにオプション `description` フィールド追加
- **RFC 3339 タイムスタンプ**: ISO 8601 準拠の明確化

#### マイナーアップデート

- Stderr ロギング明確化（stdio transport）
- HTTP 403 Forbidden（無効な Origins）の明確化
- SSE ストリームポーリングサポート
- JSON Schema 2020-12 をデフォルトダイアレクトに
- RFC 9728 OAuth 2.0 Protected Resource Metadata 準拠
- Elicitation のプリミティブ型デフォルト値サポート
- 各言語向けロギングガイダンスのテーラリング (#1970)

#### 参考リンク

- [MCP Specification](https://spec.modelcontextprotocol.io/)

---

### MCP-Apps

**現行バージョン**: v1.1.2

#### v1.1.x の主要な変更点

- **downloadFile 機能**: App → AppBridge 統合テスト付き `downloadFile` 機能追加
- **PDF Server 強化**: 堅牢なパスバリデーション、フォルダ/ファイルルートサポート、ドメイン許可リスト廃止・HTTPS 必須化
- **MCPB パッケージング**: pdf-server 用 MCPB パッケージングと Claude Code プラグイン
- **audio/video サポート**: basic-host での audio/video サポート修正
- **ドキュメント URL 更新**: `apps.extensions.modelcontextprotocol.io` ドメインへの移行
- **Sheet Music App**: `audioSession.type` を playback に設定

#### 未リリースの変更点

- **SECURITY.md 追加**: GitHub Security Advisories ガイダンス (#472)
- **npm start:stdio 修正**: サンプルサーバーの `npm run start:stdio` 修正 (#507)

#### v1.0.1 の主要な変更点

- **npm 参照修正**: ext-apps 依存の npm 参照修正
- **Zod v4 対応**: zod を v4.x に更新
- **MCP SDK ピン留め**: say-server で main ブランチではなくリリース版 MCP を使用
- **qr-server 安定化**: PyPI 安定版 MCP SDK 使用に移行
- **二重接続ガード**: プロトコルメッセージ処理エラー防止 (#450)
- **サンプル依存関係更新**: 全サンプルアプリケーションの package.json 一貫性改善

#### 参考リンク

- [MCP-Apps](https://github.com/anthropics/mcp-apps)

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

**現行バージョン**: 継続的デプロイ（バージョンタグなし）

#### 主要な変更点

- **Databricks コミュニティ追加**: コミュニティセクションにロゴ追加
- **logprobs オプション化**: logprobs をオプショナルに変更 (#45)
- **API命名修正**: `Createresponse` → `createResponse` (#40)
- **インラインMarkdownパーサー**: HTML変換用インラインパーサー追加
- **CLI コンプライアンステスト**: `bin/compliance-test.ts` 追加
- **llms.txt リファクタ**: コアコンセプト、API詳細、イベントフォーマット強化
- **Bun 移行**: Node から Bun へパッケージマネージャー変更
- **TypeSpec Prettier プラグイン**: サポート追加

#### 参考リンク

- [OpenResponses](https://github.com/openrouter/openresponses)

---

### UCP (Universal Commerce Protocol)

**現行バージョン**: v2026-01-23

#### v2026-01-23 の主要な変更点

- **リクエスト/レスポンス署名**: UCP プロトコルの暗号署名機能
- **EC カラースキーム**: 埋め込みチェックアウトの `ec_color_scheme` クエリパラメータ (#157)
- **ECP サポート**: E-Commerce Connector Protocol、チェックアウトごとのトランスポート設定
- **Technical Committee → Tech Council**: 名称変更 (#168)
- **Standard Errors**: エラー概念の標準化 (#147)
- **Affirm パートナー追加**: エンドースドパートナーに Affirm 追加 (#166)
- **エンドースドパートナー追加**: Block, Fiserv, Klarna, Splitit (#149)
- **UCP-Agent ヘッダー**: openapi.json に追加
- **Cart Capability**: バスケット構築機能 (#73)
- **Context Intent フィールド**: intent フィールド追加、非識別制約明確化 (#95)
- **マルチ親スキーマ拡張**: 決定論的スキーマ解決 (#96)
- **サービストランスポート定義**: 名前変更とバージョニング (#154)

#### v2026-01-23 後の改善

- **Transition Schema 修正**: UCP transition schema のグレースフルな活用修正 (#196)
- **Checkout ID 非推奨化**: update リクエストで `checkout_id` を `deprecated_required_to_omit` に (#145)
- **`available_instruments`**: payment handler configurations に `available_instruments` 追加 (#187)
- **Checkout.com パートナー追加**: エンドースドパートナーに Checkout.com 追加
- **CODEOWNERS ファイル**: メンテナー定義追加
- **Fulfillment Method 拡張**: update 呼び出しで fulfillment method type/id のオプション指定

#### 破壊的変更

| 変更 | 影響 |
|------|------|
| Checkout スキーマリファクタ (#100) | チェックアウトスキーマの構造変更 |
| Payments/Services/Capabilities 統一階層化 (#49) | 決済・サービス・能力の統一構造へ |
| Complete Checkout スキーマ統一 (#28) | アクション/トランスポート間の統一 |
| `_meta.ucp.profile` 非推奨 | 標準メタデータへの移行 |

#### 参考リンク

- [UCP Protocol](https://github.com/anthropics/UCP)

---

### webmcp-tools

**現行バージョン**: 継続的デプロイ（バージョンタグなし）

**管理**: Google Chrome Labs

#### 主要な変更点

- **マルチバックエンドサポート**: 異なるバックエンドのサポート追加
- **Vercel AI SDK 移行**: 実験的マルチステップツール実行付き Vercel AI SDK への移行
- **Pizza-maker デモ**: Pizza-maker デモとベーシック WebMCP zaMaker Evals 追加
- **Blackjack Agents**: AWESOME_WEBMCP.md に Blackjack Agents セクション追加
- **Awesome WebMCP リスト**: 初期作成
- **Industry Vertical Evals**: ヘルスケア、不動産、商業、旅行の業界別評価追加
- **Chrome Extension v1.6**: 拡張機能バージョン更新 (#14)
- **AGENTS.md**: エージェントドキュメント追加
- **Address Form サンプル**: アドレスフォームのサンプル追加 (#13)
- **Enum Schema**: enum input schema に `type:string` 追加 (#11)
- **Tool Evals Constraints**: ツール評価の引数制約実装 (#10)
- **Model Context Tool Inspector**: サブモジュールとして追加

#### 参考リンク

- [webmcp-tools](https://github.com/AugmentedWeb/webmcp-tools)

---

### x402 (Internet Native Payments)

**現行バージョン**: Go v2.4.1 / Python v2.2.0 / TypeScript Core v2.5.0

#### Go v2.4.x の主要な変更点

- **ルート設定バリデーション**: 初期化時のルート設定検証 (#1364)
- **リトライ with Exponential Backoff**: `GetSupported` の 429 レスポンスに対する指数バックオフリトライ (#1357)
- **ERC20 Gas Sponsorship 拡張**: ガススポンサーシップ拡張実装 (#1336)
- **Facilitator SDK 分離**: 外部チェーン情報の分離 (#1337)
- **v1 チェーンコンテキスト修正**: v2 SDK への v1 チェーンコンテキストリーク修正 (#1345)

#### TypeScript Core v2.5.x の主要な変更点

- **PAYMENT-RESPONSE ヘッダー**: 決済失敗レスポンスに `PAYMENT-RESPONSE` ヘッダー追加 (#1128)
- **ERC20 Gas Sponsorship 拡張**: ガススポンサーシップ拡張実装 (#1328)
- **Permit2 アップグレード**: 最新コントラクト状態に合わせた permit2 実装更新 (#1325)
- **SIWX Settle Hook 修正**: undefined resource に対するガード追加 (#1159)

#### Python v2.2.0 の主要な変更点

- **MCP Transport 統合の安定化**: Python MCP トランスポートの安定化
- **camelCase シリアライゼーション修正**: `BaseX402Model` に `serialize_by_alias=True` 追加、仕様準拠の camelCase 出力がデフォルト化 (#1122)
- **LocalAccount 自動ラップ**: `eth_account` の `LocalAccount` を `ExactEvmScheme` に渡す際の自動ラップ (#1122)
- **SVM V1 クライアント署名修正**: `VersionedTransaction.populate()` で明示的署名スロット指定による "not enough signers" エラー修正

#### 共通の変更点

- **MCP Transport 統合**: x402 ペイメントプロトコルの MCP トランスポート統合（Go, Python, TypeScript）
- **x402MCPClient/Server**: ミドルウェアとサンプル付き実装
- **EIP-2612 Gas Sponsorship**: ガススポンサーシップ拡張実装
- **Payment Identifier Extension SDK**: Python, Go, TypeScript の全プラットフォームサポート (#1111)
- **MegaETH メインネット**: Chain ID 4326、USDM デフォルトステーブルコイン
- **SVM トランザクションユニーク性**: memo instruction にランダム nonce 追加で重複防止
- **E2E テスト**: MCP トランスポートの E2E テスト（TypeScript, Python, Go） (#1149)

#### エコシステムパートナー（新規追加）

- Tollbooth（OSS x402 API ゲートウェイ）, Kurier, Laso Finance, xpay Facilitator
- DJD Agent Score, QuantumShield API, V402Pay
- MerchantGuard, x402engine, RelAI Facilitator, ouchanip, invy, KAMIYO
- Foldset, Moltalyzer, clawdvine (旧 imagine), AsterPay
- Agnic.AI, Postera

#### 参考リンク

- [x402 Protocol](https://github.com/x402-protocol/x402)

---

## Google Cloud / ADK

### ADK Python

**現行バージョン**: v1.26.0 (2026-02-26)

#### v1.26.0 の主要な変更点

- **Agent Registry**: ADK にエージェントレジストリ追加
- **Skills 仕様準拠**: Agent Skills 仕様のバリデーション、エイリアス、スクリプト、自動インジェクション対応
- **`load_skill_from_dir()` メソッド**: ディレクトリからのスキル読み込みメソッド追加
- **A2A インターセプター**: `A2aAgentExecutor` にインターセプターフレームワーク追加
- **Apigee LLM 統合**: `/chat/completions` 統合とストリーミングサポート
- **User Personas**: 評価フレームワークにユーザーペルソナ導入
- **ID Token サポート**: OAuth2 credentials でのネイティブ `id_token` サポート、`ServiceAccountCredentialExchanger` での ID トークン交換
- **OpenTelemetry トレースコンテキスト**: MCP ツール呼び出しに OpenTelemetry トレースコンテキスト追加
- **BigQuery Agent Analytics 強化**: スキーマ自動アップグレード、ツールプロバナンス、HITL トレーシング
- **Memory URI サポート**: CLI run コマンドでメモリサービス URI サポート
- **トークンコンパクション改善**: イントラ呼び出しコンパクションとリクエスト前トークンコンパクション
- **FastAPI DI**: エージェントローダーの依存関係注入

#### v1.26.0 バグ修正

- **OpenAI strict JSON schema**: LiteLLM での strict JSON schema 強制
- **セッションバリデーション**: ストリーミング前のセッション検証
- **カスタム genai Client**: カスタム `google.genai.Client` インジェクションサポート
- **ストリーミングツール入力**: ストリームパラメータ検出の修正
- **Pydantic 下限緩和**: 最小バージョン 2.7.0 に引き下げ
- **LiteLLM 1.81+ 互換性**: ストリーミングレスポンスパース修正

#### v1.25.1 の主要な変更点

- **McpSessionManager 修正**: ピクリングロックエラーの修正（並行セッション操作時のシリアライゼーション問題）

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

#### 破壊的変更

| 変更 | 影響 |
|------|------|
| credential manager が `tool_context` を受け取るよう変更 (v1.24.0) | `callback_context` から `tool_context` への引数変更 |
| OpenTelemetry BigQuery プラグイントレーシング移行 (v1.23.0) | カスタム ContextVar からの移行 |

#### 参考リンク

- [ADK Python](https://github.com/google/adk-python)

---

### ADK Go

**現行バージョン**: v0.5.0 (2026-02-20)

#### v0.5.0 の主要な変更点

- **OpenTelemetry Semconv Tracing**: セマンティック規約に基づくトレーシング完全実装
- **Debug Endpoints v2**: GCP quota/resource project バリデーション付きデバッグエンドポイント
- **Retry and Reflect プラグイン**: リトライ・リフレクションプラグイン追加
- **Logging プラグイン**: ロギングプラグイン追加
- **Function Call Modifier プラグイン**: 関数呼び出し変更プラグイン
- **Preload Memory ツール**: メモリプリロードサポート
- **コンソールリファクタ**: コンソール UI の刷新

#### v0.5.0 バグ修正

- Flaky トレーシングテストの修正
- Gemini 2.5 以下の LLM バリアント対応
- 非追記タスクアーティファクト更新時の集約テキスト・思考のクリア修正
- `InvocationId` 複製時の置換問題修正
- temp state デルタのローカルセッション内適用修正
- リモートエージェントの部分レスポンスデータ重複修正

#### v0.4.0 の主要な変更点

- **`WithContext` メソッド**: `agent.InvocationContext` でコンテキスト変更 (#526)
- **Human-in-the-Loop 確認**: MCP ツールセットでの確認メカニズム (#523)
- **Load Memory ツール**: メモリ検索ツール追加 (#497)
- **セッションイベントアクセス**: executor コールバックからセッションイベント取得 (#521)
- **カスタムパートコンバーター**: ADK Executor 対応 (#512)
- **プラグインシステム強化**: launcher config でプラグイン対応
- **FilterToolset ヘルパー**: ツールセットフィルタリング
- **OpenTelemetry 改善**: `gen_ai.conversation.id` を OTEL スパンに含める
- **Vertex AI Session Service**: サポート追加
- **Web Server Graceful Shutdown**: コンテキストキャンセルによる優雅な停止

#### 参考リンク

- [ADK Go](https://github.com/google/adk-go)

---

### ADK JS

**現行バージョン**: v0.4.0 (2026-02-25)

#### v0.4.0 の主要な変更点

- **Database Session Service**: データベースセッションサービス追加
- **ApigeeLlm**: TypeScript ADK に Apigee LLM 追加
- **ESM ネイティブ CLI**: CommonJS から ESM への移行
- **AdkApiClient サービス**: API クライアントサービス追加
- **AdkWebServer → AdkApiServer**: リネーム
- **FileArtifactService**: ファイルアーティファクトサービス追加
- **A2A ↔ GenAI パーツ変換**: A2A と GenAI 間のパーツ変換ユーティリティ
- **Event Case Conversion**: snake_case ↔ camelCase イベント変換ユーティリティ
- **`pauseOnToolCalls` 設定**: エージェント命名バリデーション緩和と新設定
- **Session Service Registry**: CLI 連携

#### v0.4.0 バグ修正

- `set tools` と `outputSchema` の同時使用制限撤廃
- LlmAgent での state 永続化修正
- Runner ストリーミングとステートレス実行の実装
- リクエストボディパラメータ（state/state delta）の処理改善

#### v0.3.0 の主要な変更点

- **カスタムロガー**: `setLogger()` 関数によるカスタムロガーサポート
- **MCP Session Manager Headers**: `headers` オプション追加（旧 `header` オプション非推奨）
- **Zod v3/v4 サポート**: 両バージョンのサポート
- **rootAgent getter 修正**: Python SDK 動作との一致

#### 参考リンク

- [ADK JS](https://github.com/google/adk-js)

---

### Agent Starter Pack

**現行バージョン**: v0.38.0 (2026-02-19)

#### v0.38.0 の主要な変更点

- **enhance コマンド改善**: バグ修正と UX 改善
- **Gemini 3 Flash Preview**: 評価ジャッジモデルとして統合
- **GitHub Actions リファクタリング**: ビルド自動化の改善
- **Vertex AI Search/Vector Search**: agentic_rag モジュール向けデータコネクター追加
- **エージェント選択 UI**: "Other Languages" サブメニューによる非Python エージェントのグルーピング
- **設定可能なエージェントガイダンスファイル名**: ファイル名のカスタマイズ対応

#### v0.36.0 の主要な変更点

- **smart-merge**: enhance コマンドにスマートマージ機能追加 (#784)
- **Java ADK ドキュメント更新**: ADK Java 向けドキュメント改善 (#785)
- **Zod バージョン整合**: TypeScript テンプレートで `@google/adk` 依存と Zod バージョンを整合 (#779)

#### 参考リンク

- [Agent Starter Pack](https://github.com/GoogleCloudPlatform/agent-starter-pack)

---

### Cloud Run MCP

**現行バージョン**: v1.9.0 (2026-02-23)

#### v1.9.0 の主要な変更点

- **依存関係更新**: Hono v4.12.0、AJV v8.18.0、fast-xml-parser 更新

#### v1.8.0 の主要な変更点

- **OAuth サポート**: OAuth 認証統合 (#214)
- **OAuth URL サポート**: OAuth 関連の GET URL 追加
- **OAuth 利用手順**: OAuth ワークフロー実装の手順追加 (#219)
- **トークンベースクライアント**: token-based clients サポート (#206)
- **SubmitBuild API**: デプロイ/ビルド時間の改善 (#198)
- **クライアント生成リファクタ**: 生成処理の改善 (#201)
- **MCP SDK v1.26.0**: 依存関係更新 (#216)

#### セキュリティ修正

- hono パッケージの脆弱性修正 (#215)
- lodash 4.17.23 へアップグレード (#209)
- qs 6.14.2 へアップグレード (#218)
- fast-xml-parser 更新 (#220)

#### 参考リンク

- [Cloud Run MCP](https://github.com/GoogleCloudPlatform/cloud-run-mcp)

---

### gcloud-mcp

**現行バージョン**: gcloud-mcp-v0.5.3 / storage-mcp-v0.3.3 / observability-mcp-v0.2.3

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

#### 未リリースの変更点

- **Docker イメージサポート**: Docker イメージのサポート追加 (#183)
- **Go 1.25.7**: Go バージョン更新 (#182)

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

#### 未リリースの変更点

- **Google ADK 移行**: MCP を Google ADK ベースに移行 (#107)
- **nox 2025.11.12 対応**: フォーマットファイル更新

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

**現行バージョン**: secops-v0.5.3

#### v0.5.3 の主要な変更点

- **Investigation 管理ツール**: 調査管理ツール追加（422行の新コード） (#220)
- **Watchlist 管理ツール**: ウォッチリスト管理ツール追加 (#222)
- **Advanced Rule Operations**: 高度なルール操作追加 (#229)
- **キュレーテッドルール管理ツール**: retrohunt とアラート検索ツール追加 (#227)

#### v0.5.2 の主要な変更点

- **Remote MCP サーバー**: リモート MCP サーバー実装とドキュメント (#215)
- **Gemini CLI 拡張**: google-secops Gemini CLI extension、スキルとドキュメント追加
- **スキル再構成**: runbook をスキルにインライン化、setup スキルをクライアント別に分離
- **Adaptive Execution ドキュメント**: 追加
- **gsutil 移行**: `gsutil` → `gcloud storage` コマンド移行
- **非推奨JSONキー削除**: disabled, autoApprove キーのドキュメント/設定からの削除 (#228)

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

#### 未リリースの変更点

- **Looker ディレクトリ管理**: ディレクトリの一覧・作成・削除ツール (#2488)
- **Oracle DML 有効化**: Oracle DML 操作の有効化と配列型エラー修正 (#2323)
- **GDA Cloud Go SDK 移行**: GDA ソースの Cloud Go SDK 使用リファクタ (#2313)
- **Redis TLS サポート**: Redis 接続の TLS サポート追加 (#2432)
- **PostgreSQL pgx クエリ実行モード**: 設定可能なクエリ実行モード (#2477)
- **UI ツールリストパネル**: リサイズ可能に (#2253)
- **Pre/Post Processing ドキュメント**: 多言語ドキュメント追加
- **Go SDK ドキュメント更新**: リファクタ後の SDK ドキュメント (#2479)

#### v0.26.0 の主要な変更点

- **User-Agent Metadata フラグ**: 新規追加 (#2302)
- **MCP レジストリフラグ**: MCP registry サポート
- **MCP specs 2025-11-25**: 最新仕様対応 (#2303)
- **`valueFromParam`**: Tool config サポート (#2333)
- **`embeddingModel`**: MCP handler でサポート (#2310)
- **BigQuery 設定可能化**: 最大行数設定 (#2262)
- **Cloud SQL**: backup/restore ツール追加 (#2141, #2171)
- **Snowflake 統合**: ソースとツール統合 (#858)

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
| **A2A** | v1.0.0-rc: Enum SCREAMING_SNAKE_CASE化、ID簡素化、URL変更、OAuth等 | 高 |
| **GenAI Toolbox** | v0.27.0: 設定ファイル v2、OTEL テレメトリ更新 | 高 |
| **UCP** | v2026-01-23: Checkout スキーマリファクタ、Payments 統一階層化 | 高 |
| **ACP** | v2026-01-30: Payment Handlers Framework 導入、fulfillment 構造変更 | 高 |
| **MCP-UI** | v6.0.0 で MCP Apps へ移行、MIME タイプ変更 | 高 |
| **ADK Python** | v1.24.0: credential manager 引数変更、v1.23.0: OTEL BigQuery 移行 | 高 |
| **GenAI Toolbox** | v0.26.0: Tool naming validation 強制化 | 中 |
| **Google Analytics MCP** (未リリース) | パッケージ名 `analytics-mcp` にリネーム | 低 |

### メジャーアップデート

1. **ADK Python v1.26.0** - Agent Registry、Skills仕様準拠、A2Aインターセプター、Apigee LLM統合、User Personas
2. **ADK Go v0.5.0** - OpenTelemetry Semconv Tracing、Retry/Reflectプラグイン、Debug Endpoints v2
3. **ADK JS v0.4.0** - Database Session Service、ApigeeLlm、ESM ネイティブ CLI、FileArtifactService
4. **x402 Go v2.4.1 / TS Core v2.5.0 / Python v2.2.0** - ERC20 Gas Sponsorship拡張、Permit2アップグレード、リトライ機構
5. **MCP-Apps v1.1.2** - downloadFile機能、PDF Server強化、MCPB パッケージング
6. **MCP Security secops-v0.5.3** - Investigation管理、Watchlist管理、Advanced Rule Operations
7. **Cloud Run MCP v1.9.0** - 依存関係更新と安定化
8. **A2A v1.0.0-rc** - エンタープライズ標準化、マルチテナンシー、3プロトコルバインディング
9. **ACP v2026-01-30** - Capability Negotiation、Payment Handlers、Extensions Framework
10. **GenAI Toolbox v0.27.0** - 設定ファイル v2（破壊的変更）、CLI 直接ツール呼び出し、Agent Skills 生成

### セキュリティ更新

- **MCP**: SSRF 対策ドキュメント追加、GitHub Security Advisories 統合
- **Cloud Run MCP**: hono / lodash / qs / fast-xml-parser の脆弱性修正
- **GKE MCP**: Workload Security スキル追加
- **MCP Security**: Investigation/Watchlist管理、キュレーテッドルール管理ツール、Remote MCP、gsutil 移行
- **ADK Python**: クレデンシャルキー生成の安定化とクロスユーザーリーク防止、ID トークンサポート
- **x402**: SIWX Settle Hook の undefined resource ガード追加
