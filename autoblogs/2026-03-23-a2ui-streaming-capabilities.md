---
title: "A2UI のストリーミングパーサーと Client Capabilities API — エージェント UI の次のステップ"
date: 2026-03-23
tags: [a2ui, agent-ui, mcp-apps, streaming]
source: docs/changelogs.md
---

# A2UI のストリーミングパーサーと Client Capabilities API — エージェント UI の次のステップ

A2UI (Agent-to-User Interface) プロトコルが、v0.9 (2026-01-22) のリリース以降も急速に進化している。ストリーミングパーサー、Client Capabilities API、リアクティブサーフェスステート——これらの未リリース変更が示す方向を追う。MCP-Apps v1.2.2 (2026-03-17)、MCP-UI client/v7.0.0 (2026-03-12) との連携も含め、エージェント UI エコシステム全体の現在地を整理する。

## v0.9 の哲学変更を振り返る

A2UI v0.9 (2026-01-22) は「Prompt First」設計への転換だった。構造化出力優先からプロンプト埋め込み優先へ。メッセージタイプの刷新（`beginRendering` → `createSurface`、`surfaceUpdate` → `updateComponents`）、コンポーネント構造の簡素化、モジュラースキーマ（`common_types.json`, `server_to_client.json`, `standard_catalog.json`）への分割。Enum Case の `lowerCamelCase` 統一 (#639)、UI Validation Events の `TextField` 対応 (#609) も含む。これが基盤となって、現在の進化がある。

なお、v0.9 以前の v0.8 系（`@a2ui/react v0_8`）は後方互換用サブディレクトリとして維持されており、移行パスが確保されている。

## 未リリース変更の全体像

### Client Capabilities API

MessageProcessor に Client Capabilities API が追加された。これにより、クライアント（ブラウザ、ネイティブアプリ、ターミナル等）が自分の能力をサーバーに宣言できる。

たとえばブラウザクライアントは「WebGL をサポートする」「動画再生可能」と宣言し、ターミナルクライアントは「テキストのみ」と宣言する。サーバーはこの情報をもとに、送信するコンポーネントを適応させる。これは MCP の Capabilities ネゴシエーションと同じパターンだ。

### A2UI ストリーミングパーサー

A2UI メッセージのストリーミングパーサーが実装された。LLM のストリーミング出力をリアルタイムで A2UI コンポーネントに変換する。チャット UI でトークンが流れるように、A2UI コンポーネントも段階的にレンダリングされる。

### Client Reactive Surface State（シグナル）

クライアント側でリアクティブなサーフェスステートが実装された。シグナル（Signals）パターンを採用しており、コンポーネントの状態変更が自動的に UI に伝播する。React の useState や Solid の createSignal に近い概念を、プロトコルレベルで実現している。

### Client Data Model 同期

サーバーとクライアント間のデータモデル同期。`updateDataModel` メッセージ（v0.9 で追加）の実装が進み、双方向のデータフローが確立されつつある。

## MCP Apps との統合

A2UI に MCP Apps が統合された（#748）。MCP Apps v1.2.2 (2026-03-17) の UI ウィジェットを A2UI コンポーネントとしてレンダリングできるようになる（#801）。Calculator App での MCP Tool Call 実装はその実証例だ。MCP-Apps v1.1.x では `downloadFile` 機能や PDF Server の強化が入り、v1.2.x では Zod v4 互換性修正（#548）とモバイルサポート改善（#555）が追加された。

これは重要な統合だ。MCP がツール呼び出しの標準プロトコルとして機能し、A2UI がその結果の表示標準として機能する。ツールの**実行**と**表示**が明確に分離される。

### MCP-UI との連携

MCP-UI client/v7.0.0 (2026-03-12) はレガシー仕様を完全削除する破壊的変更（#185, #187）を含む。v6.0.0 での廃止コンテンツタイプ削除、v5.0.0 での `delivery` → `encoding`・`flavor` → `framework` リネームと続いてきたクリーンアップの集大成だ。A2UI が MCP-UI v7.0.0 以降の新 API に準拠することで、よりクリーンな統合が実現する。

## 技術的成熟の指標

| 変更 | 詳細 |
|------|------|
| **Generic Binder** (#848) | web_core v0.9 の Generic Binder により、フレームワーク非依存のデータバインディングが実現（AG-UI Python SDK v0.1.14 が先行実装したパターンとの設計比較が有益）|
| **Basic Catalog Zod スキーマ** | 型安全なカタログ定義 |
| **Angular v0.9 レンダラー** | React に続き Angular もサポート |
| **@a2ui/react バージョン分割** | バージョン付きサブディレクトリへのリファクタで後方互換性を管理 (v0_8) |
| **React レンダラー** (#542) | React レンダラーの正式実装 |
| **Gallery App 仕様** (#821) | Gallery App 仕様とレンダラーガイドの精緻化 |
| **assemble_catalog.py** (#817) | 新カタログ組み立てスクリプト |
| **サーバーケイパビリティスキーマ** (#731) | トランスポート非依存の機能交換用スキーマ |

## まとめ

A2UI は「エージェントが UI を生成するためのプロトコル」から「エージェント UI のランタイムフレームワーク」へ進化している。Client Capabilities API でクライアント適応、ストリーミングパーサーでリアルタイムレンダリング、シグナルベースのリアクティブステートでインタラクティブ性。MCP Apps 統合により、ツール実行と UI 表示の分離が標準化されつつある。

## 参考リンク

- [A2UI Specification](https://github.com/anthropics/A2UI)
- [MCP-Apps v1.2.2](https://github.com/anthropics/mcp-apps)
- [MCP-UI](https://github.com/MCP-UI-Org/mcp-ui)
