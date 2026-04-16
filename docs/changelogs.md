# プロトコル変更ログ

最終更新: 2026-04-17

各プロトコル・Google Cloud サブモジュールの主要な変更点をまとめたドキュメント。

---

## プロトコル (Protocols)

### A2A (Agent-to-Agent)

**現行バージョン**: v1.0.0 (2026-03-12)

#### v1.0.0 後の変更点

- **Rust SDK 公式化**: 公式 SDK リストに Rust SDK 追加 (#1729)
- **TSC メンバー追加プロセス**: GOVERNANCE.md に TSC メンバー追加方法ドキュメント追加 (#1571)
- **仕様修正**: トランスコーディング関連エラーの修正 (#1627)
- **コードスニペットマーカー更新**: リファクタ後のサンプル識別子に合わせたマーカー更新 (#1732)

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

#### 未リリースの変更点

- **v0.9 レンダラーアイコンオーバーライド**: v0.9 レンダラーにアイコン名オーバーライド追加 (#1146)
- **Angular Restaurant Sample v0.9 移植**: Angular Restaurant サンプルの v0.9 移植 (#1189)
- **サーバーエラー伝播修正**: Angular restaurant サンプルでのサーバーエラー伝播修正 (#1203)
- **レンダラーパッケージバージョンバンプ**: alpha.3 へのバージョンバンプ (#1178)
- **A2UI Theater**: インタラクティブ JSONL プレイバック＆ストリーミングビューア (#987)
- **A2A SSE ストリーミング**: サーバーサイドストリーミング実装＆SSE レスポンス対応 (#1049)
- **concurrent surface サポート**: root ID 追跡による並行サーフェスサポート (#1037)
- **Agent SDK 開発ガイド**: 他言語向け Agent SDK 開発ガイド追加 (#1052)
- **パッケージリネーム**: `a2ui-agent-sdk` への動的バージョニング＆リネーム (#1046)
- **Python SDK 改善**: Python SDK の改善
- **依存関係更新 (CVE)**: google-adk 1.20.0 の CVE 対応を含む依存関係更新
- **MCP Apps 統合**: A2UI に MCP Apps を統合 (#748)
- **React レンダラー**: React レンダラー実装 (#542)
- **Angular v0.9 レンダラー**: Angular v0.9 Renderer 実装

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

#### 参考リンク

- [A2UI Specification](https://github.com/google/A2UI)

---

### ACP (Agentic Commerce Protocol)

**現行バージョン**: API Version 2026-01-30

**管理**: OpenAI & Stripe

#### 未リリースの変更点

- **TSC Operating Model**: TSC 運営モデルドキュメント追加 (#184)
- **CLA 署名者追加**: Meta Platforms, Affirm が CLA 署名
- **`risk_signals` 仕様修正**: `delegate_payment` で空の risk_signals を許可 (#214)
- **ガバナンスモデル改訂**: TSC, DWGs を含むガバナンス構造の見直し
- **Webhook Signing Replay Protection 強化**: リプレイ攻撃防止の強化 (#160)
- **Delegated Authentication API**: マーチャント指定認証の API コントラクト (#93)
- **Discovery Well-Known Document 実装**: Well-Known ドキュメントの実装
- **MCP Transport Binding**: Agentic Checkout 向け MCP トランスポートバインディング

#### v2026-01-30 の主要な変更点

- **Capability Negotiation**: エージェントとセラー間の機能ネゴシエーション
- **Payment Handlers Framework**: 構造化された支払いハンドラー（**破壊的変更**）
- **Extensions Framework**: オプション・コンポーザブルな拡張機能
- **Discount Extension**: リッチな割引コードサポート（初のACP拡張）

#### 破壊的変更

| 変更 | 影響 |
|------|------|
| Payment Handlers 導入 (v2026-01-30) | 支払い方法IDから構造化ハンドラーへ移行必須 |
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

**現行バージョン**: release/2026-04-15

#### 未リリースの変更点（release/2026-04-15 以降）

- **State Snapshot/Delta コンパクション**: run 単位で STATE_SNAPSHOT と STATE_DELTA イベントを単一の最終状態に圧縮、fast-json-patch (RFC 6902) によるデルタ適用 (#1535)
- **LangGraph prepareRegenerateStream config 転送修正**: `prepareRegenerateStream` で `assistantConfig` と forwarded config を正しくマージするよう修正 (#1509)
- **Python wheel パーミッション修正リバート**: 壊れた wheel ビルドを起こしていたパーミッション修正のリバート (#1508)

#### release/2026-04-15 の主要な変更点

- **AWS Strands パッケージバンプ**: AWS Strands パッケージバージョン更新 (#1531)
- **AWS Strands kwargs 転送修正**: シグネチャイントロスペクションによる per-thread エージェントへの全 template kwargs 転送 (#1529)
- **LangGraph パッケージバンプ**: LangGraph 統合パッケージバージョン更新 (#1530)
- **CVE-2026-25528 セキュリティ修正**: 依存関係バージョンバンプによるセキュリティ脆弱性修正 (#1527)
- **ツール連続実行時の状態ストリーミング修正**: ツールが連続実行される際に state がストリーミングされない問題修正 (#1526)
- **A2UI ミドルウェア v0.9 対応**: v0.9 インラインカタログスキーマフォーマット対応
- **ADK getCapabilities 実装**: ADKAgent に `getCapabilities()` と `/capabilities` エンドポイント追加 (#1475)
- **ADK Dependabot 脆弱性修正**: adk-middleware の critical/high 脆弱性修正 (#1517)
- **ADK セッション冗長スキャン排除**: 冗長なセッションスキャンの排除と古い tool-call クリーンアップ修正 (#1514, #1515, #1516)
- **マルチインスタンスセッションキャッシュ hydration**: マルチインスタンスキャッシュの修正 (#1484)
- **Kotlin Ktor 3.2.4 アップグレード**: Ktor 3.1.3 → 3.2.4 (#1520)
- **reasoning/thinking イベント**: multi-agent サポート、イベントスロットルミドルウェア (#1427)
- **BinaryInputContent 後方互換ミドルウェア**: レガシー BinaryInputContent 互換ミドルウェア追加 (#1422)
- **Strands.py v0.1.5**: Strands.py リリース

#### release/2026-03-28 の主要な変更点

- **リリース自動化**: リリース自動化パイプライン統合
- **ADK ミドルウェア O(1) 最適化**: ADK ミドルウェアのルックアップパフォーマンス改善

#### 以前の主要な変更点

- **Claude Agent SDK 統合**: Claude Agent SDK インテグレーション追加 (#916)
- **Langroid 統合**: Langroid フレームワーク統合と Dojo デモアプリ統合
- **Bedrock Converse API 互換性**: LangGraphAgent での Bedrock Converse API 互換性修正 (#1300)
- **Reasoning Spec**: 推論仕様追加 (#1050)
- **マルチモーダル仕様**: multimodal spec 追加 (#1084)
- **Ruby SDK**: フルプロトコル実装 (#865)
- **Dart SDK v0.1.0**: フルプロトコル実装
- **フレームワーク統合**: LangGraph, Mastra, CrewAI 対応
- **状態管理**: JSON Patch デルタ (RFC 6902) サポート

#### 参考リンク

- [AG-UI Protocol](https://github.com/ag-ui-protocol/ag-ui)

---

### AgentSkills

**現行バージョン**: 継続的デプロイ（バージョンタグなし）

**管理**: Anthropic

#### 最近の変更点

- **Workshop.ai クライアント追加**: Workshop.ai をクライアントショーケースに追加 (#314)
- **nanobot クライアント追加**: nanobot をクライアントショーケースに追加 (#315)
- **Client Showcase ページ**: Web ベースのクライアントショーケースページ追加 (#291)
- **シャッフル/アルファベット切替**: ClientShowcase にシャッフル/アルファベット順トグル追加

#### 主要な変更点

- **Discord リンク追加**: README とドキュメントに Discord リンク追加
- **Kiro ロゴ追加**: Kiro ロゴ追加
- **ランタイムバージョン例**: 互換性フィールドにランタイムバージョン例追加
- **クイックスタートガイド**: スキル作成者向けクイックスタートガイド追加
- **ベストプラクティスガイド**: スキル作成者向けベストプラクティスガイド追加 (#224)
- **Apache 2.0 ライセンス**: トップレベル LICENSE 追加 (#122)

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

#### 参考リンク

- [AP2 Protocol](https://github.com/google-agentic-commerce/AP2)

---

### MCP (Model Context Protocol)

**現行バージョン**: 2025-11-25

#### 未リリースの変更点

- **HTTP Standardization (SEP-2243)**: HTTP トランスポートの標準化マージ
- **Deterministic tools/list ordering**: ツールリストの決定的順序仕様追加
- **Tool-name disambiguation**: ツール名の曖昧さ排除の明確化
- **Skills Over MCP IG**: Skills Over MCP Interest Group チャーター策定
- **Inspector V2 WG**: Inspector V2 ワーキンググループチャーター策定
- **mcpc CLI クライアント更新**: MCP CLI クライアントの新機能対応 (#2576)
- **SEP-2207 OIDC リフレッシュトークンガイダンス**: OIDC フレーバーのリフレッシュトークンガイダンス追加 (#2207)
- **Ruby SDK ドキュメント**: build-client ドキュメントに Ruby SDK サンプル追加 (#2486)
- **SEP-2350 クライアントサイドスコープ蓄積**: ステップアップ認可におけるクライアントサイドスコープ蓄積の明確化 (#2350)
- **TypeScript 6.0.2**: TypeScript 5.9.3 → 6.0.2 へのバンプ (#2503)

#### 主要な変更点

- **Extensions トップレベルタブ**: Extensions を専用ページ付きトップレベルタブに昇格 (#2263)
- **SDK 階層評価**: Python SDK Tier 1, C# SDK Tier 1, Go SDK Tier 1, Java SDK Tier 2, Swift SDK Tier 3, PHP SDK Tier 3
- **OIDC / エンタープライズ管理認可**: OIDC とエンタープライズ管理認可の更新
- **実験的タスク機能**: アプリケーション駆動タスクアーキテクチャ、ポーリング付き状態追跡
- **Extensions フレームワーク** (SEP-2133, Final): 拡張機能ケイパビリティのスキーマ追加
- **MCP Apps サポート拡大**: Claude Desktop, ChatGPT, MCPJam, Postman, VSCode, goose, Copilot

#### 参考リンク

- [MCP Specification](https://spec.modelcontextprotocol.io/)

---

### MCP-Apps

**現行バージョン**: v1.6.0

#### v1.6.0 の主要な変更点

- **Progress-based timeout reset**: `callServerTool` でプログレスベースのタイムアウトリセット対応 (#600)
- **E2E テスト堅牢化**: 初期 shrink-to-fit ズームのポーリングによるテスト安定化 (#607)

#### v1.5.0 の主要な変更点

- **PDF Server アノテーションラスタライズ**: インポート済みアノテーションのラスタライズ (#593)
- **PDF Server フォームフィールド保存堅牢化**: フォームフィールド save のロバスト性向上 (#591)
- **PDF Server ハイライト/下線/取り消し線インポート**: 既存 PDF からのインポート対応 (#592)
- **PDF Server `get_viewer_state`**: interact アクションに `get_viewer_state` 追加 (#590)
- **PDF Server ズームアウト改善**: fit 以下へのズームアウト許可 (#589)
- **PDF Server フルスクリーン・ピンチズーム**: フルスクリーン時の fit-to-page とピンチズーム (#583)

#### v1.4.0 の主要な変更点

- **PDF Server `save_as` アクション**: interact アクションに `save_as` 追加 (#580)
- **path-to-regexp ReDoS CVE 修正**: v8.3.0 → v8.4.1 (#576)
- **addEventListener/removeEventListener**: DOM モデル `on*` セマンティクス追加 (#573)

#### 参考リンク

- [MCP-Apps](https://github.com/modelcontextprotocol/ext-apps)

---

### MCP-UI

**現行バージョン**: client/v7.0.0 (2026-03-12)

#### v7.0.0 の主要な変更点

- **レガシー仕様削除**: レガシー仕様の完全削除（**破壊的変更**） (#185)

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

#### 最近の変更点

- **AWS パートナー追加**: AWS パートナーロゴ追加 (#67)
- **Red Hat コミュニティ追加**: Red Hat ロゴ追加
- **コアメンテナーリスト更新**: メンテナー管理改善

#### 主要な変更点

- **Llama Stack 統合**: Llama Stack インテグレーション追加 (#29)
- **Databricks コミュニティ追加**: コミュニティセクションにロゴ追加
- **logprobs オプション化**: logprobs をオプショナルに変更 (#45)
- **CLI コンプライアンステスト**: `bin/compliance-test.ts` 追加
- **Bun 移行**: Node から Bun へパッケージマネージャー変更

#### 参考リンク

- [OpenResponses](https://github.com/openresponses/openresponses)

---

### UCP (Universal Commerce Protocol)

**現行バージョン**: v2026-04-08

#### v2026-04-08 の主要な変更点

- **`variant.selected_options` → `options` リネーム**: variant のオプションフィールドリネーム (#353)（**破壊的変更**）
- **Webhook フィールド分離**: dangling webhook フィールドをヘッダーに分離、トランスポートがベーススキーマのみ参照するよう変更 (#342)（**破壊的変更**）
- **UCP エラーコンベンション統一**: 埋め込みプロトコルエラーを UCP エラーコンベンションに統一 (#325)（**破壊的変更**）
- **Get Order オペレーション**: platform-auth 付き Get Order 操作追加 (#276)
- **Order `currency` 必須化**: Order スキーマで currency を必須フィールドに変更 (#283)（**破壊的変更**）
- **Order Capability 更新**: Order capability の更新 (#254)（**破壊的変更**）
- **`signed_amount.json` 使用**: total で signed_amount.json を使用するよう修正 (#299)（**破壊的変更**）
- **Order `label` フィールド**: Order にオプションの `label` フィールド追加 (#326)
- **Identity Linking リバート**: Identity Linking リデザインのリバート (#329)
- **lodash セキュリティ修正**: Trivy 脆弱性修正のための lodash 更新 (#333)
- **Transition Schema クリーンアップ**: バージョンカット準備のための transition schema 整理 (#341)
- **EP core 抽出**: 共有 EP core の抽出とナビゲーションでのトランスポートグルーピング (#339)

#### v2026-01-23 後の改善（v2026-04-08 に含まれる）

- **Embedded Protocol Transport Binding**: カートケイパビリティ向け埋め込みプロトコルトランスポートバインディング＋再認証メカニズム (#244)
- **Product Get Operation**: `catalog.lookup` の get product オペレーション追加 (#195)
- **Discount Capability 拡張**: カートへの割引機能拡張 (#246)
- **Eligibility Claims & Verification**: 適格性主張と検証コントラクト (#250)
- **Authorization & Abuse Signals**: 認可と不正利用シグナルの形式化 (#203)
- **Catalog Search & Lookup**: 製品ディスカバリー用カタログ検索・参照機能 (#55)

#### 破壊的変更

| 変更 | 影響 |
|------|------|
| `variant.selected_options` → `options` (#353) | variant フィールド名変更 |
| Webhook フィールドヘッダー分離 (#342) | トランスポートスキーマ構造変更 |
| EP エラーコンベンション統一 (#325) | エラーレスポンス形式変更 |
| Order `currency` 必須化 (#283) | Order 作成時に currency 必須 |
| Order Capability 更新 (#254) | Order capability 構造変更 |
| `signed_amount.json` 使用 (#299) | total 形式変更 |
| Embedded Protocol Transport Binding (#244) | カートケイパビリティ向けトランスポート＋再認証 |
| Authorization & Abuse Signals (#203) | 認可シグナルの構造変更 |

#### 参考リンク

- [UCP Protocol](https://github.com/Universal-Commerce-Protocol/ucp)

---

### webmcp-tools

**現行バージョン**: 継続的デプロイ（バージョンタグなし）

**管理**: Google Chrome Labs

#### 最近の変更点

- **Flight Search flexible routes**: フライト検索のフレキシブルルート対応
- **Registered purchase 機能**: 登録済み購入機能追加
- **Maze player trail animation 修正**: 迷路プレイヤーの軌跡アニメーション修正
- **Label `for` attribute オプション**: アクセシビリティ改善
- **依存関係更新**: Hono 4.12.14、basic-ftp 等の更新

#### 主要な変更点

- **Order Tracking 宣言的デモ**: オーダートラッキングの宣言的デモ追加
- **Ticket Booking サポート**: チケット予約サポート追加
- **webmcp-maze デモ**: 新規迷路デモプロジェクト追加
- **WebMCP Flow**: アーキテクチャダイアグラムビルダー追加
- **Vercel AI SDK 移行**: 実験的マルチステップツール実行付き Vercel AI SDK への移行
- **Sport Shop デモ**: スポーツショップデモの改善

#### 参考リンク

- [webmcp-tools](https://github.com/GoogleChromeLabs/webmcp-tools)

---

### x402 (Internet Native Payments)

**現行バージョン**: Go v2.9.0 / Python v2.7.0 / TypeScript Core v2.10.0

#### Go v2.9.0 の主要な変更点

- **`SettleResponse`/`VerifyResponse` Extensions フィールド**: TypeScript SDK パリティのための Extensions フィールド追加 (#1808)
- **net/http サポートドキュメント**: Go SDK ドキュメントに net/http サポート追加 (#1782)

#### TypeScript Core v2.10.0 の主要な変更点

- **Aptos サポート**: Aptos ブロックチェーンサポート追加
- **Stellar サポート**: Stellar ブロックチェーンサポート追加
- **hook types エクスポート**: hook types のエクスポート (#1811)
- **MCP structuredContent 保持**: payment wrapper result での structuredContent 保持修正 (#1834)

#### Python v2.7.0 の主要な変更点

- **MCP server_sync テストカバレッジ**: MCP server_sync モジュールのテストカバレッジ追加 (#1733)

#### 未リリースの変更点

- **Stable テストネットサポート**: EVM に Stable テストネット (chain ID 2201) サポート追加 (#1786)
- **EVM コントラクトデプロイ修正**: EVM コントラクトデプロイの修正 (#1880)
- **USDC 追加**: Arbitrum One/Sepolia に USDC 追加 (#1877)
- **HTTPFacilitatorClient 308 リダイレクト修正**: 308 リダイレクト対応修正 (#1813)
- **Facilitator signer ランダム選択修正**: signer 選択のランダム化修正 (#1849)
- **Polygon メインネット**: Polygon メインネット (chain ID 137) デフォルトアセットサポート追加 (#1791)
- **リポジトリ移動通知**: README にリポジトリ移動ノート追加 (#40)

#### 参考リンク

- [x402 Protocol](https://github.com/coinbase/x402)

---

## Google Cloud / ADK

### ADK Python

**現行バージョン**: v1.30.0 (2026-04-13)

**注目**: v2.0.0a3 アルファ版がタグ付けされた。v2 系の開発が進行中。

#### v1.30.0 の主要な変更点

**[Core]**

- **Auth Provider サポート**: Agent Registry への Auth Provider サポート追加
- **Parameter Manager 統合**: ADK に Parameter Manager 統合追加
- **Gemma 4 モデルサポート**: ADK での Gemma 4 モデルサポート (#5156)
- **Live avatar サポート**: ADK での Live avatar サポート
- **Live session resumption**: BaseLlmFlow で `live_session_resumption_update` を Event として公開 (#4357)
- **BigQuery ツール Stable 昇格**: BigQuery ツールを安定版に昇格
- **A2A アーティファクトインターセプター**: `RemoteA2aAgent` でインターセプターを使用したアーティファクト含有 A2A イベント送信

**[Security]**

- **credential 漏洩脆弱性修正**: Agent Registry での credential 漏洩脆弱性修正
- **path traversal バリデーション**: user_id と session_id に対するパストラバーサル検証 (#5110)

#### v1.29.0 の主要な変更点

**[Core]**

- **EnvironmentToolset**: ファイル I/O とコマンド実行のための EnvironmentToolset 追加
- **LocalEnvironment**: ローカルコマンド実行とファイル I/O のための LocalEnvironment 追加
- **Easy GCP サポート**: ADK CLI に Easy GCP サポート追加
- **Secret Manager リージョナルエンドポイント**: `SecretManagerClient` のリージョナルエンドポイントサポート
- **Auth Provider 登録 API**: Credential Manager にカスタム Auth Provider 登録のパブリック API 追加
- **MCP ツール追加 HTTP ヘッダー**: MCP ツールでの追加 HTTP ヘッダーサポート

**[Tools]**

- **BashTool シェルメタキャラクターブロック**: BashTool でシェルメタキャラクターのブロック機能追加
- **BashTool リソースリミット**: サブプロセスの設定可能なリソースリミット
- **BashTool プロセスグループ管理**: 堅牢なプロセスグループ管理とタイムアウト
- **BigQuery ADK 1P Skills**: BigQuery ツールセットに ADK 1P Skills 追加

**[Models]**

- **Vertex AI カスタムセッション ID**: Vertex AI Session Service でのカスタムセッション ID サポート
- **Model endpoints in Agent Registry**: Agent Registry でのモデルエンドポイントサポート

**[Optimization]**

- **コンテキスト伝播**: スレッドプールへのコンテキスト伝播
- **InMemorySessionService 浅いコピー**: オプションの浅いコピーセッション

**[Bug Fixes]**

- **BigQuery analytics credential 秘匿**: BigQuery analytics プラグインでの credential 秘匿
- **BaseToolset.get_tools() キャッシュ**: 同一呼び出し内での get_tools() キャッシュ
- **pending function call コンパクション防止**: pending function call を持つイベントのコンパクション防止 (#4740)
- **Live session resumption/GoAway ハンドリング**: Live セッション再開と GoAway シグナルの処理 (#4996)

#### v1.28.0 の主要な変更点

- **A2A lifespan パラメータ**: A2A lifespan パラメータサポート追加
- **BigQuery 1P Toolset 移行**: BigQuery 1P ツールセットの移行
- **Spanner Admin Toolset**: Spanner Admin ツールセット新規追加
- **Slack 統合**: Slack インテグレーション追加
- **SSE ストリーミング**: 適合テスト向け SSE ストリーミングサポート
- **Anthropic thinking_blocks**: LiteLLM での Anthropic thinking_blocks フォーマットサポート
- **MCP サンプリングコールバック**: MCP サンプリングコールバックサポート
- **モジュールインポート保護**: 任意モジュールインポートに対する保護追加（セキュリティ）

#### 破壊的変更

| 変更 | 影響 |
|------|------|
| credential manager が `tool_context` を受け取るよう変更 (v1.24.0) | `callback_context` から `tool_context` への引数変更 |
| SecretManagerClient パッケージ移動 (v1.29.0) | `google.adk.integrations.secret_manager` パッケージへの移動 |

#### 参考リンク

- [ADK Python](https://github.com/google/adk-python)

---

### ADK Go

**現行バージョン**: v1.1.0

#### v1.1.0 の主要な変更点

- **Toolsets RequestProcessor**: Toolsets が `toolinternal.RequestProcessor` インターフェースを実装可能に (#730)
- **EventArc subrouter**: EventArc subrouter サポートと Cloud Run デプロイスクリプト統合 (#713, #716)
- **Pub/Sub trigger**: Pub/Sub トリガーセットアップと subrouter (#704, #712)
- **Skills パッケージ**: `skill.Source` インターフェースの定義とファイルシステムスキルソース実装 (#711)
- **Agent Engine デプロイ**: ADK Go CLI に Agent Engine デプロイ追加 (#715)
- **テレメトリ LRU キャッシュ**: デバッグテレメトリに設定可能な LRU キャッシュ（メモリリーク防止） (#687)
- **キャッシュ読み取り入力トークン属性**: テレメトリにキャッシュ読み取り入力トークン属性追加 (#714)

#### v1.0.0 の主要な変更点

- **正式リリース**: v1.0.0 安定版リリース

#### v0.6.0 の主要な変更点

- **Apigee モデル**: Apigee モデルサポート追加 (#639)
- **RemoteAgent パーツ変換拡張ポイント**: RemoteAgent パーツ変換の拡張ポイント (#627)
- **pathPrefix 設定**: API ランチャーに pathPrefix 設定追加 (#616)
- **Replay プラグイン**: リプレイプラグイン追加 (#618)

#### 参考リンク

- [ADK Go](https://github.com/google/adk-go)

---

### ADK JS

**現行バージョン**: v0.2.4

#### 未リリースの変更点

- **Skills システム**: スキルシステム実装（パート 2 & 3）、ローダー機能
- **Auth preprocessor**: 認証プリプロセッサー追加
- **OAuth2 サポート**: OAuth2 関連クラスの追加 (#225)
- **認証基盤クラス**: auth 関連ベースクラスの追加 (#223)
- **lodash セキュリティ更新**: lodash / lodash-es セキュリティ更新 (#232, #230)
- **パストラバーサル防止**: FileArtifactService のパストラバーサル脆弱性修正 (CWE-22)
- **Preload Memory ツール**: メモリプリロードツール追加
- **ESM ビルド修正**: ESM ビルドでの `__dirname`/`__filename` 保持
- **Unsafe local code executor**: unsafe ローカルコードエグゼキューター追加

#### v0.2.4 の主要な変更点

- **A2A 統合**: CLI オプションによる A2A 経由のエージェント提供 (#188)
- **トークンベースコンテキストコンパクション**: トークンベースのコンテキスト圧縮 (#191)
- **セッション DB 初期化修正**: 初期化時の既存テーブル全削除問題の修正 (#195)
- **MikroORM リファクタリング**: セッションサービスのリファクタ

#### 参考リンク

- [ADK JS](https://github.com/google/adk-js)

---

### Agent Starter Pack

**現行バージョン**: v0.41.1

#### v0.41.1 の主要な変更点

- **バージョンバンプ**: v0.41.1 へのバージョンバンプ (#944)

#### v0.41.0 の主要な変更点

- **デフォルトリージョン変更**: デフォルトリージョンを us-east1 に変更

#### v0.40.1 の主要な変更点

- **Vertex AI モデル名修正**: 接続チェック時の有効なモデル名使用 (#919)
- **BQ アナリティクステーブル名更新**: `agent_events` テーブル名に更新 (#924)

#### v0.40.0 の主要な変更点

- **adk-py@ ショートカット**: google/adk-python contributing samples 用ショートカット追加 (#918)
- **Gemini Enterprise アプリフィルタ**: `list_gemini_enterprise_apps` に `appType` フィルタ追加 (#912)

#### 参考リンク

- [Agent Starter Pack](https://github.com/GoogleCloudPlatform/agent-starter-pack)

---

### Cloud Run MCP

**現行バージョン**: v1.10.0

#### 未リリースの変更点

- **named/bind ボリューム権限修正**: named/bind ボリュームの権限ハンドリング修正
- **AI モデルサポート**: run compose での AI モデルサポート追加
- **Secrets Manager サポート**: compose デプロイメントでの Secrets Manager サポート
- **ボリュームマウントサポート**: ボリュームマウント機能追加
- **並列ビルド**: run compose での並列ビルドサポート
- **依存関係更新**: Hono 4.12.14、lodash 4.18.1 等の更新

#### v1.10.0 の主要な変更点

- **cloud-run-mcp クライアント**: OSS Run MCP からのデプロイ用クライアント追加 (#242)
- **Ingress ポリシー環境変数**: 環境変数によるイングレスポリシー設定 (#243)
- **Run v1 クライアント**: googleapis ベースの Run v1 クライアント追加 (#236)
- **統合テスト拡充**: Java, Node.js, Python プロジェクトの統合テスト追加

#### 参考リンク

- [Cloud Run MCP](https://github.com/GoogleCloudPlatform/cloud-run-mcp)

---

### gcloud-mcp

**現行バージョン**: gcloud-mcp-v0.5.3 / storage-mcp-v0.5.0 / observability-mcp-v0.2.3

#### storage-mcp-v0.5.0 の主要な変更点

- **安全なオブジェクトダウンロードツール**: 安全なダウンロードオブジェクトツール追加、オリジナルを destructive とマーク (#403)
- **カスタム User-Agent**: Storage クライアントにカスタム User-Agent 設定 (#407)
- **`list_buckets` 修正**: `userProject` の代わりに `project` を使用するよう修正 (#408)

#### 主要な変更点

- **backupdr-mcp v0.1.0**: Backup DR MCP サーバー新規追加 (#372, #380)
- **storage-mcp v0.3.3**: ストレージコンポーネント更新 (#358)
- **observability-mcp v0.2.3**: オブザーバビリティコンポーネント更新 (#357)
- **Windows 互換性**: リファクタリング (#342)

#### 参考リンク

- [gcloud-mcp](https://github.com/googleapis/gcloud-mcp)

---

### GKE MCP

**現行バージョン**: v0.11.0

#### 未リリースの変更点（v0.11.0 以降）

- **manifestgen リッチインストラクション埋め込み**: マニフェスト生成エージェントに包括的な生成インストラクションを埋め込み (#218)
- **Hono 依存関係更新**: UI の Hono 4.12.12 → 4.12.14 (#237)

#### v0.11.0 の主要な変更点

- **MUI 依存関係最新化**: Material-UI 依存関係を最新バージョンに更新 (#233)
- **NPM 依存関係更新**: globals, typescript 等の更新 (#234)
- **CI markdownlint/Prettier 競合修正**: markdownlint ルールと Prettier フォーマットの CI 競合修正 (#232)
- **Dependabot NPM 設定**: NPM 用 dependabot 設定追加 (#220)
- **CI アクション更新**: actions/checkout v6, actions/setup-node v6, actions/setup-go v6 (#223-#225)

#### v0.10.0 の主要な変更点

- **Golden Image Finder スキル**: ゴールデンイメージ検索スキル追加
- **Docker イメージサポート**: Docker イメージのサポート追加 (#183)
- **GKE Workload Scaling スキル**: ワークロードスケーリングスキル追加
- **ComputeClasses スキル**: ComputeClasses 作成スキル追加
- **Shell Command Injection 修正**: `ui/scripts/build.ts` のシェルコマンドインジェクション脆弱性修正（セキュリティ）

#### 参考リンク

- [GKE MCP](https://github.com/googleapis/gke-mcp)

---

### Google Analytics MCP

**現行バージョン**: v0.2.0

#### v0.2.0 以降の変更点

- **google-adk 最低バージョン更新 (セキュリティ)**: google-adk 最低バージョンを 1.28.1 に更新、脆弱性 GHSA-rg7c-g689-fr3x 対応 (#137)
- **MCP スキーマ互換性改善**: MCP スキーマ互換性と LLM ガイダンスの改善
- **ADK 移行**: Google ADK を使用するよう移行
- **google-analytics-admin 更新**: v0.28.0 へ更新
- **google-analytics-data 更新**: v0.21.0 へ更新

#### v0.2.0 の主要な変更点

- **ADK スキーマ型修正**: null 型の除去修正
- **pipx 対応**: サーバーの pipx 利用対応

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
- **Cloud Data MCP サンプル**: DK と Cloud SQL リモート MCP のラボ追加
- **Chrome DevTools サーバー**: 新規 MCP サーバー追加

#### 参考リンク

- [Google Cloud MCP](https://github.com/google/mcp)

---

### MCP Security

**現行バージョン**: secops-v0.7.0 (2026-03-14)

#### v0.7.0 以降の変更点

- **SOC ペルソナドキュメント**: SOC ペルソナをドキュメントに追加 (#245)
- **gemini-extension.json 移動**: トップレベルへのリファクタ

#### v0.7.0 の主要な変更点

- **Rule Exclusions 管理ツール**: ルール除外管理ツール追加 (#242)

#### v0.6.0 の主要な変更点

- **Investigation 管理ツール**: 調査管理ツール追加 (#220)
- **Watchlist 管理ツール**: ウォッチリスト管理ツール追加 (#222)
- **Remote MCP サーバー**: リモート MCP サーバー実装とドキュメント (#215)

#### 参考リンク

- [MCP Security](https://github.com/google/mcp-security)

---

### GenAI Toolbox

**現行バージョン**: v1.1.0 (2026-04-13)

**注目**: v1.0.0 で安定版リリースに到達。[UPGRADING.md](https://github.com/googleapis/genai-toolbox/blob/main/UPGRADING.md) でのマイグレーションガイド参照。

#### 未リリースの変更点（v1.1.0 以降）

- **Dataplex Data Quality Scans 検索ツール**: Dataplex Data Quality Scans の検索・ディスカバリーツール追加。スキャン ID やテーブル名でのフィルタリング、ページネーション、ソート対応 (#2444)

#### v1.1.0 の主要な変更点

- **Cloud SQL Postgres vector assist ツール**: Cloud SQL Postgres 向けベクターアシストツール追加 (#2909)
- **Looker YAML フラット化**: Looker 設定 YAML をフラット形式に変換修正 (#3022)
- **dataplex → knowledge-catalog リネーム**: ドキュメント全体で dataplex を knowledge-catalog にリネーム (#3039)

#### v1.0.0 の主要な変更点（**安定版リリース**）

- **Elasticsearch vector search**: ベクターサーチサポート追加＆クエリパススルーパラメータ削除（**破壊的変更**） (#2891)
- **Looker git-branch ツールリファクタ**: looker-git-branch ツールを5つの個別ツールに分割（**破壊的変更**） (#2976)
- **opaque token バリデーション**: `generic` authService での opaque token バリデーションサポート (#2944)
- **Cloud SQL Postgres 接続確認**: 接続成功後に `SELECT 1` を実行 (#2997)
- **BigQuery semantic search**: BigQuery SQL にセマンティックサーチサポート追加 (#2890)
- **Elasticsearch ES/QL**: 任意の ES/QL クエリ実行ツール追加 (#3013)
- **MySQL list-table-stats**: MySQL テーブル統計一覧ツール追加 (#2938)

#### v0.32.0 の主要な変更点

- **リポジトリ名更新**: リポジトリ名の変更（**破壊的変更**） (#2968)
- **MCP ツールアノテーション**: 全残ツールに MCP ツールアノテーション追加 (#2221)
- **BigQuery 会話分析ツール**: Data Agents 向け会話分析ツール追加 (#2517)
- **Claude Code / Codex スキルサポート**: 生成スクリプトに Claude Code と Codex user agent サポート追加 (#2966, #2973)
- **npx 経由ツール実行**: npx でのツール呼び出しサポート (#2916)
- **Looker エージェント管理**: MCP からの Looker エージェント管理 (#2830)

#### v0.31.0 の主要な変更点

- **`enable-api` フラグ**: API 有効化フラグの追加（**破壊的変更**）
- **Protected Resource Metadata エンドポイント**: Protected Resource Metadata エンドポイント追加
- **Manual PRM オーバーライド**: 手動 PRM オーバーライドサポート
- **Dataplex ルックアップコンテキストツール**: Dataplex ルックアップコンテキストツール追加
- **非推奨項目削除＆tools-file フラグ更新**: 非推奨項目の削除（**破壊的変更**）

#### 破壊的変更

| 変更 | 影響 |
|------|------|
| Elasticsearch vector search (v1.0.0, #2891) | クエリパススルーパラメータ削除 |
| Looker git-branch リファクタ (v1.0.0, #2976) | 1ツール → 5ツールへの分割 |
| リポジトリ名更新 (v0.32.0, #2968) | リポジトリ URL の変更 |
| `enable-api` フラグ (v0.31.0) | API エンドポイントの明示的有効化が必要 |
| 非推奨項目削除 (v0.31.0, #2806) | tools-file フラグ等の変更 |
| HTTP 非 2xx エラー出力サニタイズ (v0.31.0, #2654) | エラーレスポンス形式変更 |
| プリビルトツールセット再構成 (v0.29.0) | AlloyDB, Spanner 等のツールセット構造変更 |
| 設定ファイル v2 (v0.27.0, #2369) | 設定ファイルフォーマットの変更が必要 |

#### 参考リンク

- [GenAI Toolbox](https://github.com/googleapis/genai-toolbox)

---

## 注目ポイント

### 破壊的変更一覧

| 対象 | 変更内容 | 対応優先度 |
|------|---------|-----------|
| **UCP v2026-04-08** | 6件の破壊的変更: variant options リネーム、webhook 分離、エラー統一、currency 必須化等 | 高 |
| **GenAI Toolbox v1.0.0** | Elasticsearch vector search リファクタ、Looker ツール分割 | 高 |
| **GenAI Toolbox v0.32.0** | リポジトリ名更新 | 高 |
| **GenAI Toolbox v0.31.0** | `enable-api` フラグ必須化、非推奨項目削除 | 高 |
| **A2A v1.0.0** | Push Notification Config 統合、`blocking`→`return_immediately`、仕様リファクタ | 高 |
| **MCP-UI v7.0.0** | レガシー仕様の完全削除 | 高 |
| **ACP v2026-01-30** | Payment Handlers Framework 導入 | 高 |
| **ADK Python v1.29.0** | SecretManagerClient パッケージ移動 | 中 |
| **Google Analytics MCP** (未リリース) | パッケージ名 `analytics-mcp` にリネーム | 低 |

### メジャーアップデート

1. **GenAI Toolbox v1.0.0 → v1.1.0** - v1.0.0 安定版リリース到達（v0.31.0 からの大幅ジャンプ）。Cloud SQL Postgres vector assist、Elasticsearch ES/QL 等追加
2. **ADK Python v1.30.0** - EnvironmentToolset (v1.29.0)、Gemma 4/Live avatar/Parameter Manager (v1.30.0)、**v2.0.0a3 アルファ版進行中**
3. **UCP v2026-04-08** - 6件の破壊的変更を含む大型リリース。Get Order、Order currency 必須化、EP エラーコンベンション統一
4. **ADK Go v1.1.0** - RequestProcessor インターフェース、EventArc/Pub/Sub、Skills パッケージ
5. **AG-UI release/2026-04-15** - 毎週リリース継続。CVE-2026-25528 セキュリティ修正、AWS Strands/LangGraph 統合更新、A2UI v0.9 ミドルウェア。未リリースで State Snapshot/Delta コンパクション追加
6. **MCP-Apps v1.6.0** - Progress-based timeout reset
7. **x402** - Go v2.9.0、Python v2.7.0、TS Core v2.10.0。Stable テストネット、Polygon メインネット
8. **gcloud-mcp storage-mcp-v0.5.0** - 安全なダウンロードツール、カスタム User-Agent
9. **GKE MCP v0.11.0** - MUI 最新化、CI 改善
10. **Agent Starter Pack v0.41.1** - v0.41.1 バージョンバンプ

### 新規プロトコル統合

1. **AG-UI + AWS Strands** - AWS Strands 統合改善、kwargs 転送修正
2. **AG-UI + A2UI v0.9** - A2UI ミドルウェア v0.9 インラインカタログスキーマ対応
3. **AG-UI + ADK getCapabilities** - ADKAgent に getCapabilities() と /capabilities エンドポイント追加
4. **MCP + HTTP Standardization (SEP-2243)** - HTTP トランスポートの標準化マージ
5. **MCP + Skills Over MCP IG** - Skills Over MCP Interest Group チャーター策定
6. **GenAI Toolbox + Claude Code/Codex** - 生成スキルに Claude Code/Codex サポート
7. **ADK Go + EventArc/Pub/Sub** - EventArc subrouter と Pub/Sub トリガー統合
8. **ADK Python + Parameter Manager** - ADK に Parameter Manager 統合
9. **gcloud-mcp + Backup DR** - backupdr-mcp v0.1.0 新規サーバー
10. **AgentSkills + Workshop.ai/nanobot** - クライアントショーケース拡大

### セキュリティ更新

- **AG-UI**: CVE-2026-25528 依存関係脆弱性修正 (#1527)、ADK ミドルウェア critical/high Dependabot 脆弱性修正 (#1517)
- **ADK Python v1.30.0**: Agent Registry credential 漏洩脆弱性修正、path traversal バリデーション (#5110)
- **ADK JS**: FileArtifactService パストラバーサル脆弱性修正 (CWE-22)、lodash セキュリティ更新
- **UCP**: lodash セキュリティ更新（Trivy 脆弱性修正） (#333)
- **x402**: HTTPFacilitatorClient リダイレクト修正、Facilitator signer ランダム選択修正
- **MCP-Apps v1.4.0**: path-to-regexp ReDoS CVE 修正
- **GKE MCP v0.10.0**: Shell Command Injection 修正（`ui/scripts/build.ts`）
- **Google Analytics MCP**: google-adk 最低バージョン 1.28.1 更新（GHSA-rg7c-g689-fr3x 対応）
- **MCP**: OIDC / エンタープライズ管理認可更新、SEP-2207 リフレッシュトークンガイダンス
