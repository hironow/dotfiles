# Provable Glossary（`hironow/dotfiles`）

`hironow/dotfiles` の用語・アーキテクチャ不変条件（旧 ADR 群）・配布同期の状態機械を Lean 4 と Quint で機械検証し、ドキュメントを生成するプロジェクト。

- **開始点**: B（既存コードから構築。参照コミット: `064a35c9`、その後反例 2 件を実装修正済み）
- **到達 Tier**: Tier 2（必須項目＋業界慣行との比較完了。Tier 3 の対照実験およびポリシー草案は未実施）
- **判定の 3 区分**: 証明済み（Lean 証明または Quint + TLC 全状態検査）、反例あり（反証または到達可能な反例）、未決定（業務・運用判断が必要な質問）
- **件数と一覧**: [docs/generated/summary.md](./docs/generated/summary.md)

## 役割と停止の場面

共有役割の対応表と停止の場面の検証結果は [docs/generated/roles.md](./docs/generated/roles.md) に自動生成される。

- **期限（Deadline）・供給の取り消し（Supply cancellation）・振替（Reallocation）**: `dotfiles` の配布・同期ドメインには該当する仕組みがコード上に存在しないため、意図的に未タグ（`なし`）としている。
- **対象コード**: `scripts/sync_agents.py`, `scripts/agent_hook_sync.py`, `scripts/agent_hook_wiring.py`, `scripts/skills_lock.py`, `scripts/deploy.sh`, `scripts/agent_mcp.py`, `scripts/doctor.sh`, `config/mise/config.toml`, `config/mise/image-tools.toml`, `bunfig.toml`, `.pre-commit-config.yaml`, `dump/harness/mcp-servers.json`, `emulator/compose.yaml`, `telemetry/compose.yaml`。

## 確認できたこと

1. **コピー配置の中断による孤児化（現行コードの反例）**: `scripts/skills_lock.py#place` は全ループ終了後にのみ `_save_state` を呼ぶため、コピー配置途中で中断し外部の `bunx skills update` がストアを進めると、次回 `place` が未記録コピーを利用者編集（`kept`）と誤認して更新を止める。
2. **ホーム内世代分裂（現行コードの反例）**: `scripts/sync_agents.py#sync_mode` は `hook_session.apply_home` より前に指示ファイルを書き込むため、`apply_home` が中断すると同一ホーム内で指示ファイル（新世代）とフック登録（旧世代）が分裂する。
3. **項目ごとの永続化とホーム単位確定による解消（提案設計の証明）**: `_swap_in` ごとの即時永続化とホーム単位の原子的確定により、上記 2 つの不変条件はモデル上の全到達状態（104 状態）で成り立つ。
4. **複数ホーム間の世代ずれ（提案設計の反例）**: 単一ホームを原子的にしても、複数ホーム同期の途中で中断すれば完了済みホームと未完了ホームで世代が分かれる。
5. **主要不変条件のコードアンカー化**: 旧 ADR 群の中核規則（`hironow/skills` 優先則、読み取り専用 Git フック、秘密を要する MCP の自動登録禁止、mise/Python/Bun/Podman/otel-lgtm/4 層設定）をコードアンカーと Lean 証明で固定した。

## 読む順番

1. [docs/generated/summary.md](./docs/generated/summary.md) — 用語・主張・判定の集計
2. [docs/generated/roles.md](./docs/generated/roles.md) — 共有役割の対応と停止の場面
3. [docs/generated/glossary.md](./docs/generated/glossary.md) — 用語定義とコードアンカー
4. [docs/generated/claims.md](./docs/generated/claims.md) — 全主張と証拠
5. [docs/generated/questions.md](./docs/generated/questions.md) — 未決定の質問一覧
6. [docs/findings.md](./docs/findings.md) — モデル検査の比較表・結果・限界
7. [docs/business-gaps.md](./docs/business-gaps.md) — 業界慣行との比較と運用判断の空白

## 使い方

リポジトリルートから実行する。

```sh
just glossary setup      # 外部 Lean パッケージが無い場合は何もしない
just glossary generate   # Glossary/*.lean から glossary/docs/generated/*.md を生成
just glossary check      # Lean 証明・stop/question/control 検査・Quint/TLC・生成物一致・コードアンカー検査
```

## 手書きと生成物、および保護機構

- **手書き**: `Glossary/DeploySync.lean`, `Glossary/Architecture.lean`, `Glossary/Registry.lean`, `Spec/deploy_sync.qnt`, `Spec/tests.txt`, `README.md`, `docs/findings.md`
- **自動生成（編集禁止）**: `docs/generated/*.md`（`just glossary generate` のみが書き換える）
- **保護機構**:
  1. `just glossary check`（`generated-check` / `anchor-check`）が生成物の改変やコードアンカー切れを拒否する。
  2. Claude Code フック（`.claude/hooks/protect_generated.py`）が `docs/generated/` への直接編集を遮断する。
  3. テンプレート由来の保護検証スクリプト（`check_protection.py`）で上記遮断とゲート動作を検証できる。

## 構成

- `Glossary/` — Lean 4 の用語集・不変条件・証明（`DeploySync.lean`, `Architecture.lean`）
- `Spec/` — Quint 状態機械モデルとスクリプト化テスト（`deploy_sync.qnt`, `tests.txt`）
- `docs/generated/` — 生成ドキュメント（編集禁止）
- `docs/findings.md` — 検証結果と限界

## 限界

- Tier 1 のみ完了しており、Tier 2（業界慣行との比較）および Tier 3（対照実験・ポリシー草案）は未実施。したがって「形式手法だけが発見した」という主張は行わない。
- `Spec/deploy_sync.qnt` は 2 ホーム・2 世代の有限モデルであり、ファイルシステムの部分書き込み・並行実行・Windows 固有の権限エラーは抽象化している。
- 現行コードの反例はモデル上の反例であり、実スクリプトに対する再現テスト実行は別途行う必要がある。
- `Glossary/Architecture.lean` の Lean 定理はコード規則の転記に対する証明であり、実装との乖離はコードアンカー（`anchor-check`）および既存のユニットテストで監視する。
