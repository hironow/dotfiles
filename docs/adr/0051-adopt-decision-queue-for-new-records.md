# 0051. 新しい決定記録をdecision queueで追跡する

**Date:** 2026-10-06
**Status:** Proposed
**ID:** ADR-0051
**Title:** 新しい決定記録をdecision queueで追跡する
**Decided-date:** —
**Decision-maker:** Hiroto N.（裁定待ち）
**Decision-maker-contact:** @hironow
**Author:** Pi（owner session）
**Author-contact:** @hironow
**Supersedes:** none
**Superseded-by:** none
**Related:** [ADR索引](README.md)、[文書規約](../../ROOT_AGENTS_docs_agents_docs-discipline.md)、[既存のignore規則](../../.gitignore)
**Consultation-trace:** [公開PR #461](https://github.com/hironow/dotfiles/pull/461)

## やさしい説明

今は判断待ちの決定案を一覧できない。
誰がいつ判断するか、相談場所も含めて一覧にするか決める。
採択済みの古い決定を勝手に書き換えたり、関係者の連絡先を推測で埋めたりはしない。

## Context

このリポジトリには採択済みを含む49件のADR（技術的な決定記録）があり、`docs/adr/README.md`に索引がある。
一方、追跡済みの`docs/decision-queue.md`はまだない。
[文書規約](../../ROOT_AGENTS_docs_agents_docs-discipline.md)はdecision queue（決裁待ち一覧）とPDR（製品上の決定記録）を任意採用とし、採用自体をADRに記録するよう求める。
しかし[既存のignore規則](../../.gitignore)は、同じパスをtooling-patrol（ツール点検作業）のローカル専用出力として2026-06-10からGitの追跡対象から除外している。
今回の公開queue案は、この誤公開防止策の変更を伴う。
作業中の元の端末には同名ファイルがないが、他の端末と外部patrolの出力先は未確認である。

このリポジトリのGitHub Issuesは無効である。
今後の相談には、公開可能な内容だけを含めたGitHub PR（変更提案）の本文と議論を使える。
今回の決定記録の起票手順はqueueへの登録を必須とするため、本ADR自身の行を決裁待ちとして仮置きする。
2026-10-06、所有者はFlatt経路に関する後続ADRを起票する前に、decision queueの採用を別ADRとして提案する順序を選んだ。

## Decision

（Proposed。確定後にAcceptedのMUST/SHALL、Rejectedの理由、またはDeferredの再検討条件を記述。）

## Options Considered

- **A) decision queueを採用する**：新しい提案はADR/PDRファイルと公開一覧を同時に作り、作者と決裁者の安定した連絡先、相談先、期限を残す。`docs/decision-queue.md`だけをignoreから外し、`docs/decision-queue-*.md`はローカル専用として引き続き除外する。承認時は決定済みログに移し、既存のAccepted本文は不変とする。過去49件は遡って書き換えないが、公開前の情報確認と一覧・索引の維持が増える。
- **B) README索引とADR本文だけで続ける**：新たな管理ファイルが要らない。未決案の期限、作者と決裁者の連絡先、相談記録は一覧できず、各ファイルを見なければ分からない。
- **C) 公開PRだけに判断待ちを記録する**：追加ファイルを作らず議論に人を呼べる。PRを閉じた後の未決事項と元ADRの関係を示す一覧がなく、PRの外から追いにくい。

## Consequences

- **Positive**：A案なら新しい未決記録と決裁期限、相談先を一か所で見られる。
- **Negative**：A案では提案、決裁、置換のたびにADR/PDR、queue、索引を同期する手間が増える。従来のignore保護を外すと、patrolが旧パスへ書き続けた場合にローカルの内容を公開する危険がある。公開PRに書く事実を確認し、非公開の運用情報は転載しない。
- **Neutral**：過去49件の状態と履歴は既存ADRとREADME索引に残る。この提案の起票だけで古い記録の状態・本文、パッケージ取得設定は変わらない。ignore（追跡除外設定）の変更はレビュー用PRの案であり、現行main（既定ブランチ）には反映しない。

## 他のDRとの照合

このリポジトリのADR49件のタイトルと状態、関係を走査し、決裁一覧そのものを採用した既存記録は見つからなかった。
関連する既存記録の本文と文書規約も確認した。
旧記録の作者や連絡先が不明な箇所を、新しいqueueのために推測して補わない。
既存のignore規則との衝突はADR同士の矛盾ではないが、2026-10-06に当該規則の作者である所有者へ確認した。
所有者の裁定は「公開queueへの切替を後続ADRで**提案**し、既存のローカル出力先と他端末の状態を採択・merge（本流への取り込み）前に確認する」であり、採択の承認ではない。
この提案だけを認めた裁定は[公開PR #461](https://github.com/hironow/dotfiles/pull/461)の相談本文にも記録した。

## 裁定・merge前の停止条件

- 他端末に同名の無追跡ローカルファイルがあるか、所有者が確認する。あれば自動移動・公開せず、別のignoredパスへ安全に退避してからcheckoutする。
- 外部tooling-patrolの出力先を所有者が確認し、追跡対象の`docs/decision-queue.md`へ書かないことを確かめる。ローカル出力には引き続きignoredとなる`docs/decision-queue-local.md`などを使う。
- この公開queueとPRの追加内容に非公開情報が含まれないことを確認する。どれかを証明できなければ採択・mergeしない。

## 反転記録 (Reversal)

none（既存のAccepted ADRを置き換えない。）

## 決定（記入待ち）

- [ ] A案でAccept
- [ ] B案でAccept
- [ ] C案でAccept
- [ ] 修正のうえAccept（修正点: ____）
- [ ] Reject（理由: ____）
- [ ] Deferred（再検討条件: ____）
- 決定者・日付: ____
- A案Accept時のアクション: 上記停止条件を確認し、以後の新しいADR/PDRにはqueueの行、連絡先、期限、相談記録を必須とする。採択後は決定済みログと索引を更新し、文書規約に採用を反映する。過去49件の連絡先を推測で遡及記載しない。
- B案Accept時のアクション: このADRの行は決定済みログに残す。今後のADR起票が必須のqueue規則と矛盾しない代替手順を人が裁定するまで、追加起票を止める。
- C案Accept時のアクション: このADRの行は決定済みログに残す。PRだけで必須のqueue規則を代替できるか別途裁定し、それまで追加起票を止める。
- 修正Accept時のアクション: 修正された適用範囲とqueueの運用を文書規約に反映する。
- Reject時のアクション: 理由を記録し、このADRの行は決定済みログに残す。以後の起票方法を人が決めるまで追加起票を止める。
- Deferred時のアクション: 再検討条件と期限を記録し、次のADR起票方法を人に確認する。
