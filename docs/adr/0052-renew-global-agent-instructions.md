# 0052. 全エージェント共通の指示を刷新する（Go優先、fake/、core/shell設計、Plain Language）

**Date:** 2026-10-09
**Status:** Proposed
**ID:** ADR-0052
**Title:** 全エージェント共通の指示を刷新する（Go優先、fake/、core/shell設計、Plain Language）
**Decided-date:** none
**Decision-maker:** Hiroto N.
**Decision-maker-contact:** @hironow
**Author:** Claude Code（owner session）
**Author-contact:** @hironow
**Deadline:** 2026-10-16
**Supersedes:** none
**Superseded-by:** none
**Related:** [ADR-0044](0044-python-toolchain-uv-ruff-ty.md)、[ADR-0051](0051-adopt-decision-queue-for-new-records.md)、[base](../../ROOT_AGENTS.md)、[設計spoke](../../ROOT_AGENTS_docs_agents_core-shell-ports.md)
**Consultation-trace:** [公開PR #463](https://github.com/hironow/dotfiles/pull/463)

## やさしい説明

全エージェントに配る指示を、次の8点で書き換える。
新しいコードはGoで書き、1つのバイナリでどの端末でも動かす。
外部サービスには`fake/`の代役を用意し、テストやローカル実行で本物を誤って呼ばないようにする。
指示の文章はすべて、誰でも一度で読めるPlain Languageにする。

## Context

これまでの指示は「サービスはGo、ツールはPython」という前提で書かれていた。
テストはルートの`tests/`に置き、`tests/unit/`などの決まった配置に従うよう求めていた。
外部サービスの扱いはmockの方針だけで、本物を誤って呼ぶ事故を防ぐ仕組みは書かれていなかった。
設計の原則（純粋な処理と副作用の分離、外部との境界）と命名の規則もなかった。
文章は長い文や受け身が多く、読み手が一度で理解しにくかった。

2026-10-09、所有者は次の8点の刷新を指示した。

1. `tests/`の配置を求める指示をなくす。
2. 外部サービスのfakeを`fake/`に置き、内部の動作確認とテストを独立させ、重大な事故を防ぐ。
3. Functional Core / Imperative Shell（Google Testing Blog、2025-10）とHexagonal Architecture（Cockburn）に従う。
4. Tidy First、TDD、Red-Green-Refactor、YAGNI、SOLID、KISS、DRYに従う。
5. 依存を最小にし、言語公式の標準ライブラリを最新の機能まで使う。
6. 複数の端末で動かすため、最新のGoでバイナリを作る。Python、TypeScript、RubyではなくGoかRustを選ぶ。
7. Managerのような汎用名を避け、具体的な名前を付ける。
8. どの言語でもPlain Languageで書く。

同じ会話で、所有者は次の点も決めた。
英語で書く。
既存のPythonとTypeScriptの規則（uv、ruff、ty、bunだけを使う）は既存コードのために残す。
e2eで本物の依存だけを使う原則は残す。
`templates/agent-baseline/`の修正は別のPRで行う。

## Decision

1. 新しいサービス、CLI、ツールは最新の安定版Goで書き、OSとCPUごとに1つのバイナリで配る。Goが合わない場合（GCを許せない、メモリが厳しい、WASM、既存のRustコード）だけRustを使う。
2. 既存のPythonとTypeScriptの規則は、既存コードのために残す（ADR-0044は変えない）。
3. テストの種類は、置き場所ではなく何に触れるかで決める。テストのディレクトリと配置は指定しない。
4. 外部サービスごとに、メモリ上で動くfakeを`fake/`に置く。テストとローカル実行ではfakeを既定にする。本物のadapterは明示した設定でだけ使い、本番の接続先なら起動を拒む。本番ではfakeが1つでも組み込まれていれば起動を拒む。fakeと本物は同じ契約テストで確かめる。
5. 業務ロジックは値だけを受け取って値を返す純粋なcoreにし、I/Oはshellが目的ごとに名付けたportを通して行う。
6. Tidy First、TDD、YAGNI、KISS、DRY、SOLID、標準ライブラリ優先、具体的な命名を共通の規則にする。
7. 指示の文章は、すべてPlain Languageで書く。

## Options Considered

- **A) 8点をすべて指示に反映する（この案）**：新しいコードの言語、設計、テスト、文章の書き方が1つにそろう。既存のPythonやシェルの手順例は、範囲を明記して残す。
- **B) 文章の書き直し（8）だけ行う**：変更は小さい。ただし所有者が求めた設計と言語の方針が指示に入らない。
- **C) Pythonの規則も外し、Go/Rustだけを書く**：指示は短くなる。既存のPythonコードとhookの前提が説明されなくなる。

## Consequences

- **Positive**：新しいコードが1つのバイナリとして全端末で動く。fakeを既定にするので、テストやローカル実行から本物のサービスを誤って呼ばない。純粋なcoreはfakeもmockもなしでテストできる。
- **Negative**：Pythonが速い場面でもGoで書く手間が増える。fakeと契約テストを保守する手間が増える。`templates/agent-baseline/`は、e2eのSemgrep ruleとrecipeが`tests/e2e/`に固定されたままなので、別のPRで直すまで新しい指示と食い違う。
- **Neutral**：dotfiles自身の`tests/`は、リポジトリ側のCLAUDE.mdが決めるので、この決定では変えない。

## 他のDRとの照合

既存のADR 50件の題名と状態を確認した。
ADR-0044（Pythonの道具はuv、ruff、ty）とは矛盾しない。既存のPythonコードに引き続き適用する。
ADR-0047とADR-0049（rtk、headroom）のspokeは、文章をPlain Languageにしただけで、規則は変えていない。
ADR-0051の決裁待ち一覧の手順に従い、この記録を決裁待ちとして登録する。

## 裁定・merge前の停止条件

- 所有者がPR #463で裁定するまでmergeしない。
- 裁定後は、この記録の状態、決裁待ち一覧の行、ADR索引を同じ変更で更新する（ADR-0051）。

## 反転記録 (Reversal)

none（既存のAccepted ADRを置き換えない。）
