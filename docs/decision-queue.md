# 決めてほしいこと一覧（Decision Queue）

> 新しい決定案を「誰が・何を・いつ決めるか」で一覧にする。
> 決裁と相談は、各行の公開PRで追跡する。
> ADR-0051で採用済み。過去のADRを遡って変更しない。

## 早見表（決裁待ち）

| ID | 何を決める（ひとことで） | 種別 | 作者 | 作者連絡先 | 決める人 | 決裁者連絡先 | 期限 | 状態 | 相談記録 | 最終催促日 | 備考 | 元ファイル |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

## 決定済みログ

> 採用前のADR49件は[既存の索引](adr/README.md)を参照する。
> このログはADR-0051以降に裁定した記録を保存する。

| ID | 何を決めた | 結論 | 作者 | 作者連絡先 | 決定者 | 決裁者連絡先 | 決定日 | 相談記録 | 備考 | 元ファイル |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ADR-0051 | 新しい決定案を公開一覧で追跡する | A案 Accepted | Pi（owner session） | @hironow | Hiroto N. | @hironow | 2026-10-06 | [PR #461の裁定](https://github.com/hironow/dotfiles/pull/461#issuecomment-6020609790) | 全端末の同名ローカルファイルなし・patrolは旧パスに書かないと所有者確認。過去49件は遡及変更しない | [adr/0051-adopt-decision-queue-for-new-records.md](adr/0051-adopt-decision-queue-for-new-records.md) |
| ADR-0052 | 全エージェント共通の指示を刷新する（Go優先、fake/、core/shell設計、Plain Language） | Accepted | Claude Code（owner session） | @hironow | Hiroto N. | @hironow | 2026-10-11 | [PR #463の裁定](https://github.com/hironow/dotfiles/pull/463#issuecomment-6104926585) | `templates/agent-baseline/` の追従は別PR | [adr/0052-renew-global-agent-instructions.md](adr/0052-renew-global-agent-instructions.md) |
| ADR-0053 | Flatt のパッケージミラーをやめ、公式の取得元に戻す | Accepted（ADR-0028 を置き換え） | Claude Code（owner session） | @hironow | Hiroto N. | @hironow | 2026-10-11 | [PR #463の裁定](https://github.com/hironow/dotfiles/pull/463#issuecomment-6104926585) | 他の機体は `just harden-env`。他 repo の Flatt は別作業 | [adr/0053-stop-using-flatt-mirrors.md](adr/0053-stop-using-flatt-mirrors.md) |
| ADR-0054 | portless を just の recipe で包まず、直接使う | Accepted（ADR-0015 の一部を置き換え） | Claude Code（owner session） | @hironow | Hiroto N. | @hironow | 2026-10-11 | [PR #468の裁定](https://github.com/hironow/dotfiles/pull/468#issuecomment-6106249810) | merge 後に `just sync-agents all` | [adr/0054-run-portless-directly.md](adr/0054-run-portless-directly.md) |
| ADR-0055 | emulate を npx ではなく bunx で動かす | A案 Accepted（ADR-0016 の一部を置き換え） | Claude Code（owner session） | @hironow | Hiroto N. | @hironow | 2026-10-12 | [PR #470の裁定](https://github.com/hironow/dotfiles/pull/470#issuecomment-6113089576) | — | [adr/0055-run-emulate-with-bunx.md](adr/0055-run-emulate-with-bunx.md) |
| ADR-0056 | 5 つの Claude home で使う plugin の和集合（40 個）を全 home 共通に宣言する | A案 Accepted（ADR-0048 の一部を置き換え） | Claude Code（owner session） | @hironow | Hiroto N. | @hironow | 2026-10-16 | [PR #475の所有者裁定](https://github.com/hironow/dotfiles/pull/475#issuecomment-6209808795) | official は追従、hironow-plugins は repo 相対。DR 間整合検査: 0037・0044・0049 と整合、0048 は意図した部分置換のみ。merge 後に main で `just claude-plugins-install` | [adr/0056-common-claude-plugin-set.md](adr/0056-common-claude-plugin-set.md) |
| ADR-0057 | 共通セットの plugin は home ごとの設定なしで動くものに限り、doctor で見張る | A案 Accepted（ADR-0056 の一部を置き換え） | Claude Code（owner session） | @hironow | Hiroto N. | @hironow | 2026-10-16 | [PR #476の所有者裁定](https://github.com/hironow/dotfiles/pull/476#issuecomment-6211696383) | 宣言 38 個、pyright-lsp は毎回・GCP 系 4 個は 1 回だけ無効化。DR 間整合検査: 0048・0044・0037・0049 と整合、0056 は意図した部分置換のみ | [adr/0057-shared-plugins-need-no-per-home-settings.md](adr/0057-shared-plugins-need-no-per-home-settings.md) |
| ADR-0058 | Pi の web 検索を Ollama 経由に寄せ、pi 本体の計測を全機体で止める | Accepted | Pi（owner session） | @hironow | Hiroto N. | @hironow | 2026-10-19 | 本セッションでの所有者の直接指示（ADR 本文に記録） | `npm:pi-web-access` は retire して `pi remove`、計測は settings で明示 off、Ollama 不足時は公式 download 手順で自動導入（失敗は WARN、共存機 Windows+WSL は WSL 側 1 台のみ）。DR 間整合検査: 0056・0057 と同構造（宣言 + script）、衝突なし | [adr/0058-pi-web-search-ollama.md](adr/0058-pi-web-search-ollama.md) |
