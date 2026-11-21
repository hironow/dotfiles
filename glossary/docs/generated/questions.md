<!-- 生成物。`just generate` が `Glossary/*.lean` から作る。手で編集しない。 -->

# 業務側への質問

判定が「未決定」の主張の一覧である。業務を知る人が決める。

## 配布・同期・スキル配置

<!-- questions: 3; with-counterexample: 3; outside-model: 0 -->
<!-- industry: classified: 3; researched: 3 -->

| # | 質問 | 用語 | 根拠 | 業界 |
|---|---|---|---|---|
| 1 | skills_lock.py のコピーモード配置で途中中断した場合、_save_state を項目ごとに永続化すべきか、それとも --force による手動復旧に委ねるか？ | 配置済みスキル, 配布・同期の中断, 診断と手動復旧 | 業務側への質問。空白を示す反例: `Spec/deploy_sync.qnt` `preFix.noOrphanedCopy` | 答えあり: chezmoi は各ターゲットを原子的リネームで書き込み永続状態 DB に記録するため、項目ごとの永続化が業界標準である |
| 2 | sync_agents.py で hook_session.apply_home が停止したとき、直前に書き込んだ指示ファイル（CLAUDE.md / AGENTS.md）をロールバックすべきか？ | 登録済みフック, エージェントホーム, 配布・同期の中断 | 業務側への質問。空白を示す反例: `Spec/deploy_sync.qnt` `preFix.noSplitHome` | 答えあり: NixOS や Home Manager や Ansible は部分適用後の自動ファイル巻き戻しを持たず、失敗しやすい処理を先行させて分裂を防ぐ |
| 3 | 複数ホーム同期で一部ホームだけ apply_home が停止したとき、完了済みホームを新世代のまま進める（現行の継続方針）か、全ホームを旧世代へ戻すべきか？ | エージェントホーム, 登録済みフック, 配布・同期の中断 | 業務側への質問。空白を示す反例: `Spec/deploy_sync.qnt` `codeAsIs.allHomesConsistent` | 空白: Ansible は既定で健全ホストを継続しつつ any_errors_fatal で全停止も選べ、一括ロールバックは標準機能になく運用選択が残る |

## リポジトリ不変条件（旧ADR群の証明化）

<!-- questions: 1; with-counterexample: 0; outside-model: 1 -->
<!-- industry: classified: 1; researched: 1 -->

| # | 質問 | 用語 | 根拠 | 業界 |
|---|---|---|---|---|
| 1 | 既存の Proposed 状態 ADR（0065 kernel-cve evidence-only、0085、0087）および退役済み Coder 関連 ADR（0002〜0013, 0045）は、docs/adr/ 削除後に git 履歴のみへ委ねてよいか？ | 読み取り専用 Git フック（prek）, 宣言済みリモート MCP 配布と秘密隔離 | 業務側への質問。モデルで示せない理由: 過去の経緯や未決裁 ADR を git 履歴のみに残すか否かは運用上の意思決定であり、状態機械モデルでは決定できない | 空白: ThoughtWorks の進化アーキテクチャでは適合度関数で規則を検証しつつ ADR に背景を残すのが主流であり、ADR 全廃と git 履歴委譲は標準がない |

