---
title: "MCP エコシステムの認可アーキテクチャ進化 — OIDC、エンタープライズ管理、Contributor Ladder"
date: 2026-03-23
tags: [mcp, oidc, security, governance]
source: docs/changelogs.md
---

# MCP エコシステムの認可アーキテクチャ進化 — OIDC、エンタープライズ管理、Contributor Ladder

Model Context Protocol (MCP) の最新の更新は、プロトコル仕様の技術的な進化とコミュニティガバナンスの成熟が同時に進んでいることを示している。現行バージョン 2025-11-25 を基盤に、MCP-Apps v1.2.2 (2026-03-17)、MCP-UI client/v7.0.0 (2026-03-12) と連動しながら、OIDC 統合、エンタープライズ管理認可、Contributor Ladder——3つの軸から MCP の現在地を見る。

## 認可アーキテクチャの進化

### OIDC 統合（バージョン 2025-11-25）

MCP バージョン 2025-11-25 において、OIDC (OpenID Connect) 統合が進んでいる。OpenID Connect Discovery 1.0 による認可サーバーディスカバリーが対応され、MCP サーバーが標準的な ID プロバイダーと連携できるようになった。外部認証サポート付き認可仕様の強化と GitHub Security Advisories 統合も含まれる。SSRF セキュリティ対策ドキュメントも同時に追加された。

これまで MCP の認証は各実装に委ねられていたが、OIDC 統合により：
- 企業の既存 IdP (Okta, Azure AD, Google Workspace) との統合が標準化
- トークン管理のベストプラクティスがプロトコルレベルで定義
- MCP クライアント間でのシングルサインオンが可能に

### エンタープライズ管理認可

OIDC に加えて、エンタープライズ向けの管理認可機能が更新された。これは大規模組織で MCP サーバーを運用する際の：
- 管理者による MCP サーバーアクセスの一元管理
- ポリシーベースのツールアクセス制御
- 監査ログの標準化

を可能にする。

### ツールエラーハンドリングの再構成

認可と密接に関連するのが、ツールエラーハンドリングの再構成だ。認可エラー、権限不足、レート制限などのエラーが体系的に整理され、クライアントが適切にハンドリングできるようになった。

### MCP-Apps v1.2.2 (2026-03-17) — CSP とセキュリティ強化

MCP-Apps v1.2.2 ではアンバンドルアセット向け Content Security Policy (CSP) 要件が文書化された。v1.1.x では GitHub Security Advisories ガイダンス (#472) が追加されており、エコシステム全体でのセキュリティ標準が整備されている。Zod v4 互換性修正 (#548)、E2E セキュリティテスト改善 (#540) も v1.2.x で対応済みだ。

## セキュリティ強化の全体像

MCP エコシステム全体で、セキュリティ関連の更新が集中している。

| コンポーネント | セキュリティ更新 |
|-------------|---------------|
| **MCP 本体** | OIDC、エンタープライズ認可、SSRF 対策ドキュメント |
| **MCP Apps** | CSP (Content Security Policy) 要件文書化 |
| **MCP Security** | Rule Exclusions 管理、Investigation 管理、Watchlist 管理 |
| **GKE MCP** | SECURITY.md、Workload Security スキル |
| **ADK Python** | AuthProviderRegistry、OpenTelemetry エラーコードキャプチャ |

外部認証サポート付きの認可仕様強化と GitHub Security Advisories の統合も入っており、脆弱性管理もプロトコルレベルで対応されている。

## Contributor Ladder — ガバナンスの成熟

技術面と並行して、MCP のコミュニティガバナンスも進化している。

### SEP-2148: MCP Contributor Ladder

MCP Contributor Ladder (SEP-2148) は、コントリビューターの役割と昇格パスを定義する仕様拡張提案。オープンソースプロジェクトのガバナンスモデルとして確立されたパターンだが、MCP でこれが正式に定義されたことは、プロジェクトの成熟を示す。

### Extensions フレームワーク (SEP-2133)

Extensions フレームワーク（SEP-2133、Final）が確定し、拡張機能ケイパビリティのスキーマが追加された。Extensions がトップレベルタブに昇格（#2263）したことと合わせて、MCP のエクステンシビリティが正式な設計原則として位置づけられた。デザイン原則ページ（#2303）も追加されている。

### MCP-UI client/v7.0.0 (2026-03-12) — レガシー仕様の終焉

MCP-UI は client/v7.0.0 (2026-03-12) でレガシー仕様を完全削除（破壊的変更、#185/#187）した。v6.0.0 では廃止コンテンツタイプの削除と MIME タイプ変更、v5.0.0 では `delivery` → `encoding`、`flavor` → `framework` のリネームがあった。レガシーを段階的に整理しながら、現行仕様への統一を進めている。

### SDK 階層評価

SDK の Tier 評価も注目に値する：
- **Tier 1**: Python SDK, C# SDK, Go SDK（最高レベルの互換性保証）
- **Tier 2**: Java SDK
- **Tier 3**: Swift SDK, PHP SDK

この階層化は、MCP エコシステムの優先言語と成熟度を明確にし、利用者の SDK 選択を助ける。

## MCP クライアントの拡大

2025-11-25 リリース以降、MCP クライアントの対応範囲が急速に広がった。

| クライアント | 対応状況 |
|------------|---------|
| Claude Desktop | 対応済み |
| ChatGPT | 対応済み |
| VSCode | 対応済み |
| Postman | 対応済み |
| goose | 対応済み |
| MCPJam | 対応済み |
| Copilot | 対応済み |
| Continue | 対応済み（2026-03-16 追加） |

Tool Annotations ブログ（2026-03-16）も公開され、ツールメタデータの活用方法が整理された。

## まとめ

MCP は「プロトコル仕様を書く段階」から「エンタープライズで運用する段階」へ移行している。バージョン 2025-11-25 を軸に、MCP-Apps v1.2.2 (2026-03-17) と MCP-UI client/v7.0.0 (2026-03-12) が連動しながら、OIDC 統合とエンタープライズ管理認可は技術面の成熟、Contributor Ladder と SDK 階層評価はガバナンス面の成熟を示す。この両輪が揃ったことで、MCP は企業環境での本格採用に向けた準備が整いつつある。

## 参考リンク

- [MCP Specification](https://spec.modelcontextprotocol.io/)
- [MCP GitHub](https://github.com/modelcontextprotocol/modelcontextprotocol)
- [Tool Annotations Blog (2026-03-16)](https://modelcontextprotocol.io/blog/tool-annotations)
