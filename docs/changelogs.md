# プロトコル変更ログ

最終更新: 2026-06-10

各プロトコル・Google Cloud サブモジュールの主要な変更点をまとめたドキュメント。

---

## プロトコル (Protocols)

### A2A (Agent-to-Agent)

**現行バージョン**: v1.0.1 (2026-05)

**チェックアウト状態**: `v1.0.1-6-g7475dd0` (v1.0.1 + 6 commits、 HEAD 2026-06-02)

#### v1.0.1 リリース (2026-05) 後の新着

- **v1.0.1 リリース**: v1.0.0 → v1.0.1 への正式リリース (#1749)
- **Rust SDK (a2a-rs) 参照追加**: README に Rust SDK (a2a-rs) リファレンス追加、 linter workflow 更新 (#1863)
- **multi-tenancy ガイド追加**: マルチテナンシーガイドと tenant フィールドのセマンティクス明確化 (#1848)
- **push notification auth 整合**: push notification 認証例をプロトコル挙動に整合 (#1793)
- **SDK 数を 6 に更新**: Rust 追加で公式 SDK 数を 6 に更新 (#1778)
- **Tutorial 8 import path 修正**: AgentExecutor import path 修正 (#1884)
- **MCP リファレンス明確化**: A2A overview の MCP 参照を明確化 (#1873)

#### v1.0.0 後の変更点

- **TaskStatus values 仕様修正**: TaskStatus values の仕様記述を修正 (#1801)
- **stateTransitionHistory 廃止参照削除**: 仕様から deprecated stateTransitionHistory references を削除 (#1834)
- **"Send Streaming Message" リネーム**: "Stream Message" → "Send Streaming Message"、レガシーメソッド名置換 (#1784)
- **HTTP binding MIME 推奨**: `application/a2a+json` を HTTP binding で優先使用 (#1753)
- **カスタムプロトコル bindings ドキュメント**: カスタムプロトコルバインディングの公式ドキュメント追加 (#1619)
- **新ロゴ＆マスコット**: ブランディング刷新 (#1719)
- **Community SDKs 追加**: 公式 SDK リストとは別に Community SDK セクション追加 (#1698)
- **Rust SDK 公式化**: 公式 SDK リストに Rust SDK 追加 (#1729)
- **TSC メンバー追加プロセス**: GOVERNANCE.md に TSC メンバー追加方法ドキュメント追加 (#1571)
- **仕様修正**: トランスコーディング関連エラーの修正 (#1627)
- **パートナーリスト拡充**: OIXA Protocol (#1692), Strale (#1702), WritBase (#1634) 追加
- **tutorial ホスト修正**: チュートリアルで `127.0.0.1` を使用 (#1783)
- **Python helloworld チュートリアル更新**: a2a-sdk v1.0 向けに更新 (#1775)
- **ローカルビルド手順**: Contributing Guide にローカルビルド手順追加 (#1726)

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

**現行バージョン**: v0.9 (v0.10 spec 作業中)

**チェックアウト状態**: `330991f5` (v0.9 タグ後の HEAD、 v0.10 仕様作業を含む、 HEAD 2026-06-09)

#### 2026-06-09 新着 (a2ui_core SDK 立ち上げ / v0.10 spec 続報)

- **a2ui_core SDK 初期化**: schema 定義 + basic UI catalog components を持つ a2ui_core SDK を新設（Python 実装 / web_core の `basic_catalog` export、 CatalogInterface for v0.9）
- **BREAKING (v0.10): `theme` → `surfaceProperties` rename + `primaryColor` 削除** (#1525)
- **v0.10 spec: surfaceId は client session 毎にグローバル一意** (#1543)、 **Catalog schema に optional `instructions` field 追加 + rules.txt 廃止** (#1522)
- **spec: list templates 向け built-in `@index` function** (#1572)、 **catalog entity 命名規則を Unicode UAX #31 で規定** (#1573)
- **FunctionCall wire schema を refactor** し protocol specification と整合 (#1518)
- **monorepo を Yarn v4 workspaces へ移行** (#1054)

#### 2026-06 新着 (v0.10 spec initialState / MIME 規約変更 / Angular checks 型)

- **BREAKING: IANA MIME を `application/a2ui+json` に**: IANA 規約に合わせ mime type を `application/a2ui+json` へ変更 (POTENTIALLY BREAKING, #1493)
- **v0.10 CreateSurfaceMessage に optional `initialState`**: v0.10 で CreateSurfaceMessage に optional initialState を追加 (#1524)
- **Angular `checks` 型を ExtendedProps に露出**: ExtendedProps に checks 型を露出 (#1523)
- **migration notice 追加**: 移行告知を追加 (#1512)
- **GeneratedPluginRegistrant 除外**: 生成された GeneratedPluginRegistrant ファイルを ignore/削除 (#1530)

#### 2026-05 末 新着 (v0.10 spec / A2UI-over-MCP 強化 / Angular ComponentBinder)

- **Angular ComponentBinder children prop バグ修正**: v0.9 Angular ComponentBinder の children prop バグを修正、 unit test を real model 使用へ改善 (#1472)
- **v0.10 spec: Slider に `steps` property 追加**: v0.10 basic catalog の Slider に `steps` property を追加 (#1462)
- **basic_catalog.json refs クリーンアップ**: 残存する basic_catalog.json への参照を全削除 (#1463)
- **A2UI-over-MCP: static resources / dynamic tools サポート**: A2UI-over-MCP 統合で static resources と dynamic tools をサポート (#1471)
- **v0.9 / v0.10 catalog files 再構成**: v0.9 と v0.10 の catalog files を専用構造に再配置 (#1452)
- **web-core formatString 仕様準拠化**: formatString の objects/arrays を spec 通り JSON-stringify (#1430)
- **Angular dataModel computed property リファクタ**: dataModel computed property の redundant version() 呼び出しを削除 (#1475)
- **Angular explorer に v0.8 サポート**: Angular explorer app で v0.8 もサポート (#1436)

#### 2026-05 後半 新着 (v0.10 spec ドリフト + v0.9 streaming/MCP 整備)

- **v0.9 streaming parser suite**: v0.9 向けストリーミングパーサ一式を追加 (#1394)
- **v0.9 統合テスト整理**: 統合テストを `tests/v0_9` ディレクトリへ移動 (#1435)
- **v0.10 spec: Video `posterUrl` 削除**: v0.9 Angular から `posterUrl` 削除し v0.10 spec に追加 (#1373)
- **v0.10 spec: `placeholder` 同等処理**: 同等処理を v0.10 spec へ統合 (#1372)
- **v0.10 spec: Icon `color` prop 削除**: Icon コンポーネントから `color` prop を削除 (#1371, fix #1303)
- **A2UI×MCP サンプル復旧**: MCP 経由 A2UI サンプル動作復旧 + ガイド更新と図示 (#1076, #1439)
- **Icon snake_case 対応**: snake_case でも解釈できるよう Icon 内部修正 (#1433)

#### v0.9 後の変更点（web_core 0.9.2+ 含む、 2026-05 アクティビティ）

- **DataValueSchema recursion depth override**: v0_8 の `DataValueSchema` で recursion depth を override 可能に（refactor、 web_core） (#1431)
- **web_core locale サポート + pluralize 修正**: web_core に locale サポートを実装、 `pluralize` の挙動修正 (#1427)
- **Icon `color` prop 削除**: Icon コンポーネントから `color` prop を削除 (#1371, fix #1303)
- **CatalogComponentInstance を web_core へ移動**: 構造整理 (#1426)
- **A2UI ローカル uploader dashboard モダン化**: workspace_settings サンプル統合と dashboard の刷新 (#1381)
- **examples の動画リンクレジストリ**: 動画付き examples のレジストリを作成 (#1407)
- **AgentExtension パラメータ順序修正**: AgentExtension 作成時のパラメータ順序が逆になっていたバグ修正 (#1393)
- **Icon `path` → `svgPath` リネーム**: 型衝突解消のため Icon path プロパティをリネーム (#1347)
- **Accept/Reject CTAs / MCP tool allowlisting / モデル選択 / 依存リンク**: A2UI と editor app の多数の改善（モデル選択、 MCP tool allowlist、 dependency linking 等） (#1363)
- **Android / Jetpack Compose v0.9 renderer**: ecosystem ドキュメントに Android/Jetpack Compose v0.9 renderer 追加 (#1352)
- **Cloud Run デプロイ gcloud auth 前提条件**: Cloud Run デプロイガイドに gcloud authentication prerequisites 追加 (#1341)
- **React SVG CSS reset 除外**: SVG エレメントを React の CSS reset から除外 (#1252)
- **Angular CI ワークフロー最適化**: (#1357)
- **Python フォーマット強制**: 全 Python ファイルへフォーマット強制 (#1340)
- **Standard Catalog → Basic Catalog リネーム**: ドキュメントでの呼称統一と v0.9 ステータス更新 (#1302)
- **Vue3 renderer サポートドキュメント**: (#873)
- **A2UI Inspect AI 評価フレームワーク追加**: Inspect AI を用いた包括的 A2UI 評価フレームワーク導入（feat(eval)）
- **renderer publishing スクリプト改善**: CI 経由 renderer publishing スクリプトの整備 (#1317)
- **restaurant sample streaming duplicate surfaces 修正**: restaurant sample アプリの streaming で発生する duplicate surfaces エラー修正 (#1322)
- **C++ Agent SDK 完全削除**: 全 C++ ソース・ビルド設定を削除 (#1335)
- **Java Agent SDK 削除**: Java エージェント SDK 削除し Kotlin 実装にリファレンス (#1336)
- **Slider 動的 aria-label**: コンポーネントプロパティの null チェック追加と Slider の dynamic aria-label 化 (#1345)
- **prettier 自動インストール抑制**: フォーマット時に prettier インストール確認を求めない (#1342)
- **リポジトリ全体のフォーマット強制**: 全リポでの自動フォーマット適用 (#1338)
- **Kotlin 非決定テスト修正**: Kotlin の format check 追加と非決定テスト失敗の修正 (#1339)
- **Surface model `any` 削除**: surface model generic fallback から `any` 除去、Angular component host 更新 (#1314)
- **node プロパティ null check**: ランタイムエラー防止のための node プロパティ null チェック (#1334)
- **Catalog コンポーネント strict type**: 必須プロパティ実装を強制する strict type 追加 (#1320)
- **Checkbox value プロパティリネーム**: `checked` → `value` (#1332)
- **モジュール名衝突解消**: 明示的修飾名による module name collision の解消 (#1329)
- **Markdown-it npm 公開リリース**: markdown-it パッケージ初リリース (#1304)
- **markdown-it dompurify 3.3.1 pin**: 企業プロキシ環境向けインストール問題の解決 (#1313)
- **jsoncons による JSON Schema validation**: 堅牢な JSON schema validation のための jsoncons 統合 (#1274)
- **A2uiCatalog glob パターンサポート**: ファイルパスマッチングの glob パターンサポートと conformance test 有効化 (#1273)
- **Angular catalog コンポーネント props typing 改善**: (#1265)
- **Python unit test の conformance test 移行**: 残りの Python ユニットテストを conformance test 化 (#1266)
- **Kotlin unit test の conformance test 移行**: 残り Kotlin ユニットテストの移行 (#1301)
- **MCP samples ディレクトリ再編**: a2ui-in-mcpapps サンプルプロジェクト追加 (#1323)
- **AnyDuringSchemaAlignment alias 作成**: Angular `any` 問題追跡用 alias 追加 (#1310)
- **未テスト platform 削除**: テスト対象外プラットフォームの削除 (#1308)
- **URL hash navigation for Angular explorer**: Angular explorer の URL hash 移動実装 (#1269)
- **sandbox iframe origin/Vite module pathing 修正**: sandboxed iframe の origin と Vite module パス問題解決 (#1318)
- **Dart 飲食店 finder 追加**: Dart restaurant finder サンプル追加 (#1280)
- **Angular Types namespace 削除**: v0.8 renderer から Types namespace 削除 (#1292)
- **React typechecking 統合**: ビルドプロセスに型チェック統合 (#1284)
- **Kotlin SDK conformance tests 統合**: Kotlin SDK と A2UI コンフォーマンステスト統合 (#1129)
- **React shell v0.9 移行**: React シェルサンプルを A2UI v0.9 に移行 (#1262)
- **Dart SDK AI ワークフロー**: AI を用いた tests のワークフローと初期テスト定義 (#1251)
- **A2UI Examples ライブ JSON 編集**: メッセージ JSON のライブ編集サポート (#1243)
- **Angular primaryColor 伝搬**: basic catalog で primaryColor をコンポーネントに伝播 (#1242)
- **C++ ポート初期実装**: Python エージェント SDK の初期 C++ ポート (#1254)
- **License 修正コマンド追加**: ライセンス修正用 command/UI config 追加 (#1281)
- **MCP guides 整理**: (#1286)
- **web_core 0.9.2 リリース**: web_core パッケージ 0.9.2 リリース (#1212)
- **obscured enum type 追加**: v0_8 common types Zod に欠落していた `obscured` enum タイプを追加 (#1264)
- **private index URL CI 修正**: uv.lock の private index URL による CI 失敗修正 (#1261)
- **Gemini Enterprise Agent Engine 修正**: Cloud Run/Agent Engine へのデプロイ不可問題修正 (#1256)
- **try_activate_a2ui_extension 修正**: 拡張機能アクティベートのバグ修正 (#1234)
- **createSurface エラー仕様明確化**: 既存サーフェスに対する createSurface がエラーとなる旨を明確化 (#1238)
- **React widgets CSS variables スタイリング**: React レンダラーで CSS 変数を使ってウィジェットスタイル (#1205)
- **React weight プロパティ対応**: basic catalog で `weight` プロパティを honor (#1215)
- **Angular Tabs コンポーネント修正**: (#1218)
- **Angular restaurant サンプルスタイル合わせ**: (#1220)
- **Node.js / publishing スクリプト更新**: Angular テストを含む improve (#1177)
- **AG-UI ガイド追加**: feature quickstarts と AG-UI ガイド追加 (#1229)
- **Python google-adk 1.28.1 bump (セキュリティ)**: (#1219)
- **personalized_learning サンプル分割**: agent と client に分割 (#1244)
- **v0.9 レンダラーアイコンオーバーライド**: (#1146)
- **Angular Restaurant Sample v0.9 移植**: (#1189)
- **サーバーエラー伝播修正**: (#1203)
- **レンダラーパッケージ alpha.3 バージョンバンプ**: (#1178)
- **A2UI Theater**: インタラクティブ JSONL プレイバック＆ストリーミングビューア (#987)
- **A2A SSE ストリーミング**: (#1049)
- **concurrent surface サポート**: (#1037)
- **MCP Apps 統合**: (#748)

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

### ADP (Agent Data Protocol)

**現行バージョン**: v1.3.1 (2026-06)

**チェックアウト状態**: `v1.3.1-7-g2d7feff` (v1.3.1 + 7 commits、 HEAD 2026-06-03)

**管理**: CMU NeuLab

#### v1.2.0 / v1.3.0 / v1.3.1 リリース (2026-05〜06)

- **SFT データセット拡充**: LiteCoder Terminal SFT (#255)、 NVIDIA SWE-Zero OpenHands trajectories (#246)、 hybrid-gym trajectory (#248) を追加
- **OpenHands SDK condenser SFT**: openhands-sdk が condenser prompt SFT データを emit (#244)、 SDK-backed OpenHands SFT converter 追加 (#241)
- **condenser replay / identity**: in-memory event history で condenser replay (#252)、 condensation 不要時に identity trajectory を emit (#251)
- **Hugging Face chat-template 互換**: SFT サンプルを HF chat-template 互換に (#242)

#### v1.0.0 / v1.1.0 リリース (2026-05)

- **v1.1.0**: trajectory フィールドに「利用可能 API」を昇格させる正式化 (#212)
- **v1.0.0**: standardized schema versioning を導入 — スキーマバージョンを公式化、暗黙バージョンから明示バージョン必須化 (#211)
- **OpenHands browser tools optional**: 非Webデータセット向けに OpenHands ブラウザツールを任意化 (#213)

#### 破壊的変更

| 変更 | 影響 |
|------|------|
| v1.0.0 へのジャンプ (schema versioning 明示必須) | 従来の暗黙 schema は明示バージョン宣言が必要 |

#### 最近の変更点 (1.x 前)

- **Catalog データセットガイドライン**: Catalog dataset ガイドライン追加と PR レビューワークフロー導入 (#186)
- **per-step reward フィールド追加**: Action / Observation スキーマに optional `reward: float | None` フィールド追加。RL トレーニングデータでの per-step reward 信号運搬対応。6 つの concrete action/observation type 全てに継承。デフォルト None で既存データセットへの影響なし (#183)
- **CoderForge-Preview データセット追加**: コーディング系トラジェクトリーデータセット (#167)
- **Nemotron Terminal Corpus データセット追加**: ターミナルコーパスデータセット (#165)
- **Toucan データセット追加**: (#163)
- **包括的ドキュメント追加**: 全サポート済みデータセット・エージェントの README/LICENSE と mini-coder インテグレーション完了 (#162)
- **SWE-Playground Trajectories データセット追加**: (#161)
- **Toucan-1.5M データセット実装**: (#154)
- **mini-coder トラジェクトリーデータセット**: (#155)
- **TextObservation `name` フィールド**: optional `name` フィールド追加 (#150)
- **MCP 統合 / SWE Agent コンバージョン整理**: MCP 追加、SWE Agent コンバージョン修正、エージェントコンバージョン整理 (#148)
- **SWE Agent std_to_sft 変換スクリプト**: (#140)
- **send_msg_to_user actions → MessageAction 変換**: (#145)
- **Nnetnav 修正＆Go-Browse フィルタ**: (#144)

#### 主要な変更点

- **データセットサポート**: SWE-Playground Trajectories, Toucan-1.5M, mini-coder trajectories, CoderForge-Preview, Nemotron Terminal Corpus, Toucan
- **MCP 統合**: エージェントツーリング連携
- **マルチエージェント対応**: OpenHands, SWE-agent, AgentLab
- **Pydantic 型安全性**: スキーマ検証強化

#### 参考リンク

- [ADP Protocol](https://github.com/neulab/agent-data-protocol)

---

### AG-UI (Agent-User Interaction Protocol)

**現行バージョン**: **TS SDK 0.0.56 (2026-06-09)** / @ag-ui/langgraph@0.0.40 (TS) / ag-ui-langgraph@0.0.41 (Py) / Python protocol 0.1.19

**チェックアウト状態**: `861d0b22` (0.0.56 リリース後、 HEAD 2026-06-09)

#### 2026-06-09 新着 (TS SDK 0.0.56 / A2UI toolkit)

- **TS SDK 一式を 0.0.56 へ**: @ag-ui/core / client / encoder / proto / create-ag-ui-app を 0.0.56 に bump
- **@ag-ui/a2ui-toolkit 0.0.3 を公開**: A2UI 連携 toolkit を publish し、 langgraph TS 統合（@ag-ui/langgraph@0.0.40）が利用。 A2UI dynamic schema params 修正も同梱
- **langgraph 統合 bump**: ag-ui-langgraph@0.0.41 (Py) / @ag-ui/langgraph@0.0.40 (TS)
- **adk-middleware**: live-test のデフォルトモデルを gemini-3.5-flash に更新

#### 2026-06 上旬 (TS SDK 0.0.55 / protocol 0.1.19 / mcp-middleware)

- **client run_id を RUN_FINISHED で保持**: RUN_FINISHED イベントで client の run_id を保持 (#1582)
- **integration-langgraph-ts 0.0.36**: langgraph TS 統合を 0.0.36 に bump
- **sdk-py protocol 0.1.19**: Python SDK protocol を 0.1.19 に bump
- **TS SDK パッケージ 0.0.55 一括リリース**: client / core / encoder / proto を 0.0.55 に
- **event reducer: tool result 順序修正**: tool result を対応する tool call の後に配置 (client)
- **langgraph TS createAgent inner graph export**: inner graph を export
- **@ag-ui/mcp-middleware 追加**: mcp-middleware リリーススコープを追加

#### release/2026-04-22 の主要な変更点

- **State Snapshot/Delta コンパクション**: run 単位で STATE_SNAPSHOT と STATE_DELTA イベントを単一の最終状態に圧縮、fast-json-patch (RFC 6902) によるデルタ適用 (#1535)
- **release-python タグ作成 idempotent 化**: 再試行時の release-python タグ作成を冪等に (#1548)
- **interrupt-aware ランライフサイクル草案拡張**: ドキュメント proposal 拡張 (#1555)
- **Python SDK 0.1.18**: SDK Python 0.1.18 リリース
- **AgentCapabilities Python SDK 追加**: Python SDK に AgentCapabilities タイプ追加 (#1307)
- **LangGraph orphan tool message 保持**: `langgraph_default_merge_state` で orphan tool message 修正保持 (#1494)
- **Strands template hooks 転送**: per-thread `StrandsAgentCore` に template hooks 転送 (#1561)
- **Mastra resourceId 転送**: working-memory sync の Memory 呼び出しで `resourceId` を毎回転送 (#1560)
- **LangGraph エンプティストリング/フォールバック多数修正**: `resolve_message_content`、`handle_reasoning_event`、`handle_node_change` 等 (langgraph 系)
- **LFS マイグレーション**: `test-image.png` を LFS トラッキングへ。pre-commit フックで生バイナリの LFS バイパス検出
- **Talk to Us フォーム**: ドキュメントサイドバーに「Talk to Us」フォーム追加 (#1554)
- **prepareRegenerateStream config 転送修正**: `assistantConfig` と forwarded config を正しくマージ (#1509)
- **Python wheel パーミッション修正リバート**: 壊れた wheel ビルド原因のリバート (#1508)

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

**チェックアウト状態**: HEAD `5d4c1fd` (2026-05-21)

**管理**: Anthropic

#### 2026-05 後半 新着

- **name field 文字範囲修正 (digits 許可)**: spec の name field 文字範囲を alphanumeric + digits に修正 (#384)
- **bub クライアント追加**: bub をクライアント一覧に追加 (#340)
- **Superconductor クライアント追加**: Superconductor を ClientShowcase に追加 (#377)
- **Vita ロゴ追加**: Agent Skills logo carousel に Vita ロゴ追加 (#332)
- **Tabnine クライアント追加**: ClientShowcase に Tabnine 追加 (#349)
- **README.md コンテンツ拡充**: home.mdx の内容を README.md に取り込み、READMEのスタンドアロン化

#### 最近の変更点

- **ランディングページ刷新**: home.mdx に「What are Agent Skills?」「How do Agent Skills work?」セクション追加、Why/What セクション統合、Adoption 再構成
- **fast-agent クライアント追加**: fast-agent をクライアント一覧に追加、ロゴサイズ調整 (#327, #328)
- **Google AI Edge Gallery 追加**: Agent Skills クライアントリストに追加、ソースコード URL 追加
- **Workshop.ai クライアント追加**: (#314)
- **nanobot クライアント追加**: (#315)
- **LogoCarousel 簡素化**: 共通 `clients.jsx` 抽出とマージンオーバーライド
- **Get Started カード縮減**: home.mdx の "Get started" を Quickstart と Specification の 2 枚に縮約
- **Progressive disclosure リンク統合**: specification.mdx への統一
- **`what-are-skills.mdx` 削除**: 冗長なドキュメント削除
- **Client Showcase ページ**: Web ベースクライアントショーケースページ (#291)
- **シャッフル/アルファベット切替**: ClientShowcase にトグル追加

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

### MCP (Model Context Protocol)

**現行バージョン**: 2025-11-25 (次期リリース候補 `2026-07-28-RC` 作業中)

**チェックアウト状態**: `1304c8fe` (2026-07-28-RC タグ後の next-revision draft 作業中、 HEAD 2026-06-09)

**注目**: 2025-11-25 タグで `2025-11-25-RC` から正式リリース昇格。HEAD はそれより先に進んでおり、**SEP-2567 (Sessionless MCP via Explicit State Handles) と SEP-2575 (Make MCP Stateless) が Final / Accepted へ昇格**して draft に組み込み中。 ステートレス志向への大きな仕様シフトが進行中。 直近では **SEP-2596 (Feature Lifecycle and Deprecation Policy)、 SEP-2577 (Deprecate Roots/Sampling/Logging)、 SEP-2106 (Tools schema を JSON Schema 2020-12 準拠化)、 SEP-2164 (resource not found error code 標準化)、 SEP-2468 (Issuer iss param 推奨)、 SEP-2484 (Standards Track SEP は Conformance Tests 必須)、 SEP-2663 (Tasks Extension)、 SEP-2575 で unsupported protocol error code 追加** 等が連続して進行。

#### 2026-06 新着 (message patterns 再編 / stdio legacy-fallback / Server Card WG)

- **Authorization spec ドキュメント再構成**: AS discovery を独立ドキュメントに分離し、 client registration を1ページに統合（normative 文言をテーブルから本文へ昇格、 2026-06-04〜05 の localden/auth-spec 一連）
- **schema 修正: `ElicitationCompleteNotificationParams`** を NotificationParams 継承として抽出 (#2866)
- **Registry / Server Card / Triggers & Events charter に repository links 追加** (#2887)

- **message patterns ページ再編**: utilities/ から message patterns ページを移動・再編し、 リンクを更新
- **stdio legacy-fallback ルール修正 + 互換性マトリクス**: stdio の legacy-fallback ルールを修正し、 compatibility matrix を追加 (#2844)
- **draft spec overview 整理**: deprecated features を削除し、 extensions セクションを追加
- **Server Identity WG → Server Card WG リネーム**: WG を改称、 Sam Morrow を IG/WG に追加 (#2827)
- **build(deps) 群**: vitest / typescript-eslint / tsx / eslint / actions 各種を bump

#### 2025-06-18 → 2025-11-25 で導入された主要 SEP (新着補完)

- **SEP-973 Icons metadata**: tools/resources/prompts にアイコンを公開する metadata
- **SEP-835 Incremental scope consent**: `WWW-Authenticate` 経由の段階的スコープ同意
- **SEP-1036 URL mode elicitation**: `ElicitResult` / `EnumSchema` 標準化、URL mode elicitation
- **SEP-1330 titled / multi-select enum elicitation**: enum の titled / multi-select 化
- **SEP-1577 Sampling に tool calling**: `tools` / `toolChoice` を sampling に追加
- **SEP-1686 Tasks (実験的)**: 永続的リクエストの polling / deferred result 取得
- **SEP-991 OAuth Client ID Metadata Documents**: 推奨 client 登録メカニズムとして追加 (PR #1296)
- **SEP-1613 JSON Schema 2020-12 をデフォルト方言に**: schema dialect を明示固定
- **OpenID Connect Discovery 1.0 対応**: 認可サーバ発見を OIDC Discovery 準拠に拡張 (PR #797)

#### 2025-11-25 リリースの破壊的変更

| 変更 | 影響 |
|------|------|
| HTTP 403 for invalid Origin (PR #1439) | Streamable HTTP transport で不正 Origin に 403 必須化 — クライアント挙動に影響 |
| OAuth Protected Resource Metadata の RFC 9728 整合 (SEP-985) | `WWW-Authenticate` ヘッダ optional、`.well-known` への fallback — 既存実装の挙動見直し |
| 入力検証エラーは Tool Execution Error として返す (SEP-1303) | Protocol Error ではなく Tool Execution Error 方針に変更 |

#### 2025-11-25 後の変更点（次回リリース向けドラフト）

- **SEP-2575 unsupported protocol error code 追加**: SEP-2575 stateless MCP に対応するため、 unsupported protocol error のカスタムエラーコードを導入
- **SEP-2596: Specification Feature Lifecycle and Deprecation Policy**: 仕様の機能ライフサイクルと deprecation policy を明文化 (#2596)
- **SEP-2577: Roots / Sampling / Logging を deprecate**: 三機能の deprecation を進行 (#2577)
- **SEP-2106: Tools `inputSchema`/`outputSchema` を JSON Schema 2020-12 準拠化**: tools の schema を JSON Schema 2020-12 dialect に統一 (#2106)
- **SEP-2164: resource not found error code 標準化**: error code を -32602 で標準化 (#2164)
- **SEP-2468: MCP Auth Response で Issuer (iss) param 推奨化**: auth response に iss を推奨 (#2468)
- **SEP-2484: Standards Track SEPs は Final 到達に Conformance Tests 必須**: standards track SEP の Final 昇格に conformance tests を必須化 (#2484)
- **SEP-2663: Tasks Extension**: tasks extension SEP の Final 昇格と reformat (#2663)
- **SEP-2260 Final 昇格**: SEP-2260 を Final マーク
- **MRTR (Multi-Round Tool Result) スキーマ bugfix 群**: resultType 必須化の明確化と absent-field を後方互換として再フレーム、 notifications/message が request-scoped であることの明確化、 HTTP 後方互換 fallback の 400/404 body 検査による曖昧化解消
- **GitHub Copilot CLI / CIMD クライアント追加**: ChatGPT MCP Client support list に CIMD を、 clients list に GitHub Copilot CLI を追加 (#2741、d1b92de)
- **SEP-2575: Make MCP Stateless**: MCP をステートレス化する提案、 SEP-2567 の補完 (init removal) として位置付け (#2575)
- **SEP-2567: Sessionless MCP via Explicit State Handles**: explicit state handle 経由で sessionless MCP を実現する提案。 Final / Accepted ステータスに昇格、 spec language を draft に適用済み。 stdio SHOULD NOT、 list endpoints が request authorization で変化することを clarify、 connect_database example と Future Work を追加
- **SEP-2567 ↔ SEP-2575 関係再定義**: SEP-2567 を SEP-2575 の opt-in predecessor ではなく complementary (init removal) として再フレーム
- **MRTR スキーマ整備**: `IncompleteResult` を `InputRequiredResult` に rename、Multi-Round Tool Result の draft/schema.mdx 修正
- **Augmented Tool Call 拡張**: tasks augmented tool call フローのドキュメント更新
- **elicitation/roots ダイアグラム更新**: elicitation diagrams と roots ページのリフレッシュ
- **`requestState` 仕様改訂**: requestState ハンドリング要件のアップデート
- **`URLElicitationRequired` エラー削除**: URL Elicitation 自体は MRTR 経由で継続サポート、エラーは廃止
- **SEP リジェネレート**: prettier 適用 + SEP 再生成
- **Core Maintainer Emeritus 移行**: Che Liu, Basil Hosmer を Core Maintainer Emeritus へ移動
- **SDK Working Group チャーター**: SDK WG charter 追加 (#2662)、 work items を spec implementation と tiering に整理
- **`#general-sdk-dev` Discord チャンネル化**: SDK WG 用 Discord チャンネル指定
- **vm2 3.11.3 セキュリティバンプ**: GHSA-vwrp-x96c-mhwq 対応 (#2711)
- **TypeScript 6.0.3 / eslint 10.3.0 / typescript-eslint 8.59.1-8.59.3**: 依存バンプ群 (#2610, #2676, #2677)
- **typescript-json-schema 0.67.1 pin**: 0.67.2 → 0.67.1 への revert pin (#2714)
- **fast-uri 3.1.2**: dev deps の fast-uri バンプ (#2715)
- **Ruby client 明示的 connect サンプル**: Ruby client サンプルを明示的な connect 化 (#2685)

#### 2025-11-25 の主要な変更点

- **Interceptors WG チャーター**: Interceptors Working Group チャーター策定 (#2619)
- **MCP クライアントベストプラクティス**: docs に MCP クライアントベストプラクティス追加 (#2582)
- **Runbear クライアント追加**: Example Clients に Runbear 追加 (#2572)
- **`.well-known/agent-skills/` 発見エンドポイント**: MCP skills を `.well-known/agent-skills/` 経由で公開
- **Mintlify ディレクトリシンボリックリンク対応**: draft-sep / search-mcp-github skill の Mintlify インデックス修正 (#2597, #2604)
- **single Core Maintainer 承認明確化**: WG charter PR の single Core Maintainer 承認明確化 (#2592)
- **fork-based contribution first-class**: フォークベースコントリビューションをファーストクラスパスに
- **TypeScript 6.0.3**: TypeScript 6.0.2 → 6.0.3 (#2610)
- **HTTP Standardization (SEP-2243)**: HTTP トランスポートの標準化マージ
- **Deterministic tools/list ordering**: ツールリストの決定的順序仕様追加
- **Tool-name disambiguation**: ツール名の曖昧さ排除の明確化
- **Skills Over MCP IG**: Skills Over MCP Interest Group チャーター策定
- **Inspector V2 WG**: Inspector V2 ワーキンググループチャーター策定
- **mcpc CLI クライアント更新**: (#2576)
- **SEP-2207 OIDC リフレッシュトークンガイダンス**: (#2207)
- **Ruby SDK ドキュメント**: build-client ドキュメントに Ruby SDK サンプル追加 (#2486)
- **SEP-2350 クライアントサイドスコープ蓄積**: (#2350)
- **TypeScript 6.0.2**: TypeScript 5.9.3 → 6.0.2 (#2503)

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

**現行バージョン**: **v1.7.4 (2026-06-04)**

**チェックアウト状態**: `v1.7.4` (タグ一致)

#### v1.7.4 の主要な変更点（2026-06-04）

- **SECURITY: lazy-auth-server token exchange で PKCE 必須化 + redirect_uri バインド** (#681)
- **lazy-auth-server の base path 配下マウント対応**: base path 配下へのマウントをサポート (#683)
- **ext-apps 1.7.4 bump** (#685)

#### v1.7.3 の主要な変更点

- **lazy-auth-server example 追加**: lazy 認証サーバの example を追加 (#679)
- **ext-apps 1.7.3 bump**: ext-apps を 1.7.3 に bump (#680)

#### v1.7.2 の主要な変更点

- **example transitives パッチ群 bump**: example 配下の transitive 依存を最新パッチへバンプ (#658)
- **pdf-lib → @cantoo/pdf-lib フォーク切替**: pdf-server で maintained な `@cantoo/pdf-lib` fork へスイッチ（メンテナンス放棄対応） (#651)

#### v1.7.1 の主要な変更点

- **PDF Server lazy フォーム抽出**: range transport によるレイジーフォーム抽出と incremental viewer scans (#639)
- **PDF Server キャッシュ共有**: サーバーインスタンス間でのキャッシュ共有とフォームパースの dedupe (#637)
- **qr-server FastMCP host/port サポート**: Docker 互換性のための host/port 渡し (#372)
- **PostMessageTransport source 検証**: PostMessageTransport の source 検証ユニットテスト追加 (#536)
- **buildAllowAttribute ユニットテスト**: (#541)
- **CONTRIBUTING.md ガイド更新**: package preview のコントリビューティングガイド更新 (#601)

#### v1.7.0 の主要な変更点

- **ツール登録仕様 (WebMCP-style)**: Host から呼び出される Apps のツール登録を仕様追加 (#72)
- **MCP app sampling サポート**: stock SDK types 経由の MCP app sampling 対応 (#530)
- **Zod jitless デフォルト化**: Zod を jitless デフォルトに、`allowUnsafeEval` opt-out 追加（CSP strict 環境対応） (#618)
- **pre-handshake guard 統一**: `console.warn` に統一し、handshake 前のリクエストをガード (#620, #630)
- **one-shot handler 登録警告**: `connect()` 後の one-shot handler 登録時に警告 (#629)
- **React StrictMode クリーンアップ**: StrictMode での cleanup と late-handler guard の再登録緩和 (#631)
- **React autoResize 転送**: `useApp` から `App` へ `autoResize` を転送 (#622)
- **types 強化**: `McpUiToolMeta` での csp/permissions を never で禁止 (#624)、stale resourceUri JSDoc 削除 (#626)
- **依存関係パッチバージョンバンプ**: vite, hono, @hono/node-server のパッチバージョンへのバンプ (#616)

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

**現行バージョン**: client/v7.1.1 (2026-05-09)

#### v7.1.1 の主要な変更点

- **sandbox proxy iframe timeout cancel**: effect cleanup 時に sandbox proxy iframe timeout をキャンセル、 StrictMode での unhandled rejection を防止 (#190)

#### v7.1.0 の主要な変更点

- **`hostInfo`/`hostCapabilities` props**: `AppRenderer` に `hostInfo` と `hostCapabilities` props 追加 (#179)

#### v7.0.0 の主要な変更点

- **レガシー仕様削除**: レガシー仕様の完全削除（**破壊的変更**） (#185)
- **major bump 修正**: semantic release で前回 commit が major bump 失敗していたため修正 (#187)

#### 破壊的変更

| バージョン | 変更 |
|-----------|------|
| v7.0.0 | レガシー仕様の完全削除 |
| v6.0.0 | 廃止コンテンツタイプ削除、MIMEタイプ変更 |
| v5.0.0 | `delivery` → `encoding`、`flavor` → `framework` |

#### 参考リンク

- [MCP-UI](https://github.com/MCP-UI-Org/mcp-ui)

---

### NLIP (Natural Language Interaction Protocol)

**現行バージョン**: 1st edition (Ecma 承認 2025-12-10)

**管理**: Ecma TC56 NLIP（Ecma International）

**注目**: AI エージェント間および人間 ↔ AI エージェント間の **アプリケーション層通信プロトコル** の業界標準。 2025-12-10 に Ecma International が正式承認、 2026-01-25 に ISO へ提出済み。 Claude Skills 互換 reference 実装が 2026-02-28 公開予定（reference 実装側）。

#### 1st edition 構成（全 6 文書）

| 標準 | タイトル | 役割 |
|------|---------|------|
| **ECMA-430** | Natural Language Interaction Protocol (NLIP), 1st edition | プロトコル本体仕様（agent-to-agent / human-to-agent application-level） |
| **ECMA-431** | NLIP over HTTP/HTTPS binding | HTTP/HTTPS バインディング |
| **ECMA-432** | NLIP over WebSocket binding | WebSocket バインディング（CBOR + UTF-8 JSON フォールバック、 RFC 8949） |
| **ECMA-433** | NLIP over AMQP binding | AMQP バインディング |
| **ECMA-434** | Security profiles for NLIP | Agent Security Profiles（NLIP 適合実装に対する mandatory 要件） |
| **ECMA TR/113** | Explanatory guide to NLIP | informative な解説書（design philosophy / use-cases / sample exchange） |

#### リポジトリ構成（追跡対象）

- **`nlip-project/nlip_spec`**: Ecma 承認版 1st edition の README index（本サブモジュール）
- **`nlip-project/ecma_draft` / `ecma_draft1`**: First Draft 期のフィードバック収集リポ（履歴的）
- **`nlip-project/documents`**: TC-56 NLIP 関連ドキュメント
- **`nlip-project/security_guidelines`**: ECMA-434 のコンパニオン
- **`nlip-project/nlip_spec_swarm` / `nlip_web` / `nlip_agents` / `kivy-chat-mach2`**: 参照実装系

#### 主要な特徴

- **マルチトランスポート対応**: HTTP/HTTPS / WebSocket / AMQP の 3 系統バインディング（用途に応じて選択可能）
- **WebSocket × CBOR**: マルチモーダル通信のためのコンパクト・効率的バイナリエンコーディング、 JSON フォールバックも保証
- **Security Profiles 標準化**: NLIP 適合を主張する実装には ECMA-434 への準拠が **mandatory**
- **Royalty-free open source 標準**: Ecma International ガバナンスのもと royalty-free
- **A2A / MCP との位置関係**: A2A は agent ↔ agent の opaque 通信、MCP は agent ↔ tool/data の通信。 NLIP は **agent ↔ agent / human ↔ agent の natural-language application-level** 通信を担当する補完的位置

#### 参考リンク

- [nlip_spec (GitHub)](https://github.com/nlip-project/nlip_spec)
- [NLIP Project site](https://nlip-project.org/)
- [Ecma International - ECMA-430](https://ecma-international.org/publications-and-standards/standards/ecma-430/)
- [Ecma International - ECMA-431 (HTTP)](https://ecma-international.org/publications-and-standards/standards/ecma-431/)
- [Ecma International - ECMA-432 (WebSocket)](https://ecma-international.org/publications-and-standards/standards/ecma-432/)
- [Ecma International - ECMA-433 (AMQP)](https://ecma-international.org/publications-and-standards/standards/ecma-433/)

---

### OpenResponses

**現行バージョン**: 継続的デプロイ（バージョンタグなし）

#### 最近の変更点

- **Response phase コンパクション**: assistant message phase パラメータをソーススキーマに追加。phase スキーマと compaction スキーマを整合化、コンプライアンステストでカバー、neutral モデル説明導入 (#68)
- **compact response エンドポイント**: 仕様に compact response エンドポイント追加。compaction エンドポイントのドキュメント化 (#68)
- **WebSocket モードサポート**: OpenResponses に WebSocket モード実装（新規の大きな機能） (#71)
- **WebSocket 復旧コンプライアンスカバレッジ**: WebSocket recovery compliance テスト追加
- **WebSocket モードドキュメント整備**: WebSocket モードのドキュメントとバリデーション整合化
- **mise version bump**: `mise-bun` 環境のバージョン bump (#72)
- **composed schema fields レンダリング**: リファレンスドキュメントで composed schema fields をレンダー
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

### UTCP (Universal Tool Calling Protocol)

**現行バージョン**: v1.1（仕様、 タグなし latest 追従、 直近 spec commit 2026-05-18）

**チェックアウト状態**: `75efb05` (2026-06-03 contributors update、 ブランチ HEAD。 前回記録以降は contributors data の自動更新のみで仕様変更なし)

**管理**: Universal Tool Calling Protocol コミュニティ（独立 OSS）

**注目**: MCP の **構造的代替案 / 補完案**。 MCP が「proxy 経由でツール呼び出し」する一方、 UTCP は **agent が discovery 後に native endpoint (HTTP/gRPC/WebSocket/CLI) を直接叩く**設計で、 wrapper tax + latency を排除し、 既存の auth/billing/security をそのまま活かせる。 v1.0 で plugin-based 構成へ全面再設計、 v1.1 で multi-protocol manual の secure-by-default 化。

#### v1.0 → v1.1 の変更点

- **`allowed_communication_protocols` 新フィールド**: call template (manual configuration) に optional フィールド追加
- **Secure by default**: 未指定時、 manual は自身のプロトコル種別のツールしか登録/呼び出し不可 (HTTP manual は HTTP tools のみ、 CLI manual は CLI tools のみ)
- **マルチプロトコル明示化**: 複数プロトコル混在 manual は `allowed_communication_protocols` を明示設定する必要がある
- **dual license 明確化**: ライセンス記載を明確化 (commit `29bbc4e`)
- **API docs 同期**: `python-utcp@4ed0a48` から API docs を再同期 (commit `6bd28ae`)

#### v1.1 の破壊的変更

| 変更 | 影響 |
|------|------|
| マルチプロトコル manual の暗黙許可廃止 | v1.0 では HTTP manual に CLI tool を混在登録できたが、 v1.1 では `allowed_communication_protocols` に明示列挙しないとフィルタアウト。 動作する設定が静かに無効化される可能性 |

#### v1.0 の主要な特徴

- **Plugin Architecture**: コア機能を pluggable component に分割、 modularity / testability / packaging 向上
- **Multiple Protocol Support**: HTTP / CLI / WebSocket / Text / **MCP** をプラグイン経由でサポート（MCP も plugin として包摂）
- **Enhanced Data Models**: Pydantic モデルへ統一、 包括的バリデーション
- **Advanced Authentication**: API key / OAuth / カスタム auth など拡張認証
- **Better Error Handling**: シナリオごとの specific exception 型
- **Async/Await Support**: 完全非同期クライアントインタフェース
- **Performance Optimizations**: クライアントとプロトコル実装の最適化
- **OpenAPI 拡張**: agent-focused enhancements（tags、 average_response_size、 multi-protocol、 direct execution instructions）を OpenAPI に追加
- **Dual license clarification**: 直近 commit でデュアルライセンス周りを整理

#### 関連リポジトリ（org エコシステム）

| リポ | 役割 |
|------|------|
| `utcp-specification` | 仕様本体（本サブモジュール） |
| `python-utcp` | 公式 Python 実装 |
| `typescript-utcp` | 公式 TypeScript 実装 |
| `utcp-agent` | 5 行未満で API/native endpoint 直叩きできる ready-to-use agent |
| `code-mode` | MCP/UTCP ツールを **コード実行経由** で呼び出す plug-and-play ライブラリ |

#### MCP との位置関係

| 観点 | MCP | UTCP |
|------|-----|------|
| 呼び出し方式 | proxy server (wrapper) 経由 | agent が native endpoint を直接 |
| latency | wrapper hop あり | hop なし |
| auth/billing | MCP server で再実装 | 既存システムを再利用 |
| 互換性 | MCP プロトコル独自 | OpenAPI 拡張で既存 API 流用 |
| MCP 取り込み | n/a | MCP プロトコルを plugin として包摂 |

#### 参考リンク

- [utcp-specification (GitHub)](https://github.com/universal-tool-calling-protocol/utcp-specification)
- [Universal Tool Calling Protocol org](https://github.com/universal-tool-calling-protocol)
- [www.utcp.io](https://www.utcp.io/)
- [python-utcp](https://github.com/universal-tool-calling-protocol/python-utcp)
- [typescript-utcp](https://github.com/universal-tool-calling-protocol/typescript-utcp)

---

### webmcp-tools

**現行バージョン**: 継続的デプロイ（バージョンタグなし）

**管理**: Google Chrome Labs

#### 2026-06-09 新着 (Angular 22 / parametersJsonSchema / french-bistro agent)

- **french-bistro demo に in-page agent 追加** (#214)
- **`parametersJsonSchema` へ移行**: tool 定義で `parameters` に代わり `parametersJsonSchema` を使用 (#220)
- **leather-bag demo を Angular 22 へ更新**: Angular 流の WebMCP tools 公開、 dynamic form 挙動の追加

#### 2026-06 新着 (Page Agent demo / Sport Shop evals / permission policy)

- **permission policy 厳格化**: permission policy を tighten
- **Page Agent demo 追加**: Page Agent デモを追加
- **Sport Shop evals**: Sport Shop の example evals 追加、 pickup / promos / 追加カートツールを Sport Shop に追加
- **Pizza-Maker tools クロスオリジンテスト公開**: cross origin testing 向けに Pizza-Maker tools を公開
- **eval レポート改善**: eval 名付きのレポート改善、 sidecar UI 改善
- **AWESOME_WEBMCP に webmcp.cool 追加**: AWESOME_WEBMCP.md に webmcp.cool を追加

#### 最近の変更点

- **Search product 全体公開ツール化**: Search product をグローバルに利用可能なツールへ昇格
- **french-bistro tool 説明更新**: french-bistro デモのツール説明改善
- **input schema 削除**: 不要な input schema を削除
- **sport shop search results ツール**: スポーツショップで検索結果を読むツール追加
- **demo サイト表記削除**: 「demo site」表現を削除（プロダクト感の向上）
- **より複雑な hotel example**: ホテル検索の複雑化、 検索ロジック修正
- **autocomplete values 追加**: name/phone form フィールドへの autocomplete 値追加 (#159, #160)
- **Leather Bag デモ修正**: Leather Bag デモのイメージ修正 (#155)
- **registered-purchase 機能**: registered-purchase 機能追加 (#149)
- **unregisterTool 削除**: unregisterTool 呼び出し削除 (#153)
- **untrustedContentHint 追加**: `shared/types/webmcp.d.ts` に untrustedContentHint 追加 (#152)
- **Pizza toppings 修正**: (#150)
- **Live demo リンクフォーマット修正**: README の live demo リンクフォーマット修正
- **Flight Search flexible routes**: フライト検索のフレキシブルルート対応・one-way/round-trip 対応 (#141)
- **Flight Search build 修正**: return flight properties をオプショナル化 (#144)
- **french-bistro demo Lighthouse 改善**: Lighthouse audit スコア改善
- **Morning ritual coffee demo**: persistent state と index entry 付きで実装（一時的に revert 状態）
- **Maze player trail animation 修正**: 迷路プレイヤーの軌跡アニメーション修正 (#133)
- **Label `for` attribute オプション**: アクセシビリティ改善 (#146)
- **依存関係更新**: Hono 4.12.14、basic-ftp 5.3.0、protobufjs 7.5.5、vite 8.0.5、vite 7.3.2 等

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

## Payments / Agentic Commerce

決済 / agentic commerce 関連プロトコルとその仕様。 既存の generic protocols と分離して管理（`payments/` ディレクトリ配下）。 軸は次の 4 つ:

1. **Commerce flow**: ACP / AP2 / UCP — 注文 / カート / 支払いハンドラ等の業務プロトコル
2. **Crypto-native payment**: x402 — HTTP ネイティブ暗号通貨決済
3. **Agent identity (cryptographic verify)**: Visa Trusted Agent Protocol、 Mastercard Verifiable Intent — 大手金融プレイヤーが回す agent identity / authorization の cryptographic 証明標準
4. **業界横断パートナーシップ**: AP2 と Verifiable Intent の周りに Adyen / Worldpay / Fiserv / Checkout.com / Basis Theory / Amex / JCB / PayPal などほぼ全大手が集結

---

### ACP (Agentic Commerce Protocol)

**現行バージョン**: API Version 2026-04-17

**管理**: OpenAI & Stripe

#### v2026-04-17 後の変更点

- **SEP: Feed API Upsert Products Response に Feed Update ID 追加** (2026-06-04、 #260)
- **Fulfillment Details on Checkout Complete (SEP)**: チェックアウト完了時に履行詳細（fulfillment details）を返却できるよう許可する SEP (#200)
- **Suggested Pricing on Checkout Create (SEP)**: チェックアウト作成時に suggested pricing を提示できるようにする SEP (#201)
- **`delegate_payment` OpenAPI examples error envelope 修正**: `delegate_payment` の OpenAPI 例で error envelope を unwrap する形に修正 (#243)
- **refund amount example スキーマ整合**: spec/2026-01-30 の refund amount example の型を schema に合わせる修正 (#249)
- **Stale PR Reminder Workflow**: PR が古くなったときに reminder を送る workflow を追加 (#240)
- **Order Schema Post-Checkout SEP**: チェックアウト後の Order Schema アライメント SEP (#232)
- **`UpsertProductsResponse` JSON Schema 追加**: feed JSON Schema バンドルに `UpsertProductsResponse` 追加 (#241)
- **Meta TSC メンバー追加**: Meta を TSC メンバーに追加 (#236)
- **Address.company 説明修正**: コピーペーストエラー修正 (#193)
- **`intervention_required` ドキュメント追加**: RFC エラーコードドキュメントに `intervention_required` 追加 (#143)
- **intent traces examples**: 全 reason code の intent traces 例追加 (#151)
- **Agentic Commerce Inc. CLA 署名**: Catalog 関連で Agentic Commerce Inc. を Corporate CLA 署名者に追加 (#226)

#### v2026-04-17 の主要な変更点

- **Cart Capability SEP**: Cart Capability 追加 (#188)
- **Product Feeds API SEP**: Product Feeds API 追加 (#190)
- **Marketing Consent SEP**: マーケティング同意フロー追加 (#199)
- **Markdown Content Specification (CommonMark)**: Markdown コンテンツ仕様策定 (#212)
- **Payment Intent (capture vs authorize)**: PaymentHandler `display_name` 含む支払い意図 (#130)
- **Payment Handler 表示順序**: マーチャント提案の表示順序サポート (#133)
- **Mandatory Idempotency Requirements**: 冪等性要件と保証の義務化 SEP (#121)
- **Rich Post-Purchase Lifecycle Tracking**: Order スキーマに購入後ライフサイクル追跡追加 (#106)
- **Discovery RFC seller terminology**: discovery RFC を seller 用語に再構成 (#176)
- **TSC Operating Model**: TSC 運営モデルドキュメント追加 (#184)
- **CLA 署名者追加**: Meta Platforms, Affirm, PayPal, Agentic Commerce (Catalog) が CLA 署名
- **`risk_signals` 仕様修正**: `delegate_payment` で空の risk_signals を許可 (#214)
- **ガバナンスモデル改訂**: TSC, DWGs を含むガバナンス構造の見直し (#173)
- **Webhook Signing Replay Protection 強化**: リプレイ攻撃防止の強化 (#160)
- **Delegated Authentication API**: マーチャント指定認証の API コントラクト (#93)
- **Discovery Well-Known Document 実装**: (#137)
- **MCP Transport Binding**: Agentic Checkout 向け MCP トランスポートバインディング (#139)

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

### AP2 (Agent Payments Protocol)

**現行バージョン**: v0.2.0 (2026-04-28)

**管理**: Google Agentic Commerce

**注目**: 2026-04-28 に **v0.2.0 リリース**。`Release of V2 (#233)` として AP2 V2 仕様の正式リリースに到達。 PayPal / Adyen / Amex / Mastercard / JCB / Worldpay 等 60+ パートナーが集結する業界横断ハブ。

#### v0.2.0 後の変更点

- **uvlock 削除**: uv.lock を repository から除外 (#246)
- **CHANGELOG.md 更新**: 0.2.0 リリースに合わせた CHANGELOG 更新 (#239)
- **動画タイトル更新**: README 動画タイトル修正 (#238)
- **CONTRIBUTING.md 更新**: コントリビューションガイドライン更新 (#240)

#### v0.1.0 → v0.2.0 の主要な変更点

- **AP2 V2 リリース**: V2 仕様の正式リリース (#233)
- **PaymentReceipt**: トランザクション確認オブジェクト実装 (#110)
- **X402 決済**: x402 payment method 統合（Python サンプル） (#121)
- **Go サンプル**: スタンドアロン Go 実装例 (#101)
- **Vertex AI 認証**: Google API キーに加えて Vertex AI 認証サポート追加 (#48)
- **X-A2A-Extensions ヘッダーロギング**: サーバーミドルウェアでヘッダーロギング (#29)
- **UCP 統合ドキュメント**: Universal Commerce Protocol 連携 (#138)
- **Kite AI / Global Payments / Tether / Solana / OKX / Nexi**: 多数のパートナー追加

#### 参考リンク

- [AP2 Protocol](https://github.com/google-agentic-commerce/AP2)

---

### UCP (Universal Commerce Protocol)

**現行バージョン**: v2026-04-08 (2026-04-13)

**チェックアウト状態**: `v2026-01-23-134-gd984d4b` (`git submodule status` は祖先タグ v2026-01-23 を表示するが、 HEAD は v2026-04-08 を超過、 HEAD 2026-06-03)

#### 2026-06 新着 (split payments extension / idempotency 契約)

- **split payments extension 追加**: 分割支払い拡張を導入（discount / loyalty に続く拡張） (#409)
- **idempotency payload-mismatch 契約明文化**: idempotency の payload 不一致時の契約を明文化 (#485)
- **Amadeus ロゴ刷新**: lodging セクションで Amadeus ロゴを強調 (#488)、 legacy Amadeus SVG を更新版に置換 (#468)
- **stylelint / SVG フォーマット修正**: local_preview と site ディレクトリを stylelint 対象外に (#495)、 pre-commit SVG formatting と trailing newline 修正 (#491)

#### v2026-04-08 後の変更点

- **`feat`: loyalty extension for catalog/cart/checkout capability**: ロイヤルティ拡張を catalog / cart / checkout capability に追加（discount 拡張に続く 2 つ目の正式拡張） (#340)
- **schema-validated documentation examples**: ドキュメント例を schema 検証ベースに整備 (#359)
- **partner ロゴ群追加**: documentation assets に partner logos と configuration 追加、 logo フォーマットと layout を整理 (#453)
- **idna / pymdown-extensions 依存バンプ**: idna 3.11 → 3.15 (#457)、 pymdown-extensions 10.21.2 → 10.21.3 (#456)
- **PR auto-labeler permissions 修正**: PR auto-labeler の権限を修正 (#454)
- **schema refactor**: schema references を common types に整理 (#436)
- **profile schemas 検証修正（破壊的）**: profile schemas をバリデーションと endpoint contract に合わせて修復、 後方互換を破るスキーマ訂正 (#429)
- **urllib3 v2.7.0 セキュリティバンプ**: urllib3 2.6.3 → 2.7.0 (#434)
- **build_local.sh のサーバー起動削除**: build_local.sh から server start を除去 (#430)
- **Identity Linking OAuth 2.0 基盤**: capability-driven scopes をベースとした identity linking の OAuth 2.0 foundation 追加（**破壊的変更**） (#354)
- **attribution フィールド追加**: platform referral context 用の attribution フィールド追加 (#391)
- **core-concepts 拡充**: 包括的な UCP プロトコル概要を core-concepts ドキュメントに統合 (#336)
- **glossary / acronym 標準化**: 中央集約型の glossary と acronym standards 追加 (#241)
- **deprecated checkout id 修正**: playground payload から deprecated checkout id を omit (#332)
- **法人レジストリブロック**: corporate registries のブロック (#411)
- **typo / formatting 修正**: index と versioning ドキュメントの typo 修正と formatting 改善 (#416)
- **Twum Djin ガバナンス評議会追加**: Governance Council に Twum Djin 追加 (#395)
- **Configure Site URL 共通アクション化**: CI ステップを composite action に抽出 (#382)
- **拡張性・前方互換ガイドライン追加**: ドキュメントに extensibility と forward compatibility ガイドライン追加 (#290)
- **discounts 拡張スキーマ修正**: ドキュメント例と discounts 拡張スキーマの不整合修正 (#371)
- **Tech Council メンテナーリスト更新**: メンテナー一覧更新
- **legacy PR テンプレート削除**: (#377)
- **signatures.md テキストダイアグラム現代化**: (#331)
- **create_cart `ucp_agent` パラメータ修正**: REST オペレーションで欠落していた `ucp_agent` パラメータ追加 (#362)
- **Total/Totals フィールドレンダー修正**: schema reference page で Total/Totals が表示されない問題修正 (#352)
- **MCP レスポンス例 entity wrapper 削除**: MCP レスポンス例から不要な entity wrapper を除去 (#360)
- **ドキュメント正確性修正**: 仕様例の inconsistency / accuracy 修正 (#363, #365)
- **Profile 例修正**: Playground widget 内の profile examples 修正 (#236)
- **lockfile package registries 標準化**: lockfile の package registries 標準化 (#368)
- **super linter アップグレード**: (#372)
- **PR auto-labeler 追加**: (#366)
- **line item ids の識別差別化**: line item ids と item ids を区別 (#112)

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
| profile schemas 検証修正 (#429, v2026-04-08 後) | profile schemas の互換破壊的訂正、 既存実装の再検証必要 |
| Identity Linking OAuth 2.0 foundation (#354, v2026-04-08 後) | capability-driven scopes へ移行、認可フロー再設計 |
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

### x402 (Internet Native Payments)

**現行バージョン**: Go v2.9.0 / Python v2.7.0 / TypeScript npm-@x402/\* v2.10.0 (npm-x402@v1.1.0 legacy バンドル含む)

**注目**: リポジトリが foundation repo に移動中。README にリポジトリ移動ノート追加 (#40)、main ブランチを foundation repo に合わせる形で bump (#93)。

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

### Visa Trusted Agent Protocol

**現行バージョン**: 初期スペック + sample 実装（タグなし、 commit 6 件、 2026 年内に立ち上げ）

**管理**: Visa Inc.（クレジットカード大手）

**注目**: Agentic commerce での **agent identity / authorization 標準化**。 既存の payments 系（ACP / AP2 / UCP / x402）の **identity 補完レイヤ** として位置。 大手金融プレイヤー（Visa）が回した数少ない agentic commerce identity 標準。

#### 主要な特徴

- **Cryptographic Identity Proof**: AI エージェントが merchant に対し、 自身の identity と user 委任権限を **暗号署名** で証明
- **署名コンテンツ**: timestamp / unique session identifier / key identifier / algorithm identifier を含む（リプレイ防止）
- **Context-Bound Security**: 全リクエストが merchant の **specific website + 操作中の正確なページ** に cryptographically lock。 認可の他所流用を不可能化
- **Replay 攻撃防止**: time-sensitive elements でリクエスト毎にユニーク化、 1 回限り有効
- **Customer / Payment Identifier 標準伝達**: 同意済み consumer の **PAR (Payment Account Reference)**、 verifiable consumer identifier、 loyalty number、 email、 phone などを query parameter 経由で merchant へ安全配信
- **Browse / Payment 双方の認可**: ブラウジングと支払いそれぞれの操作種別ごとに署名 bound
- **Anti-Fraud**: 認証済み agent と anonymous bot の区別を明確化、 chargeback / 不正取引削減

#### リポ構成

- 仕様 + sample 実装 (Quick Start で multiple components)
- **nonce validation サンプルコード** 追加済み（リプレイ防止検証実装の参考）

#### 参考リンク

- [visa/trusted-agent-protocol (GitHub)](https://github.com/visa/trusted-agent-protocol)

---

### Mastercard Verifiable Intent

**現行バージョン**: v0.1.0 (Draft)、 直近 push 2026-04-20、 v0.1.0 タグから +4 commits

**管理**: Mastercard（共同開発: Google）

**注目**: 2026-03-05 オープンソース化。 Visa Trusted Agent Protocol と並ぶ大手金融プレイヤーの agent identity / authorization 標準。 **SD-JWT (Selective Disclosure JWT) ベース**の cryptographic credential chain で「user → agent への delegation scope」を tamper-evident に証明。 AP2 / UCP との相互運用を明示的に設計（rival ではなく complementary）。

#### 主要な特徴

- **SD-JWT credential format**: Selective Disclosure 機構により、 必要最小限の情報だけを各 party に開示（プライバシー保護寄り）
- **Layered tamper-evident chain**: AI agent の commercial action が user delegation scope 内であることを cryptographic に証明
- **2 つの実行モード**:
  - **Immediate**: user が都度確認（user-confirmed）
  - **Autonomous**: agent に委任（agent-delegated）
- **標準ベース**: FIDO Alliance / EMVCo / IETF / W3C
- **AP2 / UCP との相互運用**: complementary 標準として設計
- **Reference 実装**: Python 100% で公式 reference implementation 同梱

#### 業界コミットメント (2026-03-05 発表時)

| 企業 | 役割 |
|------|------|
| Google | 共同開発 |
| Fiserv / IBM / Checkout.com / Basis Theory / Getnet | 支持表明 |
| Adyen / Worldpay (Global Payments) | 支持表明 |

#### 参考リンク

- [agent-intent/verifiable-intent (GitHub)](https://github.com/agent-intent/verifiable-intent)
- [verifiableintent.dev](https://verifiableintent.dev/)
- [Verifiable Intent spec overview](https://verifiableintent.dev/spec/)
- [Mastercard - Verifiable Intent](https://www.mastercard.com/global/en/news-and-trends/stories/2026/verifiable-intent.html)

---

### 既存 commerce 系プロトコル位置関係まとめ（横断比較）

| プロトコル | 担当領域 | 管理 |
|-----------|---------|------|
| **ACP** (Agentic Commerce Protocol) | Order / Cart / Payment Handler レイヤ | OpenAI + Stripe |
| **AP2** (Agent Payments Protocol) | Payment Receipt / Payment method 統合 | Google + 60 partners |
| **UCP** (Universal Commerce Protocol) | Cart / Catalog / Order / Discount / Identity Linking | Universal Commerce Protocol コミュニティ |
| **x402** | Crypto-native HTTP payment | Coinbase |
| **Visa Trusted Agent Protocol** | Agent identity / authorization の cryptographic proof（merchant 側 verify） | Visa |
| **Mastercard Verifiable Intent** | SD-JWT chain で user → agent delegation scope を verify（プライバシー保護寄り） | Mastercard + Google |

---

## Google Cloud / ADK

### ADK Python

**現行バージョン**: **v2.2.0 (2026-06-04)** / v1.35.0 (stable lts、 2026-06-10)

**チェックアウト状態**: `ca8baf19` (v2.2.0 リリース後の main、 HEAD 2026-06-09 付近)

**注目**: v2.0.0 GA（2026-05-19）後、 **v2.1.0 → v2.2.0（2026-06-04）と 2.x 系リリースが軌道に乗った**。 v2.2.0 は **Google GenAI SDK v2.0.0 対応**、 **AutoTracingPlugin（OpenTelemetry 自動計装）**、 **RubricBasedMultiTurnTrajectoryEvaluator**、 native OTel `gen_ai.client.*` metrics など observability / eval 強化が柱で、 セキュリティ修正も多い（下記）。 LTS 側も **v1.35.0（2026-06-10）** がリリースされ、 Gemini 3.1 Live 系の修正（input transcription の扱い、 grounding metadata デフォルト、 history config injection）を backport。 v2.2.0 後の main では **E2BEnvironment（リモート sandbox workspace）**、 **GEPARootAgentOptimizer**、 BigQuery Agent Analytics plugin の ADK 2.0 producer cut、 `GOOGLE_GENAI_USE_ENTERPRISE` env var などが進行中。

#### v2.2.0 の主要な変更点（2026-06-04）

**[Security / 重要修正]**

- **Agent Builder file tools の path traversal ブロック** / **GCS skill 展開の Zip Slip 修正** / **v0 actions blob の unpickle 制限** / **`delete_session` の session 所有権検証** — エージェント実行系の防御強化
- **CVE-2026-48710 対応**: starlette / fastapi を bump

**[Features]**

- **AutoTracingPlugin**: OpenTelemetry 自動計装プラグイン
- **RubricBasedMultiTurnTrajectoryEvaluator**: ルーブリックベースのマルチターン軌跡評価
- **A2A 連携強化**: `to_a2a(Workflow)` 対応、 A2A message metadata の保持、 input-required vs auth-required の区別
- **`BaseSessionService.get_user_state(app_name, user_id)`** 追加、 **compaction summary に thoughts / tool calls を含める**

#### v1.34.0 / v2.0.0 GA 後の変更点（大半は v2.2.0 に取り込み済み）

**[運用 / アーキテクチャ]**

- **v2 リリースワークフローを v1 ブランチへ repoint**: v2 release workflows と manifests を v1 ブランチに付け替え、 main → v2 自動 sync workflow を削除（v1 ライン主導への運用転換）
- **Google GenAI SDK v2.0.0 対応**: Interactions で ADK を Google GenAI SDK v2.0.0 に対応
- **デフォルトモデル gemini-3-flash-preview 化**: agents のデフォルトモデルを gemini-3-flash-preview に変更（サンプル含む）
- **1.x agent config wiring 復元**: 後方互換のため 1.x agent config wiring を restore

**[Features]**

- **`request_input` tool 標準化**: LLM による能動的な確認のための request_input tool を標準化
- **Live `turn_complete_reason` サポート**: Live responses で turn_complete_reason を保持し safety 情報をキャプチャ
- **native OTel `gen_ai.client.*` metrics**: gen_ai.client.* メトリクスをネイティブ emit
- **`custom_metadata` 伝搬**: run requests の custom_metadata を run config へ転送
- **sandbox templates / snapshots からの生成**: template / snapshot から sandbox を作成可能に
- **data agent チャート生成 / artifact ロード**: data agent にチャート生成と artifact loading を追加
- **telemetry 拡充**: gen_ai.user.message log records への user.id 付与、 tool call エラーのテレメトリ修正、 transcription event order の保持
- **skills 系**: adk-review skill / adk-issue skill 追加、 PR triage と CLA verification の自動化、 SkillToolset の experimental タグ削除
- **api_server クライアント切断時 abort**: client drop 時に run を abort してリーク防止

**[Security / Hardening]**

- **ReadFileTool コマンドの shell escape**: ReadFileTool コマンドで path と range を shell escape（セキュリティ）
- **OAuth2 token requests の scope 省略**: auth の OAuth2 token request から scope を omit
- **non-mTLS hardcoded endpoints チェック**: check-file-contents.yml で非 mTLS の hardcoded endpoint を検出

**[Bug Fixes]**

- **MCP 初期化ハング / task group leak 防止**: MCP の initialization hang と task group leak を防止、 MCP tool エラー時の session drop も防止
- **Gemini 3.1 grounding metadata 損失防止**: Gemini 3.1 (live 含む) の grounding metadata の silent drop / transcription finished events を修正
- **graph chat agent wiring 修正**: graphs で chat agent の誤った wiring を防止
- **LoadSkillResourceTool 無限リトライ停止**: RESOURCE_NOT_FOUND 時の無限リトライループを停止
- **AgentTool sub-Runner plugin 修正**: AgentTool の sub-Runner で親の plugins を close しない、 prefix 設定時の skill tool 参照破損防止 + tool_filter サポート
- **state / live 修正**: NodeRunner path での state_delta 保持、 live session 再接続時の transparent config 保持
- **循環 import 解消**: base_tool / llm_request の循環 import 解消、 GCS evaluation managers / google-cloud-storage の遅延 import 化
- **perf(flows)**: agent tool unions の並列解決

#### v2.0.0 GA の主要な変更点（2026-05-19）

- **General Availability 到達**: multi-agent workflow と dynamic agent collaboration の production-grade foundations 確立
- **Multi-Agent Workflow Engine**:
  - **Flexible Execution Graphs**: 非線形・条件分岐・サイクリックなエージェント実行パターンを model-agnostic に編成するエンジン
  - **Intelligent Task Delegation**: 並列 sub-agent workers、 nested 階層チーム構成、 resilient な dynamic scheduling を有効にするモジュラー workflow abstraction
- **Dynamic Agent Collaboration**:
  - **Native Inter-Agent Routing**: inter-agent messaging、 control state handoffs、 context variable propagation を multi-agent flow 間でシームレスに編成
- **v2.0.0 alpha/beta パイプライン経由**: v2.0.0a1 → v2.0.0a2 → v2.0.0a3 → v2.0.0b1 → v2.0.0 GA という段階リリース。 main ブランチを v2.0.0 GA へ切り替え（v2 への transition）。

#### v1.34.0 の主要な変更点（2026-05-18）

**[Features]**

- **a2a persistent task stores サポート**: a2a に persistent task store サポートを追加 (cd78d87)
- **Gemini Live API in ADK evaluate**: ADK evaluate に Gemini Live API のサポートを追加、 evaluation_generator で `Runner.run_live()` を利用、 local / base eval service の live mode 対応 (790c9be)
- **mTLS Google Cloud Telemetry exporter**: Google Cloud Telemetry exporter に mTLS サポート (cfe8d2c)
- **A2aAgentExecutor factory in `to_a2a()`**: `to_a2a()` 関数に factory を渡せるよう拡張 (115124c)
- **non-ADK input-required events サポート**: ADK 外で生成された input-required events をサポート (6e53472)
- **user simulator conv history config**: user simulator に渡す会話履歴に tool calls/responses を含めるか設定可能化 (baf7efb)
- **GCPSkillRegistry 実装**: ADK に `GCPSkillRegistry` を実装 (88ebd42)
- **Skill Registry 実装**: ADK に Skill Registry を実装 (380d261)
- **Agent Skill description validation 改善**: validation メッセージを informative 化 (9f38973)
- **ask_data_agent / ask_data_insights データ取得簡素化**: data retrieval ハンドリングを簡素化 (48f1b30)
- **McpToolset OAuth PKCE サポート**: McpToolset で OAuth PKCE をサポート (e7316dc)
- **CI: Gemini auto review/invoke workflows**: Gemini ベースの自動レビュー / invoke ワークフローを CI に追加 (fd8b492)

**[Bug Fixes]**

- **output_key state delta callback 可視性修正**: agents の output_key state delta を callback で見えるよう修正 (0524797)
- **Anthropic negative thinking_budget → adaptive thinking**: 負の thinking_budget を adaptive thinking にマッピング (03b915b)
- **refreshed OAuth2 credentials persist**: auth で refresh された OAuth2 credentials を store に永続化 (218ea76, #5329)
- **不要 OAuth フロー削除**: auth から不要な OAuth flows を削除 (c35a579)
- **Interactions API double-escape 防止**: dict 値の pre-serialization を回避 (85f397d)
- **CacheMetadata active-state invariant 強制 + fingerprint-only metadata 対応**: cache active state invariant を強制し、 performance analyzer で fingerprint-only metadata をハンドリング (76b9f0b, 9c5de58)
- **AnthropicLlm import OSError catch**: AnthropicLlm import 時の OSError を捕捉 (91cb5c6)
- **project_id fallback**: credentials に quota project が無い場合 project id にフォールバック (e377cb5)
- **SkillToolset dynamically loaded tools 修正**: 同一 invocation 内で SkillToolset に dynamically load された tool が見つからない問題を修正 (f9097cb)
- **sub live agent session resumption handle 分離**: sub live agent が parent から session resumption handle を継承して会話を中断する問題を修正 (8dd9147)
- **Anthropic tool_result blocks string content 保持**: Anthropic models の tool_result blocks で string content を保持 (9a1e75f, #5358)
- **Anthropic session resume で tool_use ID 保持**: Anthropic models の session resume で tool_use ID を保持 (327c45f, #5074)
- **空 GenerateContentResponse の正常扱い**: prompt feedback の無い empty GenerateContentResponse を成功として扱う (0cb9ae9)
- **AgentTool 結果保持**: `code_execution_result` と `executable_code` を AgentTool 内で保持 (7e61b51, #5481)
- **A2A 変換時 role 尊重**: events を A2A 形式に変換する際に user / agent role を区別 (59f7347)
- **AgentRegistry import eager raise**: a2a-sdk 不在時に AgentRegistry import で eagerly に raise (33cf6cb)
- **AnyIO CancelScope task boundary violations 防止**: MCP セッション作成失敗時の CancelScope violations を防止 (4309159)
- **HITL イベントの compaction 抑止**: Human-in-the-Loop に関わる events の compaction を防止 (bb2efb6)
- **live_session_id 保持**: function call ハンドリング時に live_session_id を保持 (07a9a01)
- **trace 含まれない場合 llm_response シリアライズ抑止**: trace に含まれない時のみ llm_response を json シリアライズ (1284493)
- **CLI deprecated フラグ＆ version-based service URI 削除**: CLI の deprecated flag と version-based service URI handling を削除 (e04a468)
- **gemini-3-flash-preview モデル更新**: hello world / session state agent サンプルのモデル更新 (6d89d21, 2d423e8)
- **gemma4 LiteLLM tool_responses role 使用**: gemma4 models で LiteLLM integration の tool_responses role を使用 (3d07960, #5650)

**[Performance]**

- **lazy-load サービスレジストリ**: `apps.app` を分割し service registry を lazy-load、 cold start を約 8% 削減 (bd062ec)
- **isEnabledFor で debug log evaluation ガード**: debug log evaluation を isEnabledFor でガード (57d8fc7)
- **find_context_parameter introspection キャッシュ** (ec54bd4)

**[Code Refactoring]**

- **`a2a_metadata` 定数化**: extension 開発者が依存できるよう `a2a_metadata` 文字列を定数化 (0821f2d)

#### v1.33.0 後の変更点（v1.34.0 へ取り込まれた hotfix を含む）

- **Gemini Live API 評価対応**: ADK evaluate に Live API サポート、 `Runner.run_live()` を evaluation_generator で利用、 local / base eval service の live mode 対応
- **GCPSkillRegistry 実装**: ADK に `GCPSkillRegistry` を新規実装
- **mTLS Telemetry exporter**: Google Cloud Telemetry exporter に mTLS サポート追加
- **A2aAgentExecutor factory in to_a2a()**: `to_a2a()` に factory を渡せるよう拡張
- **SkillToolset 安定化**: SkillToolset から experimental タグ削除
- **lazy-load サービスレジストリ**: `apps.app` を分割し service registry を lazy-load、 cold start を約 8% 削減 (perf)
- **AgentTool 結果保持**: `code_execution_result` / `executable_code` を AgentTool 内で保持
- **A2A 変換時 role 尊重**: events を A2A 形式に変換する際に user / agent role を区別
- **OAuth フロー整理**: 不要な OAuth フローを auth から削除 (c35a5796)
- **CLI deprecated フラグ＆ service URI 削除**: 廃止された CLI flag と version-based service URI handling を削除 (e04a4683)
- **SkillToolset dynamically loaded tools 修正**: 同一 invocation 内で SkillToolset に dynamically load された tool が見つからない問題を修正 (f9097cbf)
- **project_id fallback**: credentials に quota project が無い場合 project id にフォールバック (e377cb5e)
- **non-ADK input-required events 対応**: ADK 外部で生成された input-required event をサポート (6e534723)
- **Gemini auto review/invoke workflows**: CI に Gemini ベースの自動レビュー / invoke ワークフローを追加 (fd8b4929)
- **Anthropic session resume tool_use ID 保持**: session resume 時に Anthropic モデルの tool_use ID を保持 (327c45f9)
- **Skill Registry 実装**: ADK に Skill Registry を実装 (380d261e)
- **a2a persistent task stores サポート**: a2a に persistent task store サポート追加 (cd78d87b)
- **CacheMetadata active-state invariant 強制**: cache の active-state invariant を強制 (76b9f0ba)
- **sub live agent session resumption handle 分離**: sub live agent が parent から session resumption handle を継承して会話を中断する問題を修正 (b4dab9a)
- **refreshed OAuth2 credentials 永続化**: refresh された OAuth2 credentials を store に persist (af74b21)
- **gemini-3-flash-preview モデル更新**: hello world / session state agent サンプルのモデルを更新
- **AgentRegistry 即時エラー**: a2a-sdk 不在時に AgentRegistry import で eagerly に raise
- **`a2a_metadata` 定数化**: extension 開発者が依存できるよう `a2a_metadata` 文字列を定数化
- **CacheMetadata fingerprint-only 対応**: performance analyzer で fingerprint-only metadata を扱う
- **AnthropicLlm import OSError catch**: AnthropicLlm import 時の OSError を捕捉
- **McpToolset OAuth PKCE サポート**: McpToolset で OAuth PKCE をサポート

#### v1.33.0 の主要な変更点（2026-05-08）

**[Features]**

- **BufferableSessionService**: バッファリング可能なセッションサービスを新規追加 (0bc767e)
- **LlmResponse function call/response ヘルパー**: `get_function_calls()` と `get_function_responses()` を LlmResponse に追加 (22fae7e)
- **ApigeeLlm credential 注入**: ApigeeLlm に credentials を inject できるオプション追加 (ce578ff)
- **ADK environment tools truncation 設定化**: environment tools の truncation limit を設定可能化 (83ae405)

**[Bug Fixes]**

- **video inline data session 除外**: inline data の video event をセッションに保存しないようフィルタ (88421f8)
- **fork detection / offload limits / response logging (BigQuery)**: BigQuery plugin の fork 検出、 offload limit、 response logging 修正 (9d1bb4b)
- **hot reload agents for adk web**: adk web で agent の hot reload に対応 (740557c)
- **state_delta overwrite skip on function_response-only**: function_response-only event での state_delta 上書きをスキップ (fc27203, 211e2ce)
- **CustomAuthScheme 未登録エラー明確化**: AuthProvider 未登録時に actionable error を投げる (83f9817)
- **`req.app_name` → `app_name` 修正**: 正しい変数名へ修正 (8286066)
- **LlmBackedUserSimulator 空応答エラー**: 空応答時に明示的エラーメッセージを出す (fb92aad)
- **agent engine デプロイ認証**: API key ではなく project / location を使用 (398f28f)
- **catch genai.ClientError sandbox 不在時**: sandbox 不在時の genai.ClientError を catch (69fa777)
- **`asyncio.sleep` 化**: blocking sleep を asyncio.sleep に置換しイベントループブロックを回避 (3a1eadc)
- **ListSkillsTool 重複防止**: ListSkillsTool 利用可能時に skills を system instruction に追記しない (01f1fc9)
- **double append bug 修正**: double append バグを修正 (f8b4c59)
- **Express mode API call default api key**: Express mode API call で default api key param を含める (e833995)

**[Code Refactoring]**

- **adk metrics の input.type/output.type 属性削除**: metrics 定義の整理 (9559968)
- **workflow.steps メトリクス計算調整**: `workflow.steps` 計算ロジックを調整＋ unit test 追加 (03d6208)

#### v1.32.0 の主要な変更点（2026-04-30）

**[Security]**

- **`load_web_page` SSRF / local-file アクセス修正**: load_web_page における SSRF とローカルファイルアクセス脆弱性修正 (0447e93)
- **nested YAML configs RCE 修正**: ADK のネスト YAML 設定経由 RCE 脆弱性ブロック (74f235b)
- **PubSub / Eventarc user_id sanitization**: PubSub サブスクリプション / Eventarc source 由来の user_id をサニタイズ (#5324, 0c4f157)
- **credential isolation in auth context**: 解決済み認証情報の context 内分離（race condition / データ漏洩防止） (5578772)
- **litellm cap >= 1.83.7**: CVE パッチを取り込むため litellm の最低バージョンを引き上げ (6d2ada8)
- **Vertex RAG memory display name スコープ化**: scope 化 (784350d)

**[Core / Features]**

- **Anthropic thinking blocks サポート**: Anthropic の thinking blocks フォーマット対応 (16952bd)
- **adk deploy CLI express mode onboarding**: adk deploy CLI に express mode オンボーディング追加 (2b04996)
- **native OpenTelemetry agentic metrics**: ネイティブ OpenTelemetry agentic メトリクス追加 (6942aac)
- **event compaction OpenTelemetry tracing**: event compaction の OpenTelemetry tracing 追加 (c65dd55)
- **GcpAuthProvider 2LO/3LO/API Key sample**: GcpAuthProvider 経由の 2LO/3LO/API Key auth サンプル追加 (909a8c2)
- **ComputerUseToolset predefined function exclusion**: 事前定義関数の除外サポート (d760037)
- **BigQueryAgentAnalyticsPlugin credentials**: credentials パラメータ追加 (34713fb)
- **Apigee LLM refusal messages**: Apigee LLM での refusal メッセージ対応 (d6594a1)
- **`save_live_blob` パラメータ**: /run_live エンドポイントに save_live_blob クエリパラメータ追加 (36ab8f1)
- **MCP tool エラー/transport graceful handling**: ツール実行エラー・トランスポートクラッシュを安全に処理 (7744cfe)
- **McpToolset credential_key 指定**: ユーザー定義の credential_key 対応 (282db87, #5103)
- **SaveFilesAsArtifactsPlugin reference 抑止オプション**: メッセージにリファレンスファイルを attach させないオプション (987c809)
- **BigQuery LLM cache メタデータロギング**: LLM cache メタデータを BigQuery に記録 (02deeb9)
- **rubric-based eval `evaluate_full_response`**: full response 評価オプション (#5316, 7623ff1)

**[Bug Fixes]**

- **state_delta マージ時 list アキュムレート**: 並列ツール呼び出しの state_delta マージで list 値を accumulate (#5190)
- **GcpAuthProvider Bearer scheme 大文字化**: capitalized Bearer に修正 (ad937fe)
- **load_web_page 修正、google-genai 下限 bump**
- **LoopAgent サブエージェント state リセット防止**: pause 時に sub-agent state をリセットしない (8846be5)
- **VertexAiSessionService list filters quote 修正**: `user_id` リテラル quote 修正 (bdece00)
- **safe-JSON serializer ValueError 捕捉**: 循環参照時の ValueError ハンドリング (#5412, 70a7add)
- **bound token mcp_tool 無効化** / **web oauth flow と trace view 修正** / **schema RecursionError 修正**
- **ReflectRetryToolPlugin 例外順序修正** / **mcp 最低バージョン 1.24.0 → 1.25.0 系**

**[Performance]**

- **lazy-load optional providers**: 任意 provider と auth chain の lazy-load によりコールドスタート約 25% 改善 (66bfedc)

#### v1.31.1 / v1.31.0 の主要な変更点

**[Core]**

- **Parameter Manager / Secret Manager ユーザーエージェント**: Google ユーザーエージェント追加
- **VertexAiMemoryBankService `memories.ingest_events`**: サポート追加
- **Vertex AI Agent Engine Sandbox 統合**: コンピュータユースサポート
- **Firestore サポート追加**
- **Live session_id in LlmResponse**: LlmResponse に live session_id 追加
- **MCP 最低バージョン 1.24.0**: MCP 最低バージョンを 1.23.0 → 1.24.0 へ引き上げ

**[Bug Fixes]**

- **CLI コンソール URL パス修正**: CLI 展開後のコンソール URL パス修正 (#5336)
- **on_event_callback 順序修正**: イベント処理順序のバグ修正 (#3990)
- **FunctionDeclaration json_schema フォールバック**
- **BigQuery プラグイン問題解決**

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

**現行バージョン**: **v1.4.0 (2026-05-29)**

**チェックアウト状態**: `v1.4.0` (HEAD はタグ v1.4.0 に一致、 HEAD 2026-05-29)

**注目**: **v1.4.0 が 2026-05-29 にリリース**。 Context unification（tool context を callbackContext にマージする内部統合）、 adka2a structured error propagation、 a2a-go/v2 SDK への example / CLI 移行、 StreamingResponseAggregator の metadata-only SSE チャンク許容（ストリーム中断防止）が中心。 直前の v1.3.0（2026-05-20）で Live bidirectional streaming コア機能群・a2a-go/v2 対応・VertexAI MemoryBank が取り込まれた流れの直系。

#### v1.4.0 の主要な変更点（2026-05-29）

- **Context unification（tool context → callbackContext）**: tool context を callbackContext にマージする内部コンテキスト統合 (#871)、 agent/context + internal/context/callback_context の統合 (#868)
- **adka2a structured error propagation**: adka2a で構造化エラーを伝搬 (#874)
- **a2a-go/v2 SDK への移行**: examples と CLI launcher を a2a-go/v2 SDK 利用へ更新 (#780)
- **metadata-only SSE チャンク許容**: StreamingResponseAggregator で metadata-only な SSE チャンクを abort せず受理し、 ストリーム中断を防止 (#918)
- **conformance test recording plugin**: 適合テスト記録用プラグインを追加 (#890)
- **a2a execution cleanup callback 修正**: cleanup callback が発火しない問題を修正 (#903)
- **unrelated function events 保持**: 無関係な function events を保持するよう修正 (#767)
- **Vertex AI function call ID 保持**: Vertex AI の function call ID を保持 (#762)
- **tool responses を confirmations より先に yield**: (#765)
- **ThoughtSignature 複製**: `adk_request_confirmation` parts に ThoughtSignature をコピー (#763)
- **replay_plugin 修正**: 空の llmresponses と function formatting を比較前に normalize (#869)
- **transfer agent validation 追加**: transfer agent に validation を追加 (#824)

#### v1.3.0 の主要な変更点（2026-05-20）

- **user auth propagation 修正 (adka2a compat)**: adka2a 互換で user auth propagation が機能していなかった問題を修正 (#861)
- **Live audio cache for save artifact**: live で save artifact 向け audio cache を追加 (#838)
- **Live streaming tools**: live で streaming tools を追加 (#836)
- **Live session resumption**: bidirectional Live ストリーミングにセッション resumption を追加 (#837)
- **Live bidirectional streaming core**: 双方向ストリーミングのコア機能を新規追加 (#833)、 sequential agent live run (#835)、 live example (#834) を同梱
- **nil deref ガード (tool.Tool 未実装)**: ツールが `tool.Tool` interface を実装していない場合の nil dereference を防止 (#855)
- **non-streaming agent の StateDelta 伝搬修正**: non-streaming agent で StateDelta を伝搬するよう修正 (#854)
- **runtime request Decode error 修正**: runtime で request の Decode エラーを無視せずハンドリング (#851)
- **Gemini モデル更新**: examples のモデルを `gemini-3.1-flash-lite` に変更 (#839)
- **Dependabot 設定追加**: genai 系依存の自動アップデート用 Dependabot 設定 (#843)
- **a2a-go nil part fix bump**: a2a-go の nil part fix を取り込むためバージョンバンプ (#827)
- **parallel HITL function test**: parallel HITL function test を追加 (#817)
- **ADK Go LLM Request タグ付け対応**: LLM Request タグ付けのため ADK Go バージョン更新 (#816)
- **adka2a public API v2 移行**: 旧 adka2a public api が新 a2a-go/v2 に依存するよう修正 (#813)
- **VertexAI MemoryBank サポート**: VertexAI MemoryBank サポート追加 (#801)
- **thought signature 伝搬修正**: mixed responses の最初の function call へ thought signature を伝搬 (#788)
- **`gen_ai.usage` 属性リネーム**: experimental reasoning tokens 属性を `gen_ai.usage.*` に rename（OTel semantic conventions 整合） (#779)
- **a2a-go/v2 対応**: ADK を a2a-go v2 に対応 (#701)
- **stream_query simple text サポート**: full `genai.Content` ではなく simple text もサポート (#773)
- **Agent Engine 既存インスタンス更新**: 既存 Agent Engine インスタンスの更新サポート (#755)
- **runner manual session ID 削除＆自動生成**: runner で手動 session ID 入力を削除し自動生成を有効化 (#754)

#### v1.2.0 の主要な変更点

- **Agent Engine 統合**: Agent Engine デプロイのフルサポート (#749)
- **Merged skill source proxy**: 複数 skill source をマージするプロキシ実装 (#747)
- **Preload frontmatters skill source proxy**: frontmatter プリロードプロキシ (#748)
- **Skill Source proxy for preloading skills**: skill preloading プロキシ (#745)
- **SkillToolset 実装**: Skill をツールセットとして提供 (#733)
- **Toolsets RequestProcessor**: Toolsets が `toolinternal.RequestProcessor` インターフェースを実装可能に (#730)
- **traceCapacity API config 修正**: API config に traceCapacity 追加 (#731)
- **adk-web SSE エラーフォーマット修正**: (#734)
- **content processor 修正**: `toolconfirmation.FunctionCallName` を除外 (#717)

#### v1.1.0 の主要な変更点

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

**現行バージョン**: **v1.2.0 (adk-v1.2.0、 2026-06-03)**

**チェックアウト状態**: `a41c62c` (v1.2.0 リリース後の main、 HEAD 2026-06-08 付近)

**注目**: **v1.2.0 リリース（2026-06-03）**。 v1.1.0 後に積まれていたセキュリティ / 堅牢性修正（CORS 脆弱性、 OAuth2 SSRF 防止、 HTTP 切断時 abort、 AdkApiServer host 制限等）を取り込み。 v1.2.0 後の main では **Skills Registry 3部作**（Core interface + Zip 展開 + local Toolset キャッシュ → リモート GCP Skills Registry 統合 → LLM Agent 向け動的 SearchSkillsTool、 #422-424）、 **OpenAPI spec operation parser + auth handler (part 2、 #385)**、 **streaming の prototype pollution 修正（model 制御 JSON path 経由、 セキュリティ、 #410）** が進行中。 Python 側の Skills Registry / GCP 連携と歩調を揃える動き。

#### v1.1.0 後の変更点（v1.2.0 に取り込み済み）

- **Agent Registry 実装**: adk-js に Agent Registry を実装 (#358)
- **CORS 脆弱性修正**: express.urlencoded parser を無効化して CORS 脆弱性を解消 (セキュリティ) (#378)
- **OAuth2 SSRF 防止**: IPv4-mapped IPv6 経由の SSRF をブロックし、 死んでいた 172.16/12 チェックを修正 (セキュリティ) (#354)
- **run_sse の hardcoded `*` 削除**: run_sse から hardcoded Access-Control-Allow-Origin ワイルドカードを削除 (セキュリティ) (#360)
- **HTTP 切断時の agent 実行 abort**: HTTP 接続が切断された際に agent 実行を abort (#382)
- **AdkApiServer host 制限**: AdkApiServer を設定された host のみで listen するよう制限 (#383)
- **OpenAPI auth helpers / credential exchangers (part 1)**: OpenAPI 向け auth helper と credential exchanger を実装 (#384)
- **customMetadata サポート**: runAsync / runEphemeral で customMetadata をサポート (#363)
- **listSessions pagination / sorting**: listSessions に pagination と sorting を追加 (#331)
- **MCP client session クローズ (Windows)**: listTools/callTool 後に MCP client session を close し、 Windows libuv assertion / プロセスリークを修正 (#333)
- **AgentTool 修正**: skipSummarization を親 EventActions に伝搬しない (#301)、 sub-agent state delta から temp: キーをフィルタ (#271)
- **function tools array response ラップ**: Gemini API 準拠のため array レスポンスをラップ (#347)
- **agent_loader esbuild external 化**: lightningcss / jiti を external に指定し、 optional deps 不在時の adk web 不具合を修正 (#319)
- **Agent Engine Sandbox Code Executor**: Agent Engine Sandbox 経由のコード実行 Executor を新規追加 (#317)
- **TSDoc `@param` 追加**: `BeforeA2ARequestCallback` と `AfterA2ARequestCallback` に `@param` TSDoc 追加 (#339)
- **injectSessionState ユニットテスト**: instructions の `injectSessionState` に unit test 追加 (#338)
- **runWithRouting failover_utils テスト**: `runWithRouting` の unit test 追加 (#336)
- **file_extension_utils テスト**: file_extension_utils の unit test 追加 (#337)
- **Vertex AI Memory Bank service**: Vertex AI Memory Bank service を新規実装＋テスト (#291)
- **Agent Engine Sessions サポート**: Agent Engine Sessions サポート追加 (#249)
- **Google Maps tool**: 新規 Google Maps ツール追加 (#321)
- **VertexRagRetrievalTool**: Vertex AI RAG Engine を使ったグラウンディング向け retrieval ツール (#277)
- **stringifyContent / AgentTool thought parts フィルタ**: thought parts を出力からフィルタ (#323)
- **Windows 互換性**: dev/build.js で unix `cp` を Node.js fs.cp に置換 (#318)
- **MCPToolset.getTools() toolFilter 適用**: getTools() でも toolFilter を適用するよう修正 (#312, #313)
- **StreamingResponseAggregator.close() drop 修正**: 最後のチャンクに candidates が無い場合の drop を修正 (#289, #311)

#### v1.1.0 の主要な変更点

- **UrlContextTool**: Gemini 2+ の URL context グラウンディング向け UrlContextTool 追加 (#303)
- **Vertex AI Search Tool**: Vertex AI Search ツール追加 (#296)
- **MCP プレフィックス strip**: ツール実行時にプレフィックスを strip 修正 (#299)
- **AgentTool セッション再利用**: 同一セッション内での再利用のため `getOrCreateSession` 使用 (#302)
- **adk web UI ソース提供パス修正**: (#309)
- **js-yaml 利用**: yaml パッケージから js-yaml に変更 (#293)

#### v1.0.0 の主要な変更点

**[Core / Features]**

- **正式リリース**: v1.0.0 への昇格 (#229)
- **Progressive model streaming processing**: プログレッシブモデルストリーミング処理 (#258)
- **Skills システム**: script execution (#276)、loader part 3 (#256)、toolset part 2 (#252)、skills interface (#251)
- **Abort parameter サポート**: runner / agent / model / tool / processors で abort パラメータ対応 (#234)
- **RoutedAgent / RoutedLlm**: ルーティング可能なエージェント・LLM（experimental） (#215)
- **Unsafe local code executor**: unsafe ローカルコードエグゼキューター (#257)
- **Plugin callbacks for context compaction and tool selection**: プラグインコールバック (#250)
- **Auth preprocessor**: 認証プリプロセッサー (#227)
- **OAuth2 サポート**: OAuth2 関連クラス (#225)
- **AdkApiServer エクスポート**: `@google/adk-devtools` から export (#245)
- **Agent type alias for LlmAgent**: Python ADK とのパリティ (#242)

**[Bug Fixes]**

- **custom URL options for DB 接続**: client URL 対応 (#284)
- **thoughtSignature 伝播修正**: 並行 function calls streaming 時の伝播 (#268)
- **ESM dynamic require 対応**: esm ビルドでの `__dirname`/`__filename`/`import.meta.url` 保持 (#254)
- **ESM dynamic require 修正**: (#244)
- **invocation id 追加**: parallel tool responses マージ時の invocation id 追加 (#253)
- **otel 依存関係移動**: dev deps → deps に移動 (#243)

**[Security / Deps]**

- **パストラバーサル防止**: FileArtifactService (CWE-22)
- **lodash / lodash-es セキュリティ更新**: (#232, #230)
- **follow-redirects bump**: (#275)
- **vite bump**: npm_and_yarn group (#236)

#### v0.2.4 の主要な変更点

- **A2A 統合**: CLI オプションによる A2A 経由のエージェント提供 (#188)
- **トークンベースコンテキストコンパクション**: (#191)
- **セッション DB 初期化修正**: (#195)
- **MikroORM リファクタリング**: セッションサービスのリファクタ

#### 参考リンク

- [ADK JS](https://github.com/google/adk-js)

---

### Agent Starter Pack

**現行バージョン**: v0.41.3

**チェックアウト状態**: `v0.41.3-1-g659f047` (v0.41.3 + 1 commit、 HEAD 2026-05-21)

**注目**: README で後継プロジェクト「agents-cli」への進化告知 (#952)、 直近では **maintenance mode に入ったことを公式に surface し、 ユーザーを agents-cli に push** (#967)。 Google の agent dev tooling 戦略は事実上 agents-cli へ移行。

#### v0.41.3 後の変更点

- **maintenance mode 公式アナウンス**: README / ドキュメントで maintenance mode 入りを surface し、 agents-cli への移行を push (#967)

#### v0.41.3 の主要な変更点

- **バージョンバンプ**: v0.41.3 へのバージョンバンプ (#953)

#### v0.41.2 の主要な変更点

- **uv lock 再生成 + langgraph-prebuilt pin**: `langgraph-prebuilt<1.0.9` への pin (#948)
- **agents-cli 発表**: Agent Starter Pack の次世代進化として agents-cli 告知 (#952)

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

#### v1.10.0 後の変更点

- **@protobufjs/utf8 1.1.0 → 1.1.1 バンプ**: 依存パッチバンプ (#282)
- **fast-uri 3.1.2 / fast-xml-builder 1.2.0 / hono 4.12.18 バンプ**: 依存パッチバンプ群 (#281, #280, #279)
- **ip-address / express-rate-limit バンプ**: セキュリティパッチ群 (#277)
- **Docker Compose デプロイメントサポート**: docker compose deployments を Cloud Run へ展開可能に (#272)
- **BUILD_ID ベース cloudbuild**: scheduled builds 向け BUILD_ID base の cloudbuild 追加 (#275)
- **cloudbuild image location 修正**: イメージ配置のロケーション修正 (#273)
- **README SKILL.md リンク修正**: (#276)
- **Cloudbuild 設定**: `cloudbuild.yaml` 追加 (#269)
- **Cloud Run skills**: cloud run skills 追加 (#267)
- **named/bind ボリューム権限修正**: (#262)
- **AI モデルサポート**: run compose で AI モデルサポート (#258)
- **Secrets Manager サポート**: compose デプロイメントで Secrets Manager サポート (#256)
- **ボリュームマウントサポート**: (#254)
- **並列ビルド**: run compose での並列ビルドサポート (#253)
- **deployCompose capability**: (#252)
- **translate functionality for run compose**: (#249)
- **サービス情報詳細化**: getInfo でより詳しい情報提供 (#248)
- **SECURITY.md 追加**: (#247)
- **run-compose binary 統合**: binary ダウンロードとリソースコマンド実行 (#244, #245)
- **artifact download ロジックリファクタ**: 再利用可能化 (#240)
- **依存関係更新**: Hono 4.12.14、fast-xml-parser 5.7.1、lodash 4.18.1、path-to-regexp 8.4.0、picomatch 4.0.4 等

#### v1.10.0 の主要な変更点

- **cloud-run-mcp クライアント**: OSS Run MCP からのデプロイ用クライアント追加 (#242)
- **Ingress ポリシー環境変数**: 環境変数によるイングレスポリシー設定 (#243)
- **Run v1 クライアント**: googleapis ベースの Run v1 クライアント追加 (#236)
- **統合テスト拡充**: Java, Node.js, Python プロジェクトの統合テスト追加

#### 参考リンク

- [Cloud Run MCP](https://github.com/GoogleCloudPlatform/cloud-run-mcp)

---

### gcloud-mcp

**現行バージョン**: gcloud-mcp-v0.5.3 / storage-mcp-v0.6.0 / observability-mcp-v0.2.3 / backupdr-mcp-v0.1.0

**チェックアウト状態**: `release-please-422-16-g7a07667` (storage-mcp-v0.6.0 release-please ブランチから 16 commits 先、 HEAD 2026-05-27)

#### storage-mcp-v0.6.0 後の変更点

- **依存標準更新**: standard dependency updates (#428)
- **turbo v2.9.14 バンプ (security)**: turbo を v2.9.14 にセキュリティ更新 (#430)
- **@tootallnate/once 2.0.0 → 2.0.1 バンプ**: 依存パッチバンプ (#431)
- **qs 6.15.0 → 6.15.2 バンプ**: 依存パッチバンプ (#432)
- **protobufjs 7.5.6 → 7.6.1 バンプ**: 依存マイナーバンプ (#436)
- **googleapis v172 更新**: googleapis 依存を v172 に更新 (#433)
- **brace-expansion 5.0.5 → 5.0.6 バンプ**: 依存パッチバンプ (#429)
- **fast-uri 3.1.0 → 3.1.2 バンプ**: dev deps バンプ (#427)
- **依存標準更新**: standard dependency updates (#399)

#### storage-mcp-v0.6.0 の主要な変更点（2026-05-06）

- **`download_object_safe` ツール削除（破壊的変更）**: 「safe」を名乗っていたが実際は destination パスへの ~/.bashrc 等への書き込みを許す設計だったため削除。 destructive 経路の `download_object` または `read_object_content` / `read_object_metadata` への移行が必要 (#420, #422)
- **integration tests 修復**: MCP 接続不能による失敗を修正 (#421, #426)
- **依存バンプ群**: hono 4.12.12 → 4.12.18 (#425)、 ip-address / express-rate-limit (#423)、 protobufjs 7.5.4 → 7.5.6 (#417)、 postcss 8.5.6 → 8.5.12 (#416)、 fast-xml-parser 5.5.7 → 5.7.1 (#415)、 codecov-action v6 (#410)

#### storage-mcp-v0.5.1 の主要な変更点

- **`delete_object` を destructive に移動**: safe tools から destructive tools へ移動（セキュリティ強化） (#412)
- **gemini mcp list `--debug` フラグ**: 出力切り詰め解消のための debug フラグ追加 (#405)

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

### Gemini Cloud Assist MCP

**現行バージョン**: v0.8.0 (2026-04-21)

**チェックアウト状態**: `v0.8.0-6-ga0439a7` (v0.8.0 + 6 commits、 HEAD 2026-05-19)

**注目**: ローカル Node.js 実装 (v0.2.0) を **完全 deprecate**、 Remote MCP Server 構成へアーキテクチャ全面刷新。 現在 **Private Preview** で allowlist 制（Google Cloud account team 経由でアクセス申請が必要）。

#### v0.8.0 後の変更点（次回リリース向け）

- **skills 更新**: bundled skills の更新 (a0439a7)
- **Claude Code Instructions 追加**: Claude Code 向け instructions を README/プロジェクトドキュメントに追加 (540474b, 22a2a18)
- **README MCP Tool description 更新**: MCP Tool 説明と Claude Code 向け instructions を README に取り込み (997bb4d, 8580afd)
- **GitHub workflows cleanup / 修正**: CI ワークフローの整理 (a8c60dc)

#### v0.8.0 の主要な変更点

- **Remote MCP Server 化**: ローカル Node.js MCP server から **Remote MCP Server architecture** へ全面移行（**破壊的変更**） (d225f7b)
- **ローカル Node.js server の完全 deprecate**: v0.2.0 の local server 完全廃止 (d5d860b)
- **Private Preview ローンチ**: Gemini Cloud Assist remote MCP Server を Private Preview として正式公開
- **Skills 群追加**: `designing-and-deploying-infrastructure`、 `operating-google-cloud` の 2 種類の Skill 定義追加
- **README に deprecation notice / Private Preview notice 追加**: ローカル版 deprecation とリモート版アクセス申請手順を明示

#### v0.2.0 / v0.1.x（legacy local Node.js）の主要な変更点

- **npm パッケージ公開**: `@google-cloud/gemini-cloud-assist-mcp` を npm 公開 (e24e526)
- **mcpName / インストール手順整備**: `mcpName` フィールド追加と Claude Desktop / npm パッケージ経由のインストール手順整備 (831c72e, 4a7afda)
- **version sync スクリプト**: ツーリングへ追加 (94cc346)
- **npm publish workflow**: GitHub Actions で npm publish 自動化 (6b00fa5)

#### 破壊的変更

| 変更 | 影響 |
|------|------|
| Local Node.js server → Remote MCP Server (v0.8.0) | クライアント設定をリモートエンドポイント参照に変更必須、ローカル install 系手順は無効化 |

#### 参考リンク

- [Gemini Cloud Assist MCP](https://github.com/GoogleCloudPlatform/gemini-cloud-assist-mcp)
- [Use the Gemini Cloud Assist remote MCP server (Cloud Docs)](https://docs.cloud.google.com/cloud-assist/use-gemini-cloud-assist-mcp)

---

### GKE MCP

**現行バージョン**: **v0.13.0 (2026-05-28)**

**チェックアウト状態**: `v0.13.0` (HEAD はタグ v0.13.0 に一致、 HEAD 2026-05-28)

**注目**: **v0.13.0 が 2026-05-28 にリリース**。 v0.12.0 の Anthropic Claude ADK adapter / node pool 管理ツールに続き、 k8s リソース操作ツール群（apply / get / describe / patch / delete / logs / rollout status / auth check / api resources / cluster info / events）を一括拡充。 install 時の checksum verification とセキュアな CI（insecure `pull_request_target` 防止チェック）も追加。

#### v0.13.0 の主要な変更点（2026-05-28）

- **k8s リソース操作ツール群拡充**: `list_k8s_api_resources` (#378)、 `patch_k8s_resource` (#387)、 `get_k8s_rollout_status` (#386)、 `check_k8s_auth` (#385)、 `describe_k8s_resource` (#388)、 `get_k8s_cluster_info` (#379)、 `get_k8s_logs` (#370)、 `delete_k8s_resource` (#368) を新規実装
- **delete デフォルト cascade policy を background 化**: k8s delete のデフォルト cascade policy を background に設定 (#376)
- **install checksum verification**: インストール時の checksum 検証を追加 (#398)
- **insecure `pull_request_target` 防止チェック (CI)**: 安全でない `pull_request_target` 利用を防ぐ CI チェックを追加 (#400)
- **eval-on-pr workflow 削除**: eval-on-pr ワークフローを無効化のうえ完全削除 (#397, #399)
- **依存バンプ群**: google.golang.org/adk 1.2.0 → 1.3.0 (#393)、 genai 1.57.0 → 1.58.0 (#392)、 anthropic-sdk-go 1.43.0 → 1.45.0 (#394)、 adk-anthropic-go 0.1.15 → 0.1.16 (#395)、 go-sdk 1.6.0 → 1.6.1 (#391)、 api 0.279.0 → 0.280.0 (#390)、 all-npm group 7 件 (#396)、 qs 6.15.0 → 6.15.2 (#382)
- **manifestgen developer knowledge instructions**: manifestgen に developer knowledge の利用指示を追加 (#371)
- **`apply_k8s_manifest` ツール実装**: k8s manifest を適用する MCP ツールを新規実装 (#358)
- **ADK Anthropic Claude Go ライブラリ統合**: `Alcova-AI/adk-anthropic-go` を統合 (#356)
- **dk: SearchDocuments / GetDocuments / AnswerQuery 実 HTTP 接続化**: Developer Knowledge 3 ツールを mock から実 HTTP 接続へ昇格 (#344, #345, #346)
- **Baseline Evaluation Label Requirement 削除**: Baseline Evaluation の必須ラベル要件を撤廃 (#369)
- **anthropic-sdk-go 1.42.0 → 1.43.0 バンプ** (#364)
- **google.golang.org/genai 1.56.0 → 1.57.0 バンプ** (#363)
- **all-npm group 7 件アップデート (UI)** (#365)
- **`get_k8s_version` ツール**: K8s バージョン取得ツール追加 (#353)
- **Cluster operations support**: cluster operations サポートと unit test 改善 (#328)
- **DK 実 HTTP 接続実装**: `SearchDocuments` を実 HTTP 接続化、 mock 実装から本物のAPI接続へ昇格 (#344)
- **OWNERS / automatic reviewers 更新**: owners と自動レビュアー設定を更新 (#355)
- **eval skips 削除**: evaluation skip ロジックを削除 (#354)
- **`list_k8s_events` ツール実装**: k8s イベント一覧ツールを新規実装 (#329)
- **baseline evals feature branches トリガー化**: baseline evaluation を feature branch でも実行 (#352)
- **eval-on-pr `pull_request_target` 化**: eval CI を pull_request_target で実行 (#347)
- **`dk_get_documents` ツール定義**: Developer Knowledge get-documents ツール定義 (#324)
- **`get_k8s_resource` MCP ツール**: client-go を使った k8s リソース取得 MCP ツール (#327)
- **`dk_search_documents` ツール定義**: Developer Knowledge search-documents ツール定義 (#326)
- **`dk_answer_query` ツール定義**: Developer Knowledge answer-query ツール定義 (#325)
- **DeepEval CI/CD 統合**: PR 向け DeepEval テストと CI/CD ワークフロー実装 (#323)
- **Developer Knowledge API クライアント統合**: developer knowledge api client を統合 (#319)
- **`giq_fetch_model_servers` instructions**: manifestgen に giq_fetch_model_servers の利用指示追加 (#307, #308)
- **UI 依存バンプ**: hono 4.12.14 → 4.12.18 (#322)、 ip-address / express-rate-limit (#320), fast-uri 3.1.0 → 3.1.2 (#331)
- **Go / NPM 依存バンプ群**: anthropic-sdk-go 1.39.0 → 1.42.0 (#342), genai 1.55.0 → 1.56.0 (#339), gkerecommender 0.5.0 → 1.0.0 (#340), google-cloud group (#337)
- **CI アクションバンプ**: google-github-actions/auth v2 → v3 (#336), actions/checkout v4 → v6 (#335), setup-go v5 → v6 (#334), setup-python v5 → v6 (#333)

#### v0.12.0 の主要な変更点

- **ADK Anthropic Claude アダプター実装**: LLM 抽象 factory + Anthropic Claude 用 ADK adapter (#280, #303)
- **Node Pool 管理ツール追加**: GKE node pool の create/list/update 等の管理ツール (#282)
- **新規 cluster ツール群＋GKE remote MCP 機能**: 新規クラスタ操作ツールと GKE remote MCP 連携 (#281)
- **giq fetch_model_servers / fetch_profiles**: model servers と profiles の fetch ツールを実装し manifest agent と接続 (#284, #285, #290, #293, #279)
- **manifestgen rename**: `giqTool` → `generateManifestTool` (#306)
- **GKE AI TPU 接続障害トラブルシュート skill**: (#267)
- **GKE AI トラブルシュート skill 作成ガイド**: (#268)
- **dependency バンプ群**: google-cloud groups (#296), modelcontextprotocol/go-sdk 1.5→1.6 (#298), google.golang.org/api (#297), genai 1.54→1.55 (#299)
- **auto-request-review 追加**: (#305)

#### v0.11.1 後の変更点

- **GIQ ツール manifest agent 統合**: `giq_generate_manifest` をマニフェストエージェントに統合 (#253)
- **GIQ コアロジックを MCP transport から分離**: (#251)
- **ADK フレームワーク統合 (manifest agent)**: manifest agent に ADK 統合 (#247)
- **Skills インストール手順**: README に Skills インストール手順追加 (#252)
- **backend vertex pool 抽象化**: エージェントモック分離 (#240)
- **gke-productionize skill ガイドライン強化**: (#242)
- **gke-workload-security skill pathing 修正**: (#248)

#### v0.11.1 の主要な変更点

- **go-version-file 使用**: release プロセスで go-version-file を使用、v0.11.1 へバージョンバンプ (#238)
- **manifestgen リッチインストラクション埋め込み**: (#218)
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

**現行バージョン**: **0.6.0 (2026-05-21)**

**チェックアウト状態**: `0.6.0` (HEAD はタグ 0.6.0 に一致、 HEAD 2026-05-21)

#### 0.6.0 の主要な変更点（2026-05-21）

- **subprocess stdio handle inheritance 防止**: サブプロセスでの stdio handle 継承を抑止し、 v0.4.0 #151 修正のフォローアップ deadlock を解決 (#154)

#### 0.5.0 の主要な変更点

- **conversions schema/spec ツール追加**: 新しい conversions schema / spec 用ツール追加 (#161)
- **google-analytics-data v0.22.0**: 依存バンプ (#159)
- **google-analytics-admin v0.29.0**: 依存バンプ (#158)

#### v0.4.0 の主要な変更点

- **tool call deadlock / stdout corruption 修正**: tool call の deadlock と stdout プロトコル汚染を解決 (#151)

#### v0.3.0 の主要な変更点

- **`run_funnel_report` ツール追加**: GA Data API v1alpha を使った funnel レポートツール (#127)
- **ADK 開発向け Skills 追加**: ADK 開発の Skills 群を Google Analytics MCP に同梱 (#148)

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

**現行バージョン**: 継続的デプロイ（バージョンタグなし）

**性質**: Google 公式の MCP サーバーディレクトリ・デプロイガイダンス・入門例を集約するリポジトリ（継続デプロイ）。

#### 最近の変更点

- **bakery demographics.csv 修正**: launchmybakery デモの demographics.csv から `median_household_income` 列を除去し、 dataset description を修正 (#53)
- **リモート MCP サーバー・例セクション更新**: (#44)
- **bakery デモ自動化**: `--quiet` フラグで gcloud mcp 有効化をオートメーション化
- **launchmybakery cold start 修正**: MCP エンドポイントに明示的タイムアウト設定（cold start 対応）
- **bakery ADK version pin**: ADK tool を v1.28.0 に pin、Ctrl+C 停止手順追加
- **bakery bigquery.googleapis.com 有効化**: `setup_env.sh` で API 有効化
- **Cloud Data MCP サンプル**: DK と Cloud SQL remote MCP のラボ追加 (#22)
- **デモ動画・バッジ**: README にデモ動画・バッジ追加
- **Chrome DevTools サーバー**: 新規 MCP サーバー追加

#### 主要な変更点

- **Gemini 3.1 Pro Preview**: ルートエージェントモデルを gemini-3.1-pro-preview に更新
- **リモートサーバー集約**: AlloyDB, BigQuery, Bigtable, Cloud Resource Manager, Cloud SQL (MySQL/PostgreSQL/SQL Server), Compute Engine, Firestore, Google Maps, Chronicle, GKE, Spanner, Cloud Run, Cloud Storage
- **オープンソース MCP サーバー統合**: Workspace, Firebase, Cloud Run, Google Analytics, MCP Toolbox, GCS 等

#### 参考リンク

- [Google Cloud MCP](https://github.com/google/mcp)

---

### MCP Security

**現行バージョン**: secops-v0.7.0 (2026-03-14)

#### v0.7.0 以降の変更点

- **`list_parsers` ツール追加**: secops-mcp に `list_parsers` ツールを追加し、parser management の return type を標準化、pagination token 対応 (#252)
- **pyink フォーマット適用**: parser_management.py に pyink フォーマット適用
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

**現行バージョン**: **v1.4.0 (2026-06-04)**

**チェックアウト状態**: `eede644599f` (v1.4.0 + 8 commits)

**注目**: **v1.4.0 リリース（2026-06-04）**。 **Data Lineage 統合**、 起動時に未知ツールを無視する **`--ignore-unknown-tools` フラグ**、 Cloud SQL Postgres の **vector assist tools 完備**、 Spanner **`search_catalog` tool**、 windows/arm64 バイナリ配布が新規。 セキュリティ面では v1.3.0 後に積まれていた **ClickHouse / BigQuery の identifier injection 防止 (#3219)**、 **Looker filter value escape (#3289)** に加え、 **opaque token 検証での issuer 必須化 (#3360)**、 **Google / Generic MCP OAuth 検証の分離 (#3341)** を取り込み。 [UPGRADING.md](https://github.com/googleapis/genai-toolbox/blob/main/UPGRADING.md) でのマイグレーションガイド参照。

#### v1.4.0 の主要な変更点（2026-06-04）

- **Data Lineage 統合**: Data Lineage integration を追加 (#3285)
- **`--ignore-unknown-tools`**: 起動時に未知ツールを無視するフラグ (#3353)
- **Cloud SQL PG vector assist tools**: 残りの vector assist tools を追加 (#3203)
- **Spanner `search_catalog`**: search_catalog tool を実装 (#3140)
- **opaque token の issuer 必須化**: generic auth の opaque token validation で issuer presence を強制 (セキュリティ) (#3360)
- **Google / Generic MCP OAuth 検証の分離**: OAuth verification を分離 (セキュリティ) (#3341)
- **windows/arm64 バイナリ配布**: CI で windows/arm64 をサポート (#3231)

#### v1.3.0 以降の変更点（v1.4.0 に取り込み済み）

- **ClickHouse / BigQuery identifier injection 防止**: identifier パラメータをバリデーションし injection を防止 (セキュリティ) (#3219)
- **apache/thrift CVE-2026-41602 対応**: apache/thrift を v0.22.0 → v0.23.0 に置換し CVE を解消 (#3312)
- **Looker unquoted parameters filter value escape**: unquoted パラメータの filter 値をエスケープ (#3289)
- **GitHub Actions メジャーアップデート**: GitHub Actions 群を major バージョン更新 (#3316)
- **Go ランタイム更新**: go の更新 (#3187)
- **conformance presubmit go version mismatch 修正**: presubmit の go version mismatch を修正 (#3315)
- **依存バンプ群**: otel 1.39.0 → 1.41.0 (#3198)、 fast-xml-builder 1.1.4 → 1.2.0 (#3200)、 brace-expansion (#3246)、 ws 8.19.0 → 8.21.0 (#3248) / 8.18.3 → 8.20.1 (#3262)

#### v1.3.0 の主要な変更点（2026-05-21）

**[Features]**

- **`cloud-sql-admin-execute-sql-many` / `cloud-sql-admin-sql-many` ツール追加**: Cloud SQL admin 系で bulk execute-sql / sql ツールを新規追加 (#3083)
- **SQLCommenter + クライアントメタデータ送出**: SQL に client metadata コメントを付与する SQLCommenter 機構を追加 (#3064)
- **MCP auth tool-level scopes バリデーション**: tool レベルの scope を MCP auth でバリデーション (#3049)
- **Looker client IP 伝搬**: incoming MCP リクエストの client IP を downstream SDK 呼び出しに伝搬 (#3253)

**[Bug Fixes]**

- **HTTP tool path traversal / base path scope escape 防止**: HTTP tool での path traversal と base path scope escape を防止 (セキュリティ) (#3218)
- **toolset/promptset boundary 強制**: `tools/call` と `prompts/get` で toolset/promptset の境界を強制 (#3036)
- **generic auth expiration 修正**: generic auth の expiration フィールドと `authRequired` の統合を修正 (#3251)
- **Looker 401 透過**: Looker が 401 を返した場合 MCP クライアントに 401 をそのまま返却 (#3233)
- **Looker filter value wrapping quotes strip**: unquoted パラメータの filter 値から囲み quote を除去 (#3273)
- **query result slices 初期化**: query 結果スライスを空配列で初期化 (#3250)

#### v1.2.0 の主要な変更点（2026-05-07）

**[Features]**

- **HTTPS/TLS listener 対応**: HTTPS/TLS listener サポート追加 (#3126)
- **BigQuery `maximumBytesBilled` ソース設定**: BigQuery source にコスト制限用の `maximumBytesBilled` 設定追加 (#2724)
- **Cloud Storage source (read 系)**: `list_objects`, `read_object` ツールを提供する Cloud Storage source を新規追加 (#3081)
- **Cloud Storage bucket / object 管理ツール**: bucket and object 管理ツールを Cloud Storage source に追加 (#3129)
- **Cloud Storage write/copy/move/delete object ツール**: Cloud Storage source に write/copy/move/delete 操作を追加 (#3139)
- **Knowledge-catalog Data Quality Scans 検索**: スキャン ID・テーブル名フィルタ、 pagination、 sort 対応の Dataplex DQ Scans 検索ツール (#2444)

**[Bug Fixes]**

- **string literal block with list 変換許可**: 該当変換を許可 (#3050, closes #3023)
- **MCP router-level logger injection 実装**: MCP auth で router-level logger injection (#3067)
- **test.db 生成防止**: unit test 中の test.db 生成を防止 (#3042)
- **SSE hardcoded `*` allowed origin 削除**: SSE の hardcoded allow-origin を削除 (セキュリティ) (#3054)
- **Postgres ソース URL エンコーディング修正**: query string params の URL encoding 適用 (#3020)
- **Looker conversational-analytics OAuth トークン**: GDA payload で OAuth token を修正 (#3058)
- **BigQuery execute-sql エラー出力**: 不正クエリを MCP 500 として表面化しないよう修正 (#3056)
- **Looker Conversational Analytics OAuth**: Looker Conversational Analytics 向け OAuth 修正 (#3044)

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
| **ADK Python v2.2.0** (2026-06-04) | Google GenAI SDK v2.0.0 対応、 AutoTracingPlugin、 RubricBasedMultiTurnTrajectoryEvaluator、 path traversal / Zip Slip / unpickle 制限 / CVE-2026-48710 等のセキュリティ修正一括 | 高 |
| **ADK JS v1.2.0** (2026-06-03) | v1.1.0 後のセキュリティ修正（CORS、 OAuth2 SSRF、 host 制限）を取り込み。 後続 main で Skills Registry 3部作 + streaming prototype pollution 修正 | 高 |
| **GenAI Toolbox v1.4.0** (2026-06-04) | Data Lineage 統合、 `--ignore-unknown-tools`、 identifier injection 防止 / opaque token issuer 必須化 / OAuth 検証分離（セキュリティ） | 中 |
| **A2UI v0.10 `theme` → `surfaceProperties`** (#1525, 2026-06) | BREAKING rename + `primaryColor` 削除。 v0.10 では surfaceId の client session 毎グローバル一意化 (#1543) も | 中 |
| **A2UI v0.10 MIME 変更** (#1493, 2026-06) | IANA 規約準拠で mime type を `application/a2ui+json` へ変更（POTENTIALLY BREAKING）。 既存 A2UI-over-HTTP / MCP クライアントの content-type 判定に影響 | 中 |
| **MCP-Apps v1.7.4 PKCE 必須化** (#681, 2026-06-04) | lazy-auth-server の token exchange で PKCE を必須化し redirect_uri をバインド（セキュリティ強化）。 PKCE 非対応の旧フローは拒否される。 base path 配下マウントも対応 (#683) | 中 |
| **ADK Go v1.4.0** (2026-05-29) | Context unification（tool context を callbackContext にマージする内部統合）、 adka2a structured error propagation、 examples / CLI を a2a-go/v2 SDK へ移行、 metadata-only SSE チャンク許容でストリーム中断防止 | 高 |
| **GenAI Toolbox v1.3.0** (2026-05-21) | `cloud-sql-admin-execute-sql-many` / `sql-many` bulk ツール、 SQLCommenter（client metadata 送出）、 MCP auth tool-level scopes バリデーション、 HTTP tool path traversal 防止（セキュリティ） | 中 |
| **GKE MCP v0.13.0** (2026-05-28) | k8s リソース操作ツール群（apply / get / describe / patch / delete / logs / rollout / auth / api-resources / cluster-info / events）一括拡充、 install checksum verification、 insecure `pull_request_target` 防止 CI | 中 |
| **Google Analytics MCP 0.6.0** (2026-05-21) | subprocess stdio handle inheritance 防止（v0.4.0 #151 のフォローアップ deadlock 解消, #154）を正式リリース | 低 |
| **ADK Python v2.0.0 GA** (2026-05-19) | v1.x → v2.0 メジャー昇格。 Multi-Agent Workflow Engine / Flexible Execution Graphs / Intelligent Task Delegation / Native Inter-Agent Routing が production-grade GA に。 main ブランチも v2.0.0 へ transition。 v1.34.0 は LTS として継続。 直近 HEAD で v2 リリースワークフローを v1 ブランチへ repoint | 高 |
| **ADK Go v1.3.0** (2026-05-20) | Live bidirectional streaming のコア機能（session resumption / streaming tools / audio cache）一括取り込み、 a2a-go/v2 互換化、 VertexAI MemoryBank サポート、 `gen_ai.usage` 属性 rename (OTel 整合) | 高 |
| **Agent Starter Pack maintenance mode** (2026-05-21) | README で **公式に maintenance mode を surface**、 後継 **agents-cli** への移行を push (#967)。 新規プロジェクトは agents-cli を使うべき | 高 |
| **UCP loyalty extension** (#340, v2026-04-08 後) | catalog / cart / checkout capability に loyalty 拡張を追加。 既存 discount 拡張に続く 2 つ目の正式拡張 | 中 |
| **UTCP v1.0** (新規追跡, 直近 commit 2026-05-05) | MCP の構造的代替案（agent → native endpoint 直叩き）、 plugin architecture へ全面再設計 | 中 |
| **Visa Trusted Agent Protocol** (新規追跡, `payments/`) | Agentic commerce での agent identity / authorization 標準。 cryptographic signature ベース | 中 |
| **Mastercard Verifiable Intent v0.1.0** (新規追跡, 2026-03-05 OSS化, `payments/`) | SD-JWT chain で user → agent delegation scope を verify、 Selective Disclosure でプライバシー保護 | 中 |
| **Gemini Cloud Assist MCP v0.8.0** (新規追跡, 2026-04-21) | Local Node.js → Remote MCP Server へ全面刷新、 v0.2.0 (local) は完全 deprecate | 高 |
| **ADK Python v1.34.0** (2026-05-18) | a2a persistent task stores、 Gemini Live API in ADK evaluate、 mTLS Cloud Telemetry exporter、 GCPSkillRegistry / Skill Registry 実装、 McpToolset OAuth PKCE | 高 |
| **ADK Python v1.33.0** (2026-05-08) | BufferableSessionService、 LlmResponse function call/response ヘルパー、 ApigeeLlm credential 注入、 adk web hot reload | 中 |
| **GenAI Toolbox v1.2.0** (2026-05-07) | Cloud Storage source write/copy/move/delete、 HTTPS/TLS listener、 BigQuery `maximumBytesBilled`、 Knowledge-catalog DQ Scans 検索 | 中 |
| **MCP SEP-2567/SEP-2575** (2025-11-25 後) | Sessionless MCP via Explicit State Handles + Make MCP Stateless、 ステートレス志向への大型仕様シフト | 高 |
| **ACP v2026-04-17 後 #429 (UCP)** | UCP の profile schemas 検証修復は破壊的、 既存実装の再検証必要 | 中 |
| **UCP v2026-04-08 後** | Identity Linking OAuth 2.0 foundation、capability-driven scopes（破壊的）、 profile schemas 検証修復（#429、 破壊的） | 高 |
| **MCP-UI v7.1.1** (2026-05-09) | sandbox proxy iframe timeout cancel で StrictMode 安定化、 v7.1.0 の hostInfo/hostCapabilities props と組合せ | 中 |
| **ADK Python v1.32.0** (2026-04-30) | SSRF / RCE / credential isolation 等のセキュリティ修正、Anthropic thinking blocks、native OTel agentic metrics | 高 |
| **GKE MCP v0.12.0** | Anthropic Claude ADK adapter、node pool 管理ツール、新規 cluster ツール群 | 中 |
| **Google Analytics MCP 0.5.0** | conversions schema/spec ツール、 v0.4.0 では tool call deadlock 修正・`run_funnel_report` ツール・ADK Skills 追加 | 中 |
| **AP2 v0.2.0** (2026-04-28) | V2 仕様正式リリース。v0.1.0 から 7 ヶ月ぶりの大型更新 | 高 |
| **gcloud-mcp storage-mcp v0.6.0** (2026-05-06) | `download_object_safe` ツール削除（破壊的変更）。 destructive 経路 `download_object` または `read_object_content` / `read_object_metadata` への移行必須 | 中 |
| **ADK JS v1.0.0 → v1.1.0** | UrlContextTool/Vertex AI Search Tool 追加、MCP プレフィックス strip 修正、AgentTool セッション再利用 | 中 |
| **ADK Go v1.2.0** | Agent Engine 統合、Skill Source proxy 群、SkillToolset 実装、stream_query simple text サポート | 中 |
| **UCP v2026-04-08** | 6件の破壊的変更: variant options リネーム、webhook 分離、エラー統一、currency 必須化等 | 高 |
| **GenAI Toolbox v1.0.0** | Elasticsearch vector search リファクタ、Looker ツール分割 | 高 |
| **GenAI Toolbox v0.32.0** | リポジトリ名更新 | 高 |
| **GenAI Toolbox v0.31.0** | `enable-api` フラグ必須化、非推奨項目削除 | 高 |
| **A2A v1.0.0** | Push Notification Config 統合、`blocking`→`return_immediately`、仕様リファクタ | 高 |
| **MCP-UI v7.0.0** | レガシー仕様の完全削除 | 高 |
| **ACP v2026-01-30** | Payment Handlers Framework 導入 | 高 |
| **MCP-Apps v1.7.0** | ツール登録 WebMCP-style 仕様化、Zod jitless デフォルト化 | 中 |
| **x402** | メインリポジトリが foundation repo へ移動 | 中 |
| **ADK Python v1.29.0** | SecretManagerClient パッケージ移動 | 中 |
| **Google Analytics MCP** (未リリース) | パッケージ名 `analytics-mcp` にリネーム | 低 |

### メジャーアップデート

0. **NEW: ADK Python v2.2.0** (2026-06-04) - Google GenAI SDK v2.0.0 対応、 AutoTracingPlugin（OTel 自動計装）、 RubricBasedMultiTurnTrajectoryEvaluator、 native `gen_ai.client.*` metrics、 A2A 連携強化（`to_a2a(Workflow)` / metadata 保持 / input-required vs auth-required）。 セキュリティ: Agent Builder path traversal / GCS skill Zip Slip / v0 actions unpickle 制限 / delete_session 所有権検証 / CVE-2026-48710（starlette・fastapi bump）。 LTS 側は v1.35.0 (2026-06-10) で Gemini 3.1 Live 修正を backport
0. **NEW: ADK JS v1.2.0** (2026-06-03) - v1.1.0 後のセキュリティ / 堅牢性修正を正式リリース。 後続 main で Skills Registry（Core + GCP remote + SearchSkillsTool、 #422-424）、 OpenAPI parser/auth handler part 2 (#385)、 streaming prototype pollution 修正 (#410)
0. **NEW: GenAI Toolbox v1.4.0** (2026-06-04) - Data Lineage 統合 (#3285)、 `--ignore-unknown-tools` (#3353)、 Cloud SQL PG vector assist tools (#3203)、 Spanner `search_catalog` (#3140)、 windows/arm64 配布。 セキュリティ: identifier injection 防止 (#3219)、 opaque token issuer 必須化 (#3360)、 Google/Generic OAuth 検証分離 (#3341)、 Looker filter escape (#3289)
0. **NEW: ADK Go v1.4.0** (2026-05-29) - Context unification（tool context を callbackContext にマージする内部統合: #871, #868）を軸に、 adka2a structured error propagation (#874)、 examples / CLI launcher の a2a-go/v2 SDK 移行 (#780)、 StreamingResponseAggregator の metadata-only SSE チャンク許容（abort せずストリーム継続: #918）、 conformance test recording plugin (#890) を取り込み
0. **NEW: GenAI Toolbox v1.3.0** (2026-05-21) - `cloud-sql-admin-execute-sql-many` / `cloud-sql-admin-sql-many` bulk ツール (#3083)、 SQLCommenter による client metadata 送出 (#3064)、 MCP auth tool-level scopes バリデーション (#3049)、 HTTP tool path traversal / base path scope escape 防止（セキュリティ: #3218）、 toolset/promptset boundary 強制 (#3036) を正式リリース。 後続の identifier injection 防止 (#3219) / thrift CVE-2026-41602 対応 (#3312) は v1.4.0 (2026-06-04) で正式リリース
0. **NEW: GKE MCP v0.13.0** (2026-05-28) - k8s リソース操作ツール群を一括拡充: `list_k8s_api_resources` (#378)、 `patch_k8s_resource` (#387)、 `get_k8s_rollout_status` (#386)、 `check_k8s_auth` (#385)、 `describe_k8s_resource` (#388)、 `get_k8s_cluster_info` (#379)、 `get_k8s_logs` (#370)、 `delete_k8s_resource` (#368)。 delete のデフォルト cascade policy を background 化 (#376)、 install checksum verification (#398)、 insecure `pull_request_target` 防止 CI (#400)
0. **NEW: Google Analytics MCP 0.6.0** (2026-05-21) - subprocess stdio handle inheritance 防止 (#154) を正式リリース。 v0.4.0 #151（tool call deadlock / stdout corruption）修正のフォローアップ deadlock を解消
0. **NEW: ADK Python v2.0.0 GA** (2026-05-19) - **Google ADK の v2.0 General Availability** 到達。 Multi-Agent Workflow Engine (Flexible Execution Graphs + Intelligent Task Delegation: 並列 sub-agent workers、 nested 階層チーム、 resilient dynamic scheduling) と Dynamic Agent Collaboration (Native Inter-Agent Routing: messaging / control state handoffs / context propagation) を production-grade に。 main ブランチを v2.0.0 へ transition。 アルファ (a1〜a3) / ベータ (b1) 経由でリリース
0. **NEW: ADK Go v1.3.0** (2026-05-20) - Live bidirectional streaming のコア機能を一括リリース: session resumption (#837)、 streaming tools (#836)、 audio cache for save artifact (#838)、 sequential agent live run (#835)、 live example (#834)、 core bidirectional streaming (#833)。 a2a-go/v2 対応、 VertexAI MemoryBank サポート、 user auth propagation 修正 (adka2a compat)
0. **NEW: Agent Starter Pack maintenance mode** (2026-05-21) - **公式に maintenance mode を surface**、 後継 **agents-cli** への移行を push (#967)。 Google の agent dev tooling 戦略は事実上 agents-cli へ移行
0. **NEW: UCP loyalty extension** (#340) - catalog / cart / checkout capability に loyalty 拡張を追加。 既存 discount 拡張に続く 2 つ目の正式拡張で、 commerce プロトコルの拡張軸が広がる
0. **NEW: UTCP v1.0** (直近 commit 2026-05-05, 新規追跡開始) - Universal Tool Calling Protocol。 MCP が proxy 経由ツール呼び出しなのに対し、 agent が discovery 後 native endpoint (HTTP/gRPC/WebSocket/CLI) を直接叩く設計で wrapper tax 削減。 v1.0 で plugin-based 構成へ再設計、 MCP プロトコル自体も plugin として包摂。 Python / TypeScript / Go 公式実装あり
0. **NEW: payments/ ディレクトリ新設** - 既存 commerce 系 5 件 (ACP / AP2 / UCP / x402 / Visa-TAP) を `protocols/` から `payments/` に分離 + Mastercard Verifiable Intent を新規追加で計 6 件。 generic protocols と決済系で関心領域を明確化
0. **NEW: Visa Trusted Agent Protocol** (新規追跡開始, `payments/`) - Agentic commerce における agent identity / authorization の cryptographic 標準。 AI エージェントが merchant に対して timestamp / session id / key id を含む暗号署名で identity と user 委任権限を証明。 既存 ACP/AP2/UCP/x402 の identity 補完レイヤ
0. **NEW: Mastercard Verifiable Intent v0.1.0** (2026-03-05 OSS化, 新規追跡開始, `payments/`) - Mastercard + Google 共同開発。 **SD-JWT (Selective Disclosure JWT)** ベースで user → agent への delegation scope を tamper-evident に証明。 Immediate / Autonomous の 2 実行モード。 FIDO/EMVCo/IETF/W3C ベース。 AP2 / UCP との相互運用設計。 Adyen / Worldpay / Fiserv / IBM / Checkout.com / Basis Theory / Getnet が支持表明
0. **NEW: NLIP 1st edition** (Ecma 承認 2025-12-10, 新規追跡開始) - Ecma TC56 が標準化した natural-language application-level プロトコル。 ECMA-430 本体 + 4 binding (HTTP/WebSocket/AMQP/Security profiles) + TR/113 解説書の 6 文書構成。 ISO 提出済み (2026-01-25)、 Claude Skills 互換 reference 実装は 2026-02-28 予定
0. **NEW: Gemini Cloud Assist MCP v0.8.0** (2026-04-21, 新規追跡開始) - GCP 環境を natural language で understand / manage / troubleshoot する MCP サーバー。 Local Node.js から Remote MCP Server architecture へ全面移行（**破壊的変更**）、 v0.2.0 (local) を完全 deprecate。 `designing-and-deploying-infrastructure` / `operating-google-cloud` skills 同梱。 現在 Private Preview (allowlist 制)
1. **ADK Python v1.33.0 → v1.34.0 → v2.0.0 GA** (2026-05-08 / 05-18 / 05-19) - 短期間で 3 リリース。 v1.33.0 で BufferableSessionService、 LlmResponse function call/response ヘルパー、 ApigeeLlm credential 注入、 adk web hot reload。 v1.34.0 で a2a persistent task stores、 Gemini Live API in ADK evaluate、 mTLS Cloud Telemetry exporter、 GCPSkillRegistry / Skill Registry 実装、 McpToolset OAuth PKCE。 v2.0.0 GA で multi-agent workflow engine と dynamic agent collaboration の production-grade 確立
1a. **ADK Python v1.31.x → v1.32.0** (2026-04-30) - **前安定リリース**。Anthropic thinking blocks、native OpenTelemetry agentic metrics、event compaction tracing、GcpAuthProvider 2LO/3LO/API Key sample、Cold start ~25% 短縮、複数のセキュリティ修正（SSRF/RCE/credential isolation/PubSub user_id sanitization）
2. **GKE MCP v0.11.1 → v0.12.0** - LLM 抽象 factory + Anthropic Claude ADK adapter、node pool 管理ツール、giq fetch_model_servers / fetch_profiles、GKE AI TPU トラブルシュート skill
3. **Google Analytics MCP v0.4.0 → 0.5.0** - 新規 conversions schema/spec ツール、 google-analytics-data v0.22.0 / admin v0.29.0 への依存バンプ。 v0.4.0 では `run_funnel_report` ツール（Data API v1alpha）、ADK 用 Skills、tool call deadlock / stdout corruption 修正
4. **MCP-UI v7.1.0 → v7.1.1** (2026-05-09) - sandbox proxy iframe timeout キャンセルで StrictMode unhandled rejection を防止。 v7.1.0 では AppRenderer に `hostInfo` / `hostCapabilities` props 追加 (2026-05-01)
5. **AP2 v0.1.0 → v0.2.0** (2026-04-28) - **V2 仕様正式リリース**。PaymentReceipt、X402 決済統合、Vertex AI 認証、Go サンプル、UCP 統合等を含む 7 ヶ月ぶりの大型リリース
6. **ADK JS v1.0.0 → v1.1.0 + 後続** - UrlContextTool（Gemini 2+ URL context）、Vertex AI Search Tool、MCP プレフィックス strip、AgentTool セッション再利用、Google Maps tool、VertexRagRetrievalTool、MCPToolset.getTools toolFilter
7. **ADK Go v1.2.0 → v1.3.0** (2026-05-20) - Live bidirectional streaming のコア (session resumption / streaming tools / audio cache / sequential agent live run / live example)、 a2a-go/v2 対応、 VertexAI MemoryBank、 stream_query simple text サポート、 `gen_ai.usage` 属性リネーム、 user auth propagation 修正
8. **ADK Python v1.30.0 → v1.31.1** - v1.31.x で Parameter Manager/Secret Manager ユーザーエージェント、Firestore、Vertex AI Agent Engine Sandbox、`memories.ingest_events`
9. **ACP v2026-01-30 → v2026-04-17 + 後続** - Cart Capability、Product Feeds API、Marketing Consent、Markdown Content Specification、Payment Intent、Mandatory Idempotency 等。リリース後も Order Schema Post-Checkout (#232)、`UpsertProductsResponse` JSON Schema 追加 (#241)、Meta TSC メンバー追加 (#236) など継続更新
10. **AG-UI release/2026-04-22** - State Snapshot/Delta コンパクション (#1535)、AgentCapabilities Python SDK 追加、Strands/Mastra アダプター修正、LFS マイグレーション
11. **MCP-Apps v1.7.0 → v1.7.1** - PDF Server lazy フォーム抽出 (#639)、キャッシュインスタンス間共有 (#637)、qr-server FastMCP host/port サポート (#372)
12. **OpenResponses + Phase Compaction** - WebSocket モード実装に加えて compact response エンドポイント、phase parameter 追加
13. **GenAI Toolbox v1.1.0 → v1.2.0** (2026-05-07) - **新たなマイナー安定リリース**。 Cloud Storage source (list/read + write/copy/move/delete)、 HTTPS/TLS listener、 BigQuery `maximumBytesBilled`、 Knowledge-catalog Data Quality Scans 検索ツールを正式取り込み。 v1.2.0 後では MCP auth tool-level scopes バリデーション (#3049)、 HTTP tool path traversal 防止 (#3218、 セキュリティ) 等が進行中
14. **MCP 2025-11-25 後** - **SEP-2567 (Sessionless MCP via Explicit State Handles) Final/Accepted 昇格** と **SEP-2575 (Make MCP Stateless)** によりステートレス志向への大型シフト進行中。 vm2 3.11.3 への GHSA-vwrp-x96c-mhwq 対応セキュリティバンプ。 MRTR (Multi-Round Tool Result) スキーマ整備、`InputRequiredResult` への rename、Augmented Tool Call フロー、SDK Working Group チャーター
15. **Agent Starter Pack v0.41.1 → v0.41.3 (+ maintenance mode)** - langgraph-prebuilt pin、 v0.41.2 で次世代プロジェクト「agents-cli」発表 (#952)、 v0.41.3 後の **#967 で公式に maintenance mode を surface し agents-cli へ移行を push**
16. **UCP v2026-04-08 以降** - **Identity Linking OAuth 2.0 foundation (#354, 破壊的)**、attribution フィールド (#391)、core-concepts 拡充 (#336)、Twum Djin Governance Council 追加
17. **gcloud-mcp storage-mcp-v0.5.1** - `delete_object` を destructive tools へ移動（セキュリティ強化）
18. **ADP データセット拡充** - per-step reward フィールド (#183)、CoderForge-Preview, Nemotron Terminal Corpus, Toucan, Toucan-1.5M, mini-coder トラジェクトリー、Catalog dataset ガイドライン (#186) など多数追加
19. **MCP Security secops-v0.7.0 後** - `list_parsers` ツール追加と return type 標準化 + pagination token 対応 (#252)
20. **Cloud Run MCP v1.10.0 後** - docker compose deployments、BUILD_ID base scheduled cloudbuild、Cloud Run skills

### 新規プロトコル統合

0. **UTCP (Universal Tool Calling Protocol)** - MCP の構造的代替案。 agent が proxy を介さず native endpoint を直接呼び出す。 既存 MCP は plugin として包摂され UTCP の中で共存可能
0. **Visa Trusted Agent Protocol** (`payments/`) - 大手金融プレイヤー (Visa) が回す agentic commerce identity 標準。 既存 ACP/AP2/UCP/x402 の identity 補完軸を埋める
0. **Mastercard Verifiable Intent** (`payments/`) - Mastercard + Google 共同。 SD-JWT chain で user → agent delegation scope を tamper-evident に verify。 Selective Disclosure でプライバシー保護寄り。 Visa TAP と並ぶ識別系の両極を成す
0. **NLIP (Natural Language Interaction Protocol)** - Ecma TC56 標準化、 ECMA-430〜434 + TR/113 構成。 既存ラインアップ（A2A: agent ↔ agent opaque / MCP: agent ↔ tool）と相補で natural-language application-level 通信を担当
0. **Gemini Cloud Assist MCP** - GCP 環境の natural-language operation 用 MCP サーバー（Private Preview）。 既存 cloud-run-mcp / gke-mcp / gcloud-mcp と並ぶ「GCP オペレーショナル」軸の補完
1. **AP2 v0.2.0** - V2 仕様正式リリース。X402 決済、Vertex AI 認証、UCP 連携、Go サンプル
2. **ADK JS + UrlContextTool / Vertex AI Search Tool** - Gemini 2+ URL context grounding と Vertex AI Search ツール
3. **ADK Go + Agent Engine** - Agent Engine 統合、既存インスタンス更新、自動 session ID 生成
4. **ADK Python + Firestore / Vertex AI Agent Engine Sandbox** - Firestore サポートと Agent Engine Sandbox 統合
5. **ADK JS + Skills システム** - Skills interface、toolset、loader、script execution をサポート
6. **ADK JS + RoutedAgent/RoutedLlm** - 新しいルーティング型 Agent / LLM
7. **ADK Go + Skill Source proxy** - マージ/プリロード対応の skill source proxy 群
8. **GenAI Toolbox + Cloud Storage バケット/オブジェクト管理** - bucket/object 管理ツールと HTTPS/TLS リスナー
9. **ACP + Product Feeds / Cart Capability / Marketing Consent** - Commerce プロトコルの大幅拡張
9a. **UCP + Loyalty Extension** (#340) - catalog / cart / checkout capability に loyalty 拡張追加。 既存 discount 拡張に続く 2 つ目の正式拡張
9b. **GenAI Toolbox + cloud-sql-admin-execute-sql-many / sql-many** (#3083) - Cloud SQL admin 系の bulk execute/sql ツール
9c. **GKE MCP + apply_k8s_manifest + adk-anthropic-go** (#358, #356) - K8s manifest 適用ツール、 ADK 上の Anthropic Claude Go ライブラリ統合
9d. **ADK JS + Agent Engine Sandbox Code Executor** (#317) - Agent Engine Sandbox 経由のコード実行 Executor
9e. **ADK Python + GCPSkillRegistry / Skill Registry / Gemini Live API in evaluate** (v1.34.0) - Skill Registry 実装と Gemini Live API 評価対応
9f. **ADK Go + Live bidirectional streaming コア群** (v1.3.0) - session resumption / streaming tools / audio cache / sequential agent live run / live example
10. **A2UI + Kotlin SDK / C++ ポート** - Kotlin SDK conformance tests と Python エージェント SDK の C++ ポート初期実装
11. **ADP + per-step reward / 新規データセット群** - RL トレーニング用 reward フィールド、CoderForge-Preview/Nemotron Terminal Corpus/Toucan などのデータセット
12. **MCP-Apps + WebMCP-style ツール登録** - WebMCP 風のツール登録仕様
13. **OpenResponses + WebSocket / Phase Compaction** - WebSocket mode と compact response エンドポイント
14. **GKE MCP + GIQ tool** - GIQ tool を manifest agent に統合
15. **gcloud-mcp + backupdr-mcp** - Backup DR MCP サーバー新規追加
16. **AgentSkills + fast-agent / Google AI Edge Gallery / nanobot / Workshop.ai** - クライアントショーケース拡張
17. **A2A + カスタム protocol bindings** - カスタムプロトコルバインディングドキュメント追加

### セキュリティ更新

- **ADK Python v2.2.0 (2026-06-04)**: **Agent Builder file tools の path traversal ブロック (1fa7cda)**、 **GCS skill 展開の Zip Slip 修正 (2f15c6c)**、 **v0 actions blob の unpickle 制限 (9db48ce)**、 **`delete_session` の session 所有権検証 (b2916c7)**、 **CVE-2026-48710 対応（starlette / fastapi bump, 81add39）**、 ReadFileTool の shell escape (e16629b)、 OAuth2 token request の scope 省略 (6ce4b87)
- **ADK JS v1.2.0 (2026-06-03) + 後続 main**: v1.1.0 後の **CORS 脆弱性修正（express.urlencoded parser 無効化, #378）**、 **OAuth2 SSRF 防止（IPv4-mapped IPv6 ブロック, #354）**、 run_sse hardcoded `*` 削除 (#360)、 AdkApiServer host 制限 (#383) を正式リリース。 main では **streaming の prototype pollution 修正（model 制御 JSON path 経由, #410）**
- **GenAI Toolbox v1.4.0 (2026-06-04)**: **ClickHouse / BigQuery identifier injection 防止 (#3219)**、 **opaque token validation の issuer 必須化 (#3360)**、 **Google / Generic MCP OAuth 検証分離 (#3341)**、 Looker filter value escape (#3289)、 apache/thrift CVE-2026-41602 対応を正式リリース
- **MCP-Apps v1.7.4 (2026-06-04)**: **lazy-auth-server token exchange で PKCE 必須化 + redirect_uri バインド (#681)** — OAuth authorization code interception 攻撃を防止。 PKCE 非対応の旧フローは拒否される
- **GKE MCP v0.13.0 (2026-05-28)**: install 時の checksum verification 追加 (#398)、 insecure `pull_request_target` 利用を防ぐ CI チェック追加 (#400)
- **ADK Python v1.34.0 / v2.0.0 GA**: refreshed OAuth2 credentials の store 永続化 (218ea76, #5329)、 不要 OAuth フロー削除 (c35a579)、 Interactions API での dict 値 pre-serialization 起因の double-escape 防止 (85f397d)、 AnyIO CancelScope task boundary violations 防止 (4309159)、 AnthropicLlm import 時の OSError catch (91cb5c6)、 HITL イベントの誤 compaction 防止 (bb2efb6)
- **MCP HEAD (2025-11-25 後)**: **vm2 3.11.3 セキュリティバンプ GHSA-vwrp-x96c-mhwq** (#2711)
- **GenAI Toolbox (v1.3.0 後 → v1.4.0 で取り込み済み)**: **ClickHouse / BigQuery identifier injection 防止 (#3219)**、 **apache/thrift CVE-2026-41602 対応（v0.22.0 → v0.23.0, #3312）**、 Looker unquoted parameters の filter value escape (#3289)
- **GenAI Toolbox v1.3.0 (リリース済み, 2026-05-21)**: **HTTP tool path traversal / base path scope escape 防止 (#3218)**、 MCP auth tool-level scopes バリデーション (#3049)、 toolset/promptset boundary 強制 (#3036)
- **GenAI Toolbox v1.2.0 (リリース済み, 2026-05-07)**: SSE hardcoded `*` allowed origin 削除 (#3054、 セキュリティ取り込み)、 router-level logger injection (#3067)
- **ACP v2026-04-17 後 → UCP v2026-04-08 後**: urllib3 v2.7.0 セキュリティバンプ (#434)
- **ADK Python v1.33.0 後 HEAD**: AnthropicLlm import の OSError catch（クラッシュ回避）、 refreshed OAuth2 credentials の persist (auth) など safety hardening 多数
- **ADK Python v1.32.0 (リリース済み, 2026-04-30)**: **`load_web_page` SSRF / local-file アクセス修正 (0447e93)**、**nested YAML configs 経由の RCE 脆弱性ブロック (74f235b)**、credential isolation in auth context (race condition / データ漏洩防止) (5578772)、PubSub サブスクリプション / Eventarc source 由来 user_id サニタイズ (#5324, 0c4f157)、litellm 最低バージョンを 1.83.7 へ引き上げ CVE パッチ取り込み (6d2ada8)、Vertex RAG memory display name スコープ化 (784350d)
- **GenAI Toolbox (未リリースから v1.2.0 で取り込み済み)**: pgx v5.9.2 セキュリティ更新 (#3133)、SSE hardcoded `*` allowed origin 削除 (#3054)、macOS SDK を内部 GCS バケットに移行 (#3025)、pytest v9.0.3 セキュリティ更新 (#3047)
- **gcloud-mcp storage-mcp v0.6.0 (2026-05-06)**: `download_object_safe` ツール削除（破壊的変更、 destination パスへの sensitive 書き込みを許す設計だったため）。 destructive 経路の `download_object` または `read_object_content` / `read_object_metadata` への移行が必要 (#420, #422)
- **gcloud-mcp storage-mcp**: `delete_object` を safe → destructive tools へ移動（誤削除防止）
- **A2UI**: Python google-adk 1.28.1 へ bump（セキュリティ）
- **MCP-Apps v1.7.0**: vite / hono / @hono/node-server パッチバージョンへのバンプ (#616)
- **AG-UI**: CVE-2026-25528 依存関係脆弱性修正 (#1527)、ADK ミドルウェア critical/high Dependabot 脆弱性修正 (#1517)
- **ADK Python v1.30.0**: Agent Registry credential 漏洩脆弱性修正、path traversal バリデーション (#5110)
- **ADK JS**: FileArtifactService パストラバーサル脆弱性修正 (CWE-22)、lodash セキュリティ更新
- **UCP**: lodash セキュリティ更新（Trivy 脆弱性修正） (#333)、lockfile registries 標準化 (#368)
- **x402**: HTTPFacilitatorClient リダイレクト修正、Facilitator signer ランダム選択修正
- **MCP-Apps v1.4.0**: path-to-regexp ReDoS CVE 修正
- **GKE MCP v0.10.0**: Shell Command Injection 修正（`ui/scripts/build.ts`）
- **Google Analytics MCP**: google-adk 最低バージョン 1.28.1 更新（GHSA-rg7c-g689-fr3x 対応）
- **MCP**: OIDC / エンタープライズ管理認可更新、SEP-2207 リフレッシュトークンガイダンス
