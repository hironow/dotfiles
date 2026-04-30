---
title: "x402 Go v2.7.0 / TypeScript v2.8.0 — Fastify/Echo アダプターと Aptos 対応が示すマルチチェーン決済の設計思想"
date: 2026-03-26
tags: [x402, payments, blockchain, aptos, fastify, echo, multichain]
source: docs/changelogs.md
---

# x402 Go v2.7.0 / TypeScript v2.8.0 — Fastify/Echo アダプターと Aptos 対応が示すマルチチェーン決済の設計思想

2026-03-26 時点で、x402 は Go v2.7.0 と TypeScript Core v2.8.0 をリリースした。Go 版では **Fastify と Echo フレームワークアダプター**の追加、TypeScript 版では **Aptos ブロックチェーンサポート** と `upto` パラメータが主要変更だ。Python v2.5.0 と合わせた 3 言語エコシステムの現在地と、マルチチェーン展開という**設計思想の進化方向性**を整理する。

## Go v2.7.0：フレームワークアダプターの体系化

### Fastify アダプターと Echo アダプターの設計的意味

Go v2.7.0 で追加された **Fastify フレームワークアダプター** と **Echo フレームワークアダプター** は、x402 の Go SDK における **ミドルウェアエコシステム拡大** を意味する。

Fastify と Echo はそれぞれ異なる設計思想を持つ：

| フレームワーク | 設計思想 | ユースケース |
|-------------|---------|------------|
| Fastify | JSON スキーマバリデーション中心、高スループット | API ゲートウェイ、マイクロサービス |
| Echo | シンプルさと拡張性、高速ルーティング | REST API、Web アプリバックエンド |
| (既存) Gin | 軽量高速、豊富なエコシステム | 汎用 Web アプリ |

3 フレームワーク対応により、Go で x402 決済を実装する際の**フレームワーク選択の自由度**が大幅に向上した。既存のサービスに x402 を後付けする場合、フレームワーク移行なしに対応できることは導入障壁を下げる。

### Facilitator エラーメッセージ改善

v2.7.0 の **Facilitator エラーメッセージ改善**（登録スキームを含むエラーメッセージ改善）は小さな変更だが、**運用時のデバッグ体験** に直結する。

x402 では Facilitator（支払い検証者）が決済を承認・拒否する。Facilitator エラーが発生した場合、どのスキーム（EVM, SVM, Aptos 等）で問題が起きたかが分かることで、マルチチェーン環境での問題特定が容易になる。

### Go v2.6.0 の基盤——ERC20 Gas Sponsorship と指数バックオフ

v2.7.0 の前段として、v2.6.0 では重要な変更が入っていた：

| 変更 | Issue/PR | 詳細 |
|------|---------|------|
| Permit2 E2E テスト修正 | - | TypeScript サーバーの Permit2 E2E テスト修正 |
| ルート設定バリデーション | #1364 | 初期化時のルート設定検証 |
| 指数バックオフリトライ | #1357 | `GetSupported` の 429 レスポンスに対するリトライ |
| ERC20 Gas Sponsorship | #1336 | ガススポンサーシップ拡張実装 |
| Memo Instruction & SVM スキーム | - | Memo インストラクションと SVM スキーム仕様改善 |

