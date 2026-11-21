# 業界慣行との比較（Business Gaps）

## 結論

1. **コピー配置の状態永続化（質問 1）は業界で回答済み**: chezmoi は各ターゲットを原子的リネームで書き込み、永続状態 DB（`chezmoistate.boltdb`）で直前の書き込み状態を追跡して外部変更を検知する。`scripts/skills_lock.py#place` も項目ごとの原子的 `_save_state` に修正し、業界標準に揃えた。
2. **単一ホーム内の世代分裂防止（質問 2）は業界で回答済み**: NixOS / Home Manager / Ansible のいずれも、ファイルシステムへの部分適用後に任意の変更を自動ロールバックする仕組みは持たず、事前検証や失敗しやすい処理の先行実行で分裂を防ぐ。`scripts/sync_agents.py#sync_mode` も `hook_session.apply_home` をファイル書き込みより先に実行する形へ修正した。
3. **複数ホーム間の部分失敗方針（質問 3）は空白（運用判断）**: Ansible は既定で健全ホストを継続しつつ `any_errors_fatal: true` で全停止も選べるが、全ホスト一括の自動ロールバックは標準機能にない。複数エージェントホーム間で一部停止したときに継続するか全停止するかは運用者の選択である。
4. **ADR 全廃とコード証明への一本化（質問 4）は空白（独自方針）**: ThoughtWorks の進化アーキテクチャ（Fitness Functions）では、適合度関数で規則の遵守を機械検証しつつ ADR に人間向けの意思決定背景を残す併用が主流である。ADR を廃止してコード証明＋git 履歴へ一本化する運用には確立された業界標準がない。

## 調査方法と信頼性

- **調査日**: 2026-11-21
- **対象領域**: dotfiles 管理ツール（chezmoi）、宣言的環境管理（NixOS / Home Manager）、マルチホスト構成管理（Ansible）、進化的アーキテクチャ（ThoughtWorks Fitness Functions）
- **一次情報と二次情報の区別**: 各ツールの公式ドキュメント（chezmoi.io, nixos.org, home-manager.dev, docs.ansible.com, thoughtworks.com）の検索サマリーと一次URLに基づく。各ページの全文精読ではなく該当節の仕様確認に留めており、統計的な障害頻度データは存在しない。

## 質問ごとの分類と根拠

全質問の一覧と分類カウントは [docs/generated/questions.md](./generated/questions.md) を参照する。

| 領域・番号 | 分類 | 業界の実態と根拠 | 主な出典 |
|---|---|---|---|
| 配布・同期 #1（`skills_lock.py` 項目別永続化） | 回答済み | chezmoi は全ファイル・シンボリックリンクを同一ディレクトリ内の一時ファイル経由で原子的リネームし、`chezmoistate.boltdb` に各エントリの書き込み状態を保持して外部編集を検知する。バッチ末尾一括保存は途中終了で不整合を生むため避けられる。 | <https://www.chezmoi.io/user-guide/frequently-asked-questions/design/> , <https://www.chezmoi.io/reference/command-line-flags/global/> |
| 配布・同期 #2（`sync_agents.py` 停止時のファイル巻き戻し） | 回答済み | Home Manager のアクティベーションや Ansible のタスク実行は、部分適用後のファイルシステム変更を自動ロールバックしない。代わりに失敗し得るチェックや切り替えを先に通し、失敗時は後続の適用を止める設計をとる。 | <https://nixos.org/manual/nixos/stable/> , <https://nix-community.github.io/home-manager/> |
| 配布・同期 #3（複数ホーム同期の一部停止方針） | 空白 | Ansible の既定は「失敗ホストのみ停止し健全ホストは継続」だが、`any_errors_fatal: true` や `max_fail_percentage` で全停止にも切り替えられる。一方、完了済みホストを含めた一括ロールバックは標準機構がなく、運用設計に委ねられる。 | <https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_error_handling.html> |
| 不変条件 #1（ADR 全廃と git 履歴委譲） | 空白 | ThoughtWorks の Fitness Functions は「ドキュメントはデリバリーに参加しない」として機械検証を重視するが、ADR は意思決定の文脈（Why）を残すために併用するのが一般的である。ADR を完全に消去してコード証明＋git 履歴へ寄せるかは組織・個人の方針判断となる。 | <https://www.thoughtworks.com/insights/articles/fitness-function-driven-development> |

