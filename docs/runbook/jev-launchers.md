# Jev で Claude Code と Pi を起動する

通常の `claude` と `pi` はそのまま使える。
作業内容に応じて Sonnet 5.5 の思考レベルを選びたいときは、専用コマンドに**最初の依頼文**を渡す。

## 初回準備

`just deploy` を実行し、新しいシェルを開く。
Pi の拡張が未導入と表示された場合は、`just pi-extensions-install` を再実行する。

TypeSafe の API キーは `TYPESAFE_API_KEY` 環境変数に設定する。
macOS と Linux では、`TYPESAFE_API_KEY=...` と書いた `~/.env`（所有者のみ読み書き可能な 0600）からも読み込める。
Windows PowerShell では環境変数を使用する。
セッション中だけ設定する場合は以下を実行する。

```powershell
$env:TYPESAFE_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host -AsSecureString 'TypeSafe key')).Password
```

キーをリポジトリに置かない。
依頼文は Jev に送信されるため、パスワードなどを含めない。

## 使い方

macOS と Linux（zsh）、または Windows PowerShell で、作業リポジトリに移動して実行する。

```sh
jev-claude '失敗しているパーサのテストを修正して'
jev-pi '失敗しているパーサのテストを修正して'
```

依頼文を渡さないと起動しない。
既存セッションを再開するコマンドではなく、新しいセッションを開始する。

## 選択と切り戻し

起動時に Jev へ1回問い合わせ、Sonnet 5.5 の思考レベルを選ぶ。
[Anthropic の Sonnet 5.5 推奨](https://platform.claude.com/docs/en/build-with-claude/effort#recommended-effort-levels-for-claude-sonnet-5-5) に合わせ、明確な作業は `medium`、難しい作業や難しい JSON は `high` にする。
`xhigh` と `max` は評価で改善が確認されるまで選ばない。
応答が得られなければ `medium` で起動する。
Pi は認証済みの GitHub Copilot、Cursor、OpenRouter の順に選ぶ（最初の2つはサブスク、OpenRouter は従量課金）。
Pi の使用量上限に達したときは次の認証済み提供元へ切り替える。
利用できる提供元がなければエラーを表示する。
Claude Code 側に利用上限が出た場合、このコマンドは別アカウントや従量課金へ自動切替しない。
通常起動のモデル設定、権限、承認、既存の計画レビュー規則は変更しない。