**指数バックオフリトライ** (#1357) は、Facilitator の負荷制御（429 Too Many Requests）への対応だ。マルチチェーン環境では複数の Facilitator と通信するため、レート制限への適切な対応は必須だ。

**ERC20 Gas Sponsorship** (#1336) は Go v2.6.0 と TypeScript Core v2.7.0 で同時に入っており、言語間での機能同期が行われている。

## TypeScript Core v2.8.0：Aptos 対応とマルチチェーン拡張

### Aptos サポートの戦略的位置づけ

TypeScript Core v2.8.0 での **Aptos ブロックチェーンサポート追加** は、x402 のマルチチェーン戦略における重要なステップだ。

x402 が現在サポートするブロックチェーンを整理すると：

| チェーン | カテゴリ | 対応バージョン |
|--------|---------|--------------|
| Ethereum / EVM 互換チェーン | EVM | 初期から |
| Solana / SVM 互換チェーン | SVM | v2.6.0 以前 |
| Aptos | Move VM | TypeScript v2.8.0 |
| Polygon メインネット | EVM | 未リリース (#1564) |
| Stellar | Stellar Protocol | 未リリース（ドキュメント追加済み） |

Aptos は Move 言語で書かれたスマートコントラクトを実行する。Move は **リソース中心の安全な型システム** が特徴で、金融アプリケーションのセキュリティを言語レベルで強化する設計思想を持つ。x402 がサポートする理由は明確だ。

### EVM から SVM、そして Move VM へ

x402 の対応チェーン拡大は、単純な「チェーン数増加」ではない。**実行モデルの多様化** という観点で見ると重要だ：

```
x402 マルチチェーン対応の進化:

EVM (Ethereum 互換)
  |-- exact_evm スキーム
  |-- ERC-7710 サポート (TypeScript v2.7.0)
  |-- ERC20 Gas Sponsorship (#1336)
  |-- Polygon メインネット (未リリース, #1564)

SVM (Solana 互換)
  |-- Memo Instruction (Go v2.6.0)
  |-- SVM スキーム仕様改善

Move VM (Aptos)
  |-- Aptos サポート (TypeScript v2.8.0)

Stellar
  |-- ドキュメント追加済み (未リリース)
```

Legend / 凡例:

- EVM: Ethereum Virtual Machine — Solidity スマートコントラクト実行環境
- SVM: Solana Virtual Machine — Rust/BPF ベースの高速実行環境
- Move VM: Aptos/Sui で使われる Move 言語の実行環境
- Stellar: 送金特化型ブロックチェーンプロトコル

### `upto` パラメータの設計思想

TypeScript v2.8.0 の `upto` パラメータは、**支払い上限を指定する** 機能だ。エージェント間決済では、エージェントが自律的に支払い判断を行うため、**予算上限の設定** は必須のセキュリティ機能だ。

`upto` パラメータなしでは、エージェントが誤動作した場合に意図しない高額決済が発生するリスクがある。「支払っていいのは最大 X ドルまで」という制約を API レベルで強制できることは、**エージェント決済の安全な自律化** という設計思想を体現する。

## TypeScript Core v2.7.0 の変更——ERC-7710 と Permit2 の完成

TypeScript Core v2.8.0 の前の v2.7.0 では、高度な EVM 機能が追加されていた：

| 変更 | Issue/PR | 詳細 |
|------|---------|------|
| Permit2 シミュレーション | - | 実際の決済前の検証 |
| ERC-7710 サポート | - | exact_evm スキームでの委任可能な権限 |
| ERC20 Gas Sponsorship | #1328 | ガススポンサーシップ実装 |
| PAYMENT-RESPONSE ヘッダー | #1128 | 決済失敗レスポンスへのヘッダー追加 |
| Permit2 アップグレード | #1325 | 最新コントラクト状態への更新 |

**ERC-7710** は「委任可能な権限（delegatable permissions）」の標準だ。ERC-7710 サポートにより、エージェントが別のエージェントや人間から権限を委譲してもらい、その権限で決済を行うシナリオが可能になる。これは **エージェント間の権限委譲チェーン** という将来の分散エージェントシステムの重要な基盤だ。

## 3 言語 SDK の並行進化——2026-03-26 時点

x402 の 3 言語 SDK は異なる速度と優先順位で進化している：

| 言語 | 最新バージョン | 直近の主要変更 | 特徴 |
|------|-------------|--------------|------|
| Go | v2.7.0 | Fastify/Echo アダプター | フレームワーク多様性 |
| Python | v2.5.0 | Permit2 & Gas Sponsorship | サーバーサイド決済 |
| TypeScript Core | v2.8.0 | Aptos サポート, upto パラメータ | マルチチェーン先行 |

TypeScript が新チェーン対応（Aptos）を先行して実装し、Go がフレームワーク多様性を広げ、Python がサーバーサイドの決済機能を充実させる——**言語ごとの役割分担** が見える。

この分業は x402 エコシステムの健全さを示している。全言語が全機能を同時に実装するのではなく、言語の特性と主要ユースケースに応じた優先順位で開発が進んでいる。

## エコシステムパートナーの拡大——実用段階の証拠

x402 のエコシステムパートナーには新規追加が続いている：

- **Tollbooth**: OSS x402 API ゲートウェイ（既存 API への x402 後付け）
- **WalletIQ**: ウォレット管理
- **Laso Finance**: 金融サービス
- **xpay Facilitator**: 独立 Facilitator 実装
- **DJD Agent Score**: エージェント信用スコア
- **QuantumShield API**: API セキュリティ
- **RelAI Facilitator**: Facilitator 実装
- **AsterPay**: 決済処理
- **Agnic.AI**: AI 決済統合

**Tollbooth** の存在は特に意味深い。OSS の x402 API ゲートウェイが生まれたことは、x402 が **プロトコル採用のエコシステム** を形成し始めたことを示す。プロトコルが成熟すると、周辺ツールが生まれる——これは HTTP エコシステムが Nginx や Apache を生んだプロセスと同じ構造だ。

## 未リリースの変更——次の進化方向

x402 の未リリース変更群は次の方向性を示す：

| 変更 | Issue/PR | 意味 |
|------|---------|------|
| Signed Offer & Receipt Extension | #935 | 決済の証跡管理標準化 |
| Express スタイルルートパラメータ | #1313 | 動的ルートマッチング |
| Polygon メインネット | #1564 | EVM チェーン拡大 |
| Stellar サポート | - | 非 EVM チェーン拡大 |

**Signed Offer & Receipt Extension** (#935) は x402 の次の大きな変化かもしれない。「署名付きオファーとレシート」が標準化されると、エージェント間決済の **監査可能性と不可否認性** が確保される。エンタープライズ採用に向けた重要な要件だ。

## AP2 との連携——x402 の位置づけ

AP2 (Agent Payments Protocol、Google Agentic Commerce) は x402 payment method を統合している（Python サンプル）。AP2 v0.1.0（2025-09-16）のパートナーには Solana、Tether、OKX が含まれており、x402 が EVM を超えてマルチチェーン展開することと整合する。

x402 Go v2.7.0 の Fastify/Echo アダプターは、AP2 のサーバーサイド統合が Go フレームワークを使う場合の選択肢を広げる。

## まとめ

x402 Go v2.7.0 の Fastify/Echo アダプターと TypeScript Core v2.8.0 の Aptos サポートは、**x402 がマルチチェーン・マルチフレームワークの実用段階に到達した** ことを示している。EVM（Ethereum 互換）から SVM（Solana 互換）、そして Move VM（Aptos）への対応拡大は、特定ブロックチェーンへの依存から解放された**ブロックチェーン非依存の決済プロトコル**という設計思想の実現だ。

3 言語 SDK（Go v2.7.0、Python v2.5.0、TypeScript v2.8.0）の分業体制、エコシステムパートナーの拡大（Tollbooth、WalletIQ、xpay Facilitator 等）、Signed Offer & Receipt (#935)・Polygon (#1564)・Stellar という未リリース変更——これらが揃うことで、x402 は 2026-03-26 時点で **エージェント間インターネットネイティブ決済の実用インフラ** としての地位を確立しつつある。

## 参考リンク

- [x402 Protocol](https://github.com/coinbase/x402)
- [AP2 Protocol](https://github.com/google-agentic-commerce/AP2)
- [AG-UI Protocol](https://github.com/ag-ui-protocol/ag-ui)
- [ADK Python](https://github.com/google/adk-python)
