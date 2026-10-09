# 決めてほしいこと一覧（Decision Queue）

> 新しい決定案を「誰が・何を・いつ決めるか」で一覧にする。
> 決裁と相談は、各行の公開PRで追跡する。
> ADR-0051で採用済み。過去のADRを遡って変更しない。

## 早見表（決裁待ち）

| ID | 何を決める（ひとことで） | 種別 | 作者 | 作者連絡先 | 決める人 | 決裁者連絡先 | 期限 | 状態 | 相談記録 | 最終催促日 | 備考 | 元ファイル |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ADR-0052 | 全エージェント共通の指示を刷新する（Go優先、fake/、core/shell設計、Plain Language） | ADR | Claude Code（owner session） | @hironow | Hiroto N. | @hironow | 2026-10-16 | Proposed | [PR #463](https://github.com/hironow/dotfiles/pull/463) | none | `templates/agent-baseline/`は別PR | [adr/0052-renew-global-agent-instructions.md](adr/0052-renew-global-agent-instructions.md) |

## 決定済みログ

> 採用前のADR49件は[既存の索引](adr/README.md)を参照する。
> このログはADR-0051以降に裁定した記録を保存する。

| ID | 何を決めた | 結論 | 作者 | 作者連絡先 | 決定者 | 決裁者連絡先 | 決定日 | 相談記録 | 備考 | 元ファイル |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ADR-0051 | 新しい決定案を公開一覧で追跡する | A案 Accepted | Pi（owner session） | @hironow | Hiroto N. | @hironow | 2026-10-06 | [PR #461の裁定](https://github.com/hironow/dotfiles/pull/461#issuecomment-6020609790) | 全端末の同名ローカルファイルなし・patrolは旧パスに書かないと所有者確認。過去49件は遡及変更しない | [adr/0051-adopt-decision-queue-for-new-records.md](adr/0051-adopt-decision-queue-for-new-records.md) |