## 分類ごとの整理

### 業界で回答済み（Answered）

- **質問 1・質問 2**: いずれも構成管理ツールで確立された設計解が存在し、今回の修正で `scripts/skills_lock.py`（項目ごとの原子的 `_save_state`）および `scripts/sync_agents.py`（`apply_home` 先行実行）を実装・ユニットテスト化して解消した。

### 業界で問われない（Not asked）

- 該当なし（全 4 問とも構成管理・アーキテクチャ運用で実在する論点）。

### 空白（Gap）

- **質問 3（複数ホーム間の一貫性 vs 可用性）**: 一部のエージェントホーム（例: `work-a`）が停止した際、他の正常なホーム（`claude`, `codex`）の更新を止めない現行方針（Ansible 既定と同じ）を維持するか、全ホーム同期の厳密一致を優先して fail-fast にするか。
- **質問 4（意思決定の「Why」の保持場所）**: 機械検証可能な不変条件（What）は Lean/Quint とテストで完全に SSOT 化できるが、過去の却下案や経緯（Why）を git コミットメッセージと PR 本文のみに委ねる運用コストを許容するか。

## 形式手法では埋められない空白

- 複数ホーム間で「一部停止時に他ホームを継続するか全停止するか」の優先度（可用性 vs 一貫性の価値判断）。
- ADR を撤廃した後に、将来の自分や別エージェントが過去の却下理由（Why）を git 履歴から辿るコストを許容できるかという運用判断。
- ネットワーク障害や外部 CLI（`bunx skills`）の仕様変更など、モデル外の外部要因に対するリトライ・フォールバック UX。

## 業務・運用判断の一覧

| 判断 | 利用者（運用者）価値 | 形式手法の役割 |
|---|---|---|
| コピー配置の項目別・原子的状態永続化（実装済み） | 高：途中中断後の孤児化（更新停止）を防ぐ | 現行コードの反例と修正後の全状態成立を確認（対照実験は未実施） |
| `sync_mode` での `apply_home` 先行確定（実装済み） | 高：単一ホーム内の指示とフックの世代分裂を防ぐ | 現行コードの反例と修正後の全状態成立を確認（対照実験は未実施） |
| 複数ホーム同期の部分停止時ポリシー（継続 vs 全停止） | 中：障害時の影響範囲と復旧手順の明確化 | トレードオフの到達可能性を反例で可視化するが、選択自体は人間が行う |
| ADR 廃止後の「Why」の記録先（git/PR のみ vs 要約保持） | 中：将来の変更時に同じ議論を繰り返さない | 形式手法は「What（不変条件）」を守るが、「Why（経緯）」の要否は決められない |

## 主な出典

- chezmoi Design FAQ（原子的書き込み・永続状態）: <https://www.chezmoi.io/user-guide/frequently-asked-questions/design/>
- chezmoi Global Flags（`--persistent-state`, `chezmoistate.boltdb`）: <https://www.chezmoi.io/reference/command-line-flags/global/>
- NixOS Manual（`nixos-rebuild switch` / `test` / `--rollback`）: <https://nixos.org/manual/nixos/stable/>
- Home Manager Manual（世代管理とアクティベーション）: <https://nix-community.github.io/home-manager/>
- Ansible Documentation（Error handling in playbooks: `any_errors_fatal`, `max_fail_percentage`, `block`/`rescue`）: <https://docs.ansible.com/ansible/latest/playbook_guide/playbooks_error_handling.html>
- ThoughtWorks（Fitness Function-Driven Development）: <https://www.thoughtworks.com/insights/articles/fitness-function-driven-development>
