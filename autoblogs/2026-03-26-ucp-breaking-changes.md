---
title: "UCP の破壊的変更——Identity Linking リデザインと Authorization & Abuse Signals が示すエージェント商取引プロトコルの哲学転換"
date: 2026-03-26
tags: [ucp, commerce, identity, authorization, protocol, breaking-changes]
source: docs/changelogs.md
---

# UCP の破壊的変更——Identity Linking リデザインと Authorization & Abuse Signals が示すエージェント商取引プロトコルの哲学転換

Universal Commerce Protocol (UCP) は v2026-01-23 以降、2 つの重大な**破壊的変更**を経験している。**Identity Linking リデザイン**（メカニズムレジストリとケイパビリティ駆動スコープへの再設計）と **Authorization & Abuse Signals の形式化**（#203）だ。これらの変更は単なる仕様修正ではなく、**エージェントが商取引を自律的に実行する**時代に向けたプロトコル哲学の転換を示している。2026-03-26 時点での UCP の設計思想を分析する。

## UCP v2026-01-23 の起点——何を解決しようとしたか

### 基盤となる設計思想

UCP は v2026-01-23 で、以下の機能を確立した：

| 機能 | 詳細 | 意味 |
|------|------|------|
| リクエスト/レスポンス署名 | UCP プロトコルの暗号署名 | 商取引の改ざん防止 |
| Cart Capability (#73) | バスケット構築機能 | エージェントによる複数商品管理 |
| Context Intent フィールド | intent フィールド追加、非識別制約明確化 (#95) | プライバシーと意図の両立 |
| EC カラースキーム | 埋め込みチェックアウトのカスタマイズ (#157) | UI 統合の柔軟性 |
| ECP サポート | E-Commerce Connector Protocol 追加 | チェックアウトごとのトランスポート設定 |

**Context Intent フィールド**（#95）の「非識別制約明確化」は重要だ。エージェントが商品購入の「意図」をセラーに伝える際、購入者のプライバシー（非識別性）と取引の正当性確認の両立を仕様化している。これが後の Identity Linking リデザインへの前提条件だ。

## Identity Linking リデザイン——破壊的変更の解剖

### 旧設計の問題

旧来の Identity Linking は、購入者とセラー間の身元確認を**固定的なメカニズム**で実装していた。この設計の問題は、エージェントが代理購入を行う時代に顕在化する：

- エージェントが**複数のサービス**（ADK Python、LangGraph ベースエージェントなど）で動作する場合、身元確認メカニズムが固定だと相互運用性が失われる
- 身元確認の「スコープ」（どの情報をどの範囲で使うか）が静的で、ケイパビリティに基づいた動的制御ができない

### 新設計——メカニズムレジストリとケイパビリティ駆動スコープ

**メカニズムレジストリ**は、身元確認方式を動的に登録・選択できる仕組みだ。これは MCP の **Extensions フレームワーク**（SEP-2133, Final）と設計思想が対応する：

```
セラー（商取引エンドポイント）
    |
    | ケイパビリティネゴシエーション
    v
Identity Linking メカニズムレジストリ
    |
    +-- OIDC（OpenID Connect）
    +-- OAuth 2.0
    +-- カスタム企業認証
    +-- 将来のメカニズム（拡張可能）
    |
    | ケイパビリティ駆動スコープ選択
    v
エージェント（購入者代理）
```

Legend / 凡例:
- メカニズムレジストリ: 身元確認方式を動的に登録・管理するコンポーネント
- ケイパビリティ駆動スコープ: エージェントの能力に応じて最適な認証スコープを選択
- OIDC: OpenID Connect（MCP 2025-11-25 での OIDC / エンタープライズ管理認可と連携）

ADK Python v1.27.0 の **AuthProviderRegistry**（`CredentialManager` 内のプラガブル認証統合）と、UCP の Identity Linking メカニズムレジストリは**設計的に対応する**。どちらも「認証の抽象化と動的選択」という哲学を体現している。

### ケイパビリティ駆動スコープの実用的意味

旧来の「固定スコープ」から「ケイパビリティ駆動スコープ」への移行は、以下の変化をもたらす：

| 観点 | 旧設計（固定スコープ） | 新設計（ケイパビリティ駆動） |
|------|-------------------|----------------------|
| スコープ決定 | 事前設定された固定値 | エージェントのケイパビリティに基づいて動的選択 |
| 最小権限原則 | 実装が困難 | ケイパビリティに応じた自動的な最小スコープ選択 |
| 新認証方式対応 | メカニズム変更が必要 | レジストリへの追加のみ |
| マルチエージェント | 単一エージェント前提 | 複数エージェントの異なる権限を管理可能 |

ACP（Agentic Commerce Protocol）の **Capability Negotiation**（エージェントとセラー間の機能ネゴシエーション）と比較すると、UCP のケイパビリティ駆動スコープは**商取引に特化した認証ネゴシエーション**として機能する。

## Authorization & Abuse Signals（#203）——信頼の形式化

### なぜ「不正利用シグナル」が破壊的変更になったか

**Authorization & Abuse Signals の形式化**（#203）が破壊的変更として分類されることは、その本質的な意味を示している。

従来の UCP では、認可（Authorization）と不正利用検知（Abuse Detection）は実装者の裁量に委ねられていた。形式化により、これらが**プロトコルレベルの要件**になった。既存の実装は Abuse Signals フィールドを処理する機構を追加しなければならず、これが破壊的変更になる。

### Abuse Signals の設計思想

エージェントが代理購入を行う場合、セラーが直面するリスクは人間の購入者とは異なる：

| リスクカテゴリ | 詳細 | Abuse Signals での対応 |
|-------------|------|---------------------|
| ボット購入 | 大量自動注文 | レート制限シグナルの標準化 |
| プロンプトインジェクション | 悪意あるエージェント指示 | 購入意図の検証シグナル |
| 不正な委任 | 権限外エージェントによる代理 | 委任チェーンの検証 |
| 価格操作 | エージェントによる価格情報収集 | アクセスパターンシグナル |

ADK Python v1.27.3 の**任意モジュールインポート防止**や ADK JS の**パストラバーサル防止**（CWE-22、未リリース）が「エージェントフレームワーク内部のセキュリティ強化」だとすれば、UCP の Abuse Signals は「**エージェントと外部サービス間の通信のセキュリティ強化**」だ。両者は同じ脅威モデルへの異なるレイヤーでの対応を示している。

## v2026-01-23 以降の変更群——破壊的変更を含む設計の発展

### Embedded Link Delegation と Eligibility Claims

**Embedded Link Delegation**（埋め込みリンク委譲拡張）と **Eligibility Claims & Verification**（#250）（適格性主張と検証コントラクト）は、Identity Linking リデザインを補完する変更だ：

| 変更 | Issue | Identity Linking との関係 |
|------|-------|------------------------|
| Embedded Link Delegation | - | リンクを通じた権限委譲の形式化 |
| Eligibility Claims (#250) | #250 | 購入資格の主張と検証コントラクト |
| Catalog Search & Lookup (#55) | #55 | 商品発見と購入の統合フロー |
| Discount Capability (#246) | #246 | 割引適用の権限とスコープ |

**Eligibility Claims** は特に注目に値する。「エージェントが特定の商品を購入できる資格があるか」を検証する仕組みは、B2B 取引（法人契約価格での購入など）や年齢制限商品の購入代理において不可欠だ。

### `reverse_domain_name` の独立型化（#260）

**`reverse_domain_name` の独立型化**（#260、スタンドアロン型への昇格）は、UCP の型システム設計の哲学を示している。以前は他の型に埋め込まれていた `reverse_domain_name` が独立型になることで、**識別子の再利用性と一貫性**が向上する。

A2A v1.0.0 での **ID 形式簡素化**（複合 ID → 単純 UUID/リテラル、#1389）と方向性は逆だが、目的は同じだ——「識別子の扱いを明確に」という設計思想の現れだ。

## ACP との比較——エージェント商取引プロトコルの2つの哲学

UCP と ACP（Agentic Commerce Protocol, API Version 2026-01-30）は、どちらも「エージェントによる商取引」を扱うが、設計哲学が異なる。

| 観点 | UCP | ACP |
|------|-----|-----|
| 管理主体 | Anthropic | OpenAI & Stripe |
| 認証方式 | Identity Linking（メカニズムレジストリ） | OAuth 系統 |
| 不正利用対策 | Abuse Signals（形式化） | Webhook Signing Replay Protection（#160） |
| 割引 | Discount Capability (#246) | Discount Extension（初の ACP 拡張） |
| 支払い | x402 統合（AP2 経由） | Payment Handlers Framework（破壊的変更） |
| 意思決定単位 | ケイパビリティ駆動 | Extensions フレームワーク |
| 参加者 | Checkout.com | Wix.com, commercetools |

両者の**共通点**は「エージェントが関わる商取引を安全に実行するための構造化されたプロトコル」という目標だ。UCP が Identity Linking の動的化を進め、ACP が Payment Handlers の構造化を進める——それぞれ異なるアプローチで同じ問題を解いている。

## Checkout ID 非推奨化（#145）の設計的意味

**Checkout ID の非推奨化**（#145、update リクエストで `checkout_id` を `deprecated_required_to_omit` に）は、**後方互換性を保ちながら設計を移行する**UCP のアプローチを示す。

`deprecated_required_to_omit` という状態は「現在は省略することが要求されるが、以前は必須だった」という意味だ。これは ABI/API 互換性における「廃止予告」よりも強い——既存のクライアントが `checkout_id` を送ってくる場合に対応しながら、新規クライアントには送らないよう要求する段階的な移行だ。

A2A v1.0.0 での **`blocking` → `return_immediately`** フィールドリネーム（#1507）が即座の名前変更だったのに対し、UCP の Checkout ID 非推奨化は**より長い移行期間を設ける**設計選択を示している。これは商取引プロトコルの安定性要求がエージェント間通信プロトコルより高いことを反映している。

## UCP の進化が示す実用段階エージェント商取引の姿

UCP の v2026-01-23 以降の変更を整理すると、3 つの方向性が見える：

### 1. セキュリティと信頼の形式化

- Identity Linking リデザイン（動的認証）
- Authorization & Abuse Signals（#203）の形式化
- ACP の Webhook Signing Replay Protection（#160）との並走

### 2. 機能の段階的拡張

- Discount Capability (#246)
- Catalog Search & Lookup (#55)
- Eligibility Claims (#250)
- Warning Disclosure Contract

### 3. 型システムの精緻化

- `reverse_domain_name` 独立型化（#260）
- Checkout ID 非推奨化（#145）
- `available_instruments` 追加（#187）
- Totals Contract の形式化

この 3 方向が示すのは、**エージェント商取引が「実験的な概念」から「厳密に定義されたプロトコル」へと移行**しつつあるという事実だ。

## まとめ

UCP の Identity Linking リデザインと Authorization & Abuse Signals（#203）の形式化は、**エージェントが代理購入を安全に実行できる基盤の確立**という方向性を明確に示す。メカニズムレジストリによる動的な認証選択は、ADK Python v1.27.0 の AuthProviderRegistry と同じ「認証の抽象化」哲学を共有している。

Abuse Signals の形式化は、ADK Python v1.27.3 の任意モジュールインポート防止・ADK JS のパストラバーサル防止（CWE-22）・MCP-Apps の PDF Server HTTPS 必須化と同じ文脈——**エージェントが外部と接触する機会が増えるほど、セキュリティの形式化が不可欠になる**——に置かれる。

2026-03-26 時点で、UCP は商取引プロトコルとして**意味する段階**に入っている。Checkout.com のパートナー参加、Eligibility Claims (#250)、Discount Capability (#246) が揃うことで、エンタープライズグレードのエージェント商取引が現実の選択肢になってきた。

## 参考リンク

- [UCP Protocol](https://github.com/anthropics/UCP)
- [ACP Protocol](https://agenticcommerce.dev)
- [A2A Specification](https://github.com/a2aproject/A2A)
- [ADK Python](https://github.com/google/adk-python)
