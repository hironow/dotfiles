# プロトコル変更ログ

最終更新: 2026-01-20

各プロトコルサブモジュールの主要な変更点をまとめたドキュメント。

---

## A2UI (Agent-to-User Interface)

**現行バージョン**: v0.9 (v0.8も継続サポート)

### 主要な変更点

- **テーマシステム刷新**: `styles` から `theme` にリネーム、`createSurface` にプライマリカラーサポートを追加
- **A2A Extension化**: A2UI v0.9 が A2A Extension として正式に位置づけ
- **データ同期削除**: プロトコルからデータ同期機能を削除 (#490)
- **ブロードキャスト明確化**: ブロードキャストメッセージはサーフェスを作成したサーバーのみに送信されることを明確化 (#503)
- **Flutter対応**: Flutterレンダラーのプレースホルダー追加、GenUIリポジトリへ誘導 (#425)
- **カタログ統合**: weight プロパティを標準カタログへ移動 (#491)
- **文字列補間改善**: 専用の `string_format` 関数を導入
- **クライアント-サーバーデータ更新**: 設定機構を追加 (#467)

### 参考リンク
- [A2UI Specification](https://github.com/anthropics/A2UI)

---

## AG-UI (Agent-User Interaction Protocol)

**現行バージョン**: v0.0.43

### 主要な変更点

- **ADKミドルウェア改善**: partial events からの function calls をスキップ (#968, #970)
- **コンテキストサポート**: `RunAgentInput.context` サポートを実装 (#964)
- **思考イベント変換**: 思考パーツを THINKING イベントに変換 (#953, #954)
- **セキュリティ修正**: Snyk による脆弱性4件を修正 (#950)
- **依存関係整理**: RxJS を peer dependencies から dependencies へ移動（バージョン不整合防止）
- **Android/Kotlin更新**: A2UI-4K を 0.8.1 に、AGP を 8.12.0 に更新 (#947)
- **DatabaseSessionService修正**: 互換性問題を修正 (#958)

### 新規SDKリリース
- **Dart SDK v0.1.0** (2026-01-21)

### フレームワーク統合 (1st party)
- Microsoft Agent Framework
- Google ADK
- AWS Strands
- Mastra
- Pydantic AI
- Agno
- LlamaIndex
- AG2

### パートナーシップ
- LangGraph
- CrewAI

### コミュニティSDK (開発中)
- .NET, Nim, Flowise, Langflow

### 参考リンク
- [AG-UI Protocol](https://github.com/ag-ui-protocol/ag-ui)

---

## MCP (Model Context Protocol)

**現行バージョン**: 2025-11-25 (日付ベースバージョニング)

### プロトコル強化

- **OpenID Connect Discovery 1.0**: 認可サーバー検出をサポート (#797)
- **アイコンサポート**: ツール、リソース、リソーステンプレート、プロンプトにアイコンメタデータを追加 (SEP-973)
- **増分スコープ同意**: WWW-Authenticate ヘッダーによる増分同意 (SEP-835)
- **Elicitationスキーマ更新**: EnumSchema を標準ベースのアプローチに更新 (SEP-1330)
- **URLモードElicitation**: URL入力モードをサポート (SEP-1036)
- **サンプリングでのツール呼び出し**: `tools` と `toolChoice` パラメータを追加 (SEP-1577)
- **OAuthクライアントIDメタデータ**: クライアント登録用ドキュメント (SEP-991)

### 実験的機能
- **Tasks サポート**: 永続的リクエスト追跡、ポーリング、遅延結果取得 (SEP-1686)

### マイナーアップデート

- stdio トランスポートでの stderr ログ利用を明確化
- Implementation インターフェースに `description` フィールド追加（オプション）
- 無効な Origin ヘッダーに HTTP 403 Forbidden を返却
- セキュリティベストプラクティスガイダンス更新
- 入力バリデーションエラーをツール実行エラーとして返却 (SEP-1303)
- SSE ポーリングサポート、サーバー起動の切断対応 (SEP-1699)
- Elicitationスキーマでプリミティブ型のデフォルト値サポート (SEP-1034)
- **JSON Schema 2020-12** をデフォルトダイアレクトに設定 (SEP-1613)

### ガバナンス

- ガバナンス体制の正式化 (SEP-932)
- Working Groups と Interest Groups の設立 (SEP-1302)
- SDK 階層システム導入（明確な要件付き）(SEP-1730)

### 参考リンク
- [MCP Specification](https://spec.modelcontextprotocol.io/)
- [MCP GitHub](https://github.com/modelcontextprotocol/modelcontextprotocol)

---

## OpenResponses

**概要**: マルチプロバイダー対応の相互運用可能なLLMインターフェース仕様

### 主要な変更点

- **ドキュメント修正**: README と仕様のタイポ修正 (PR #4)
- 主に軽微なドキュメント整備

### 特徴
- エージェンティックループのサポート
- ツール呼び出しパターンの標準化
- セマンティックストリーミングイベント
- OpenAPI仕様 (`public/openapi/openapi.json`)

### 参考リンク
- [OpenResponses](https://github.com/openrouter/openresponses)

---

## UCP (Universal Commerce Protocol)

**概要**: プラットフォーム、ビジネス、PSP、認証プロバイダー間の商取引相互運用性のためのオープンスタンダード

### 主要な変更点

- **GOVERNANCE.md リファクタリング**: 運用ルールとプロセスを削除し CONTRIBUTING.md へ統合（安定性向上）
- **enhancement-proposal.md 追加**: 正式な機能提案テンプレートとプロセスを確立
- **貢献ガイドライン拡充**: 明確な意思決定レベル（L1/L2）を定義
- **Issue テンプレート追加**: バグ報告と機能リクエスト用テンプレート
- **提案ライフサイクル確立**: Provisional → Implementable → Implemented

### ガバナンス構造
- Tech Council
- Governing Council
- Domain Working Groups

### 参考リンク
- [UCP Protocol](https://github.com/anthropics/UCP)

---

## x402 (Internet Native Payments)

**現行バージョン**: npm @x402/next@v2.2.0 / PyPI v1.0.0

### 主要な変更点

- **Go実装強化**: facilitator エラーを複数パッケージで定数としてエクスポート
- **エラーハンドリング改善**: EVM/SVM 機構のエラー処理をリファクタリング（23ファイル、+449/-221行）
- **Bazaar拡張仕様追加**: エコシステムパートナー向けの Bazaar ディスカバリーをサポート
- **動的Bazaarインポート修正**: ディスカバリーメタデータの改善
- **Hono paywall bypass修正**

### エコシステム拡大 (新規ファシリテーター)

| 名称 | 説明 |
|------|------|
| **BlockRun.AI** | Pay-as-you-go AIゲートウェイ、主要LLMをx402 on Baseでサポート |
| **SolPay** | Solana x402ファシリテーター、メインネットでUSDCサポート |
| BlackSwan | 新規ファシリテーター |
| AutoIncentive Facilitator | 自動インセンティブ |
| Dexter | 新規ファシリテーター |
| OpenFacilitator | オープンファシリテーター |
| Rencom | 新規ファシリテーター |
| RelAI | AI関連ファシリテーター |
| PEAC Protocol | 新規プロトコル統合 |

### 参考リンク
- [x402 Protocol](https://github.com/x402-protocol/x402)
- [x402 npm packages](https://www.npmjs.com/search?q=%40x402)

---

## 注目ポイント

### 要チェック機能

1. **MCP Tasks (実験的)**: 長時間実行リクエストのポーリングと遅延結果取得が可能に
2. **AG-UI Dart SDK**: モバイル/Flutter開発者向けの新しいオプション
3. **x402 エコシステム**: 1週間で10以上の新規ファシリテーターが追加される活発な動き

### 破壊的変更の可能性

- **A2UI**: `styles` → `theme` のリネーム、データ同期機能の削除
- **MCP**: JSON Schema 2020-12 がデフォルトダイアレクトに変更

### セキュリティ更新

- **AG-UI**: Snykによる脆弱性4件修正済み
