<!-- 生成物。`just generate` が `Glossary/*.lean` から作る。手で編集しない。 -->

# 役割と停止の場面

共通の役割を、各用語に付けた役割から一覧にする。停止の場面について各用語集が宣言したことも載せる。宣言は `just check` (stop-check) が確かめる。

## 配布・同期・スキル配置

<!-- stop-scene: ok; modelled -->
<!-- roles-tagged: 7 -->

停止の場面: 検査モデルにした。支える主張を下に載せる。

| 役割 | 用語 |
|---|---|
| 資源 (Resource) | エージェントホーム |
| 仮確保 (Hold) | 切替ロックとジャーナル |
| 外部の確認 (External confirmation) | 外部スキルストア反映 |
| 権利 (Entitlement) | 配置済みスキル, 登録済みフック |
| 停止 (Stop) | 配布・同期の中断 |
| 計画停止 (Planned stop) | プレビュー実行 |
| 期限 (Deadline) | なし |
| 代わりの経路 (Fallback channel) | 診断と手動復旧 |
| 供給の取り消し (Supply cancellation) | なし |
| 振替 (Reallocation) | なし |

### 停止についての主張

| 判定 | 主張 | 用語 | 証拠 |
|---|---|---|---|
| 反例あり | 修正前設計（scripts/skills_lock.py#place のループ末尾一括 _save_state）では、コピー配置途中で中断して外部ストアが更新されても、dotfiles が配置したコピーが未記録の孤児（kept）にならない | 配置済みスキル, 外部スキルストア反映, 配布・同期の中断 | Quint 反例: `Spec/deploy_sync.qnt` `preFix.noOrphanedCopy` |
| 反例あり | 修正前設計（scripts/sync_agents.py#sync_mode のファイル先行書き込み）では、apply_home が中断してもホーム内の指示ファイル世代とフック登録世代が分裂しない | 登録済みフック, エージェントホーム, 配布・同期の中断 | Quint 反例: `Spec/deploy_sync.qnt` `preFix.noSplitHome` |
| 証明済み | 現行コード（_swap_in ごとに原子的 _save_state で .skills-lock-state.json を永続化）では、配布中断と外部ストア更新を経ても未記録の孤児コピー（kept）が生じない | 配置済みスキル, 外部スキルストア反映, 配布・同期の中断 | Quint + TLC 全状態: `Spec/deploy_sync.qnt` `codeAsIs.noOrphanedCopy` |
| 証明済み | 現行コード（sync_mode で apply_home を先行確定し停止時は書き込みを飛ばす）では、配布中断が起きても単一ホーム内で指示とフックの世代が分裂しない | 登録済みフック, エージェントホーム, 配布・同期の中断 | Quint + TLC 全状態: `Spec/deploy_sync.qnt` `codeAsIs.noSplitHome` |
| 反例あり | 現行コード（ホーム単位の先行確定）であっても、複数ホーム同期の途中で中断したとき全ホームの世代が常に一致する | エージェントホーム, 登録済みフック, 配布・同期の中断 | Quint 反例: `Spec/deploy_sync.qnt` `codeAsIs.allHomesConsistent` |
| 未決定 | skills_lock.py のコピーモード配置で途中中断した場合、_save_state を項目ごとに永続化すべきか、それとも --force による手動復旧に委ねるか？ | 配置済みスキル, 配布・同期の中断, 診断と手動復旧 | 業務側への質問。空白を示す反例: `Spec/deploy_sync.qnt` `preFix.noOrphanedCopy` |
| 未決定 | sync_agents.py で hook_session.apply_home が停止したとき、直前に書き込んだ指示ファイル（CLAUDE.md / AGENTS.md）をロールバックすべきか？ | 登録済みフック, エージェントホーム, 配布・同期の中断 | 業務側への質問。空白を示す反例: `Spec/deploy_sync.qnt` `preFix.noSplitHome` |
| 未決定 | 複数ホーム同期で一部ホームだけ apply_home が停止したとき、完了済みホームを新世代のまま進める（現行の継続方針）か、全ホームを旧世代へ戻すべきか？ | エージェントホーム, 登録済みフック, 配布・同期の中断 | 業務側への質問。空白を示す反例: `Spec/deploy_sync.qnt` `codeAsIs.allHomesConsistent` |

## リポジトリ不変条件（旧ADR群の証明化）

<!-- stop-scene: ok; in book 配布・同期・スキル配置 -->
<!-- roles-tagged: 0 -->

停止の場面: 次の用語集で検査モデルにした: 配布・同期・スキル配置

| 役割 | 用語 |
|---|---|
| 資源 (Resource) | なし |
| 仮確保 (Hold) | なし |
| 外部の確認 (External confirmation) | なし |
| 権利 (Entitlement) | なし |
| 停止 (Stop) | なし |
| 計画停止 (Planned stop) | なし |
| 期限 (Deadline) | なし |
| 代わりの経路 (Fallback channel) | なし |
| 供給の取り消し (Supply cancellation) | なし |
| 振替 (Reallocation) | なし |

