# 0051. 新しい決定記録をdecision queueで追跡する

**Date:** 2026-10-06
**Status:** Accepted
**ID:** ADR-0051
**Title:** 新しい決定記録をdecision queueで追跡する
**Decided-date:** 2026-10-06
**Decision-maker:** Hiroto N.
**Decision-maker-contact:** @hironow
**Author:** Pi（owner session）
**Author-contact:** @hironow
**Supersedes:** none
**Superseded-by:** none
**Related:** [ADR索引](README.md)、[文書規約](../../ROOT_AGENTS_docs_agents_docs-discipline.md)、[既存のignore規則](../../.gitignore)
**Consultation-trace:** [公開PR #461の所有者裁定](https://github.com/hironow/dotfiles/pull/461#issuecomment-6020609790)

## やさしい説明

新しい判断待ちの決定案を、誰がいつ判断するか、相談場所も含めた公開一覧で追跡する。
採択済みの古い決定を勝手に書き換えたり、関係者の連絡先を推測で埋めたりはしない。

## Context

このリポジトリには採択済みを含む49件のADR（技術的な決定記録）があり、`docs/adr/README.md`に索引がある。
採択前は、追跡済みの`docs/decision-queue.md`がなかった。
[文書規約](../../ROOT_AGENTS_docs_agents_docs-discipline.md)はdecision queue（決裁待ち一覧）とPDR（製品上の決定記録）を任意採用とし、採用自体をADRに記録するよう求める。
しかし[既存のignore規則](../../.gitignore)は、同じパスをtooling-patrol（ツール点検作業）のローカル専用出力として2026-06-10からGitの追跡対象から除外している。
今回の公開queue案は、この誤公開防止策の変更を伴う。
2026-10-06に所有者は全端末に同名のローカル専用ファイルがなく、外部patrolが追跡対象の旧パスへ今後書かないことを確認した。
この確認とA案の採択は[公開PRの裁定](https://github.com/hironow/dotfiles/pull/461#issuecomment-6020609790)に記録した。

このリポジトリのGitHub Issuesは無効である。
今後の相談には、公開可能な内容だけを含めたGitHub PR（変更提案）の本文と議論を使える。
今回の決定記録の起票時には本ADR自身の行を決裁待ちとして仮置きし、裁定後に決定済みログへ移した。
2026-10-06、所有者はFlatt経路に関する後続ADRを起票する前に、decision queueの採用を別ADRとして提案する順序を選んだ。

## Decision

1. 新たに起票するADR/PDRは、提案ファイルと`docs/decision-queue.md`の決裁待ち行を同時に作らなければならない（MUST）。作者と決裁者の安定した連絡先、期限、公開可能な相談先を記録する。連絡先を推測で埋めてはならない（MUST NOT）。
2. 裁定後はqueueの行を決定済みログへ移し、ADR/PDR本文と索引を同時に更新しなければならない（MUST）。採択済み本文は、後続の新しい決定記録による置換以外では変更しない。
3. Gitの追跡対象に戻すのは`docs/decision-queue.md`だけとし、`docs/decision-queue-*.md`のローカル専用保護を維持しなければならない（MUST）。過去49件を遡及変更せず、外部patrolの新しい出力先や非公開情報を公開queueに記載してはならない（MUST NOT）。
4. GitHub Issuesは無効なので、公開可能な内容だけを含むPRで決裁と相談を行い、queueにそのURLを記録しなければならない（MUST）。

## Options Considered

- **A) decision queueを採用する**：新しい提案はADR/PDRファイルと公開一覧を同時に作り、作者と決裁者の安定した連絡先、相談先、期限を残す。`docs/decision-queue.md`だけをignoreから外し、`docs/decision-queue-*.md`はローカル専用として引き続き除外する。承認時は決定済みログに移し、既存のAccepted本文は不変とする。過去49件は遡って書き換えないが、公開前の情報確認と一覧・索引の維持が増える。
- **B) README索引とADR本文だけで続ける**：新たな管理ファイルが要らない。未決案の期限、作者と決裁者の連絡先、相談記録は一覧できず、各ファイルを見なければ分からない。
- **C) 公開PRだけに判断待ちを記録する**：追加ファイルを作らず議論に人を呼べる。PRを閉じた後の未決事項と元ADRの関係を示す一覧がなく、PRの外から追いにくい。

## Consequences

- **Positive**：新しい未決記録と決裁期限、相談先を一か所で見られる。
- **Negative**：提案、決裁、置換のたびにADR/PDR、queue、索引を同期する手間が増える。ignore保護を外す対象を広げるとローカルの内容を公開する危険があるため、単一パスだけを追跡し、公開前に本文を確認する。
- **Neutral**：過去49件の状態と履歴は既存ADRとREADME索引に残る。本裁定はパッケージ取得設定や既存Accepted ADRの本文を変更しない。

## 他のDRとの照合

このリポジトリのADR49件のタイトルと状態、関係を走査し、決裁一覧そのものを採用した既存記録は見つからなかった。
関連する既存記録の本文と文書規約も確認した。
旧記録の作者や連絡先が不明な箇所を、新しいqueueのために推測して補わない。
既存のignore規則との衝突はADR同士の矛盾ではないが、2026-10-06に当該規則の作者である所有者へ確認した。
初回の相談では、所有者は公開queueへの切替を提案することだけを認め、採択は安全確認後まで保留した。
その後、全端末とpatrolの確認を終え、同じ所有者がA案の採択を[公開PR #461](https://github.com/hironow/dotfiles/pull/461#issuecomment-6020609790)で裁定した。

## 裁定・merge前の停止条件

- 所有者は全端末に同名のローカル専用ファイルがないと確認した。既存ファイルを移動・公開する必要はない。
- 所有者は外部tooling-patrolが追跡対象の旧パスへ今後書かないと確認した。新しい出力先は公開しない。
- PR #461の差分は公開可能な決定記録と正確なignoreの例外だけであり、非公開情報を転載しない。これらの確認とA案の裁定は[PRの議論](https://github.com/hironow/dotfiles/pull/461#issuecomment-6020609790)に残した。

## 反転記録 (Reversal)

none（既存のAccepted ADRを置き換えない。）

## 決定（2026-10-06）

- **A案をAccepted**。決定者：Hiroto N.（@hironow）。[公開PR #461の裁定](https://github.com/hironow/dotfiles/pull/461#issuecomment-6020609790)。
- B案を却下：索引と個別ADRだけでは未決事項の期限・連絡先・相談の進捗を一覧できない。
- C案を却下：PRだけでは終了後も残る未決事項と裁定済み記録の関係を、リポジトリ内から追いにくい。
- 次の作業：確認済みの停止条件を維持し、queueの行を決定済みログへ移す。以後の新しいADR/PDRにはqueue、安定した連絡先、期限、PR相談記録を必須とする。過去49件は遡及変更しない。
