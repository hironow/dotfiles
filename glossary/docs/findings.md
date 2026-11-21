# 検証結果と限界（Findings）

## 全体の結論

1. 配布・同期・スキル配置の修正前コード（`scripts/skills_lock.py#place`, `scripts/sync_agents.py#sync_mode`）を Quint でモデル化した結果、途中中断と外部ストア更新の組み合わせにより **未記録コピーの孤児化（`kept`）** と **単一ホーム内の指示/フック世代分裂** が到達可能な反例として確認された。
2. 両反例をそれぞれユニットテストで再現した上で、項目ごとの原子的 `_save_state` と `apply_home` 先行確定を実装し、修正後の現行コード（`codeAsIs`）では上記 2 性質が全到達状態（104 状態）で成り立つことを確認した。一方で複数ホーム間の世代一致は依然として反例を持つ。
3. 旧 ADR 群のうち現役の中核規則（`hironow/skills` 優先則、読み取り専用 Git フック、秘密を要する MCP の自動登録禁止など）を Lean 4 の証明とコードアンカーで固定し、人間向けドキュメントおよび `docs/adr/` を撤去した。
4. 業界慣行との比較（Tier 2）を [business-gaps.md](./business-gaps.md) にまとめた。対照実験（Tier 3）は未実施のため、本文書の所見はすべて「確認した（confirmed）」として扱い、形式手法固有の発見とは主張しない。

## 停止の場面（配布・同期・スキル配置）

対象モデル: `Spec/deploy_sync.qnt`（ホーム数 2: `h1`, `h2`、ストア世代 2: `1 -> 2`）。

| 設計 | `noOrphanedCopy`（未記録コピーが `kept` にならない） | `noSplitHome`（単一ホーム内で指示とフックが分裂しない） | `allHomesConsistent`（全ホームの世代が一致する） | 状態数（TLC） |
|---|---|---|---|---|
| `preFix`（修正前コード） | 反例あり（`orphanedCopyTest`・実コードで再現済み） | 反例あり（`splitHomeTest`・実コードで再現済み） | 反例あり | シミュレータ / スクリプトで反例確認 |
| `codeAsIs`（修正後の現行コード: 項目別永続化＋`apply_home` 先行確定） | 証明済み | 証明済み | 反例あり | 104 状態（全状態探索） |

- **現行コードの反例 1（`codeAsIs.noOrphanedCopy`）**:
  `placeCopy("h1") -> stopRun -> storeUpdates -> recover -> rePlace("h1")` の順で遷移すると、`h1` のコピーが `.skills-lock-state.json` 未記録のまま残り、ストア更新後の再実行で `kept` に分類される。
- **現行コードの反例 2（`codeAsIs.noSplitHome`）**:
  `syncWriteFiles("h1") -> stopRun` で `fileVer["h1"] == 2` かつ `hookVer["h1"] == 1` となり、同一ホーム内で指示ファイルとフック登録の世代が分裂する。
- **提案設計の動作確認（`guarded.perItemRecoveryTest`）**:
  同じ中断・ストア更新シーケンスでも、永続化済みの状態により `rePlace("h1")` が正常に世代 2 へ更新することを確認した。

## リポジトリ不変条件（旧 ADR 群のコード証明化）

対象ファイル: `Glossary/Architecture.lean`（Lean 4、標準公理のみ。`Audit.lean` で確認済み）。

- `selfSource_outranks_thirdParty`: `scripts/skills_lock.py#_outranks` の規則の転記において、`hironow/skills` 由来スキルは `resolvedBy` によらず第三者スキルに必ず優先し、逆転しないことを証明。
- `prek_hooks_readonly_no_prepush`: `.pre-commit-config.yaml` に登録された 9 フックの転記がすべて読み取り専用であり `pre-push` ステージを含まないことを証明。
- `mcp_secret_never_auto_registered`: `scripts/agent_mcp.py` の振り分け規則の転記において、秘密を要する MCP サーバは自動登録されないことを証明。
- 全用語がリポジトリ内の実コードへのアンカーを持ち、`just glossary anchor-check` で実在性を継続検証する。

## 対照実験（Tier 3）

**未実施**（`Glossary/Registry.lean` に `.skipped` を宣言済み）。
ツールなしのレビューとの比較を行っていないため、「形式手法によって初めて見つかった」という表現は使用しない。

## 未決定の質問一覧

全質問の番号・根拠・分類は生成ドキュメント [docs/generated/questions.md](./generated/questions.md) を正とする。Tier 2（業界調査）は未実施のため、全件が未調査である。

## 限界

- **モデル規模**: `Spec/deploy_sync.qnt` は 2 ホーム・2 世代に限定した有限モデルである（実環境は 7 ホーム・複数スキル）。
- **モデル外の範囲**: ディスク満杯・シンボリックリンク権限・並行実行中のプロセス競合・Windows 固有のファイルロックはモデルに含めていない。
- **反例の実装再現**: `codeAsIs` で得た反例トレースはモデル上の仮説であり、実スクリプトに対する結合テスト実行は未実施である。
- **ADR 全体の網羅範囲**: 本フェーズ（Phase 1）では現役の中核 ADR 群と配布・同期ドメインを優先して証明化した。残余の細目 ADR および `docs/` 削除に伴う既存テストの整合は Phase 2 で扱う。
