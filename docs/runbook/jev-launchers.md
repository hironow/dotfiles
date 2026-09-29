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
問いは2つで、1回の呼び出しにまとめる。

- 難しさ（Score、3段階）: 単純な変更から、原因不明や複数サービスにまたがる作業まで。
- 厳密な構造が必要か（Noul）: JSON スキーマなど、形式の誤りが利用側を壊す作業か。

判定はこのリポジトリのコードで行う。
[Anthropic の Sonnet 5.5 推奨](https://platform.claude.com/docs/en/build-with-claude/effort#recommended-effort-levels-for-claude-sonnet-5-5) に合わせ、明確な作業は `medium`、難しい作業と厳密な構造が必要な作業は `high` にする。
`xhigh` と `max` は評価で改善が確認されるまで選ばない。

| 条件 | 思考レベル |
| --- | --- |
| 構造の確率が 0.7 以上 | `high` |
| 難しさの確信度が 0.5 未満（Jev が判断できない） | `medium` |
| 難しさのスコアが 1.5 以上（最上位の段階に近い） | `high` |
| 上記以外 | `medium` |

確信度が 0.5 未満のときは、Jev が「わからない」と答えたものとして扱い、既定の `medium` にする。
Jev に届かない、または応答を解釈できないときも `medium` で起動する。
閾値は `scripts/jev_launch.py` にあり、Pi の拡張と同じ値を使う。
両者の一致は `tests/unit/jev_effort_cases.json` で確認している。
Pi は認証済みの GitHub Copilot、Cursor、OpenRouter の順に選ぶ（最初の2つはサブスク、OpenRouter は従量課金）。
Pi の使用量上限に達したときは次の認証済み提供元へ切り替える。
利用できる提供元がなければエラーを表示する。
Claude Code 側に利用上限が出た場合、このコマンドは別アカウントや従量課金へ自動切替しない。
通常起動のモデル設定、権限、承認、既存の計画レビュー規則は変更しない。

## Pi の worker 起動ごとの選択

`jev-pi` で起動した Pi では、`subagent` で worker を1つ起動するたびに、その `task` を Jev に送り、思考レベルを選ぶ。
起動元の Sonnet 5.5 のモデルに `:medium` か `:high` を付けて worker を起動する。
判定と、Jev に届かないときの `medium` は起動時と同じ。
モデルを明示した起動は、Sonnet 5.5 の提供元で suffix がない場合にだけ思考レベルを付ける。
ほかのモデル、`:low` などの suffix 付き、`workflowScript` の中の子、管理操作には触れない。
通常の `pi` には影響しない。

API キーは Pi 起動時に拡張へ1回だけ渡し、拡張が読み込み直後に環境から消す。
bash ツールや worker の子セッションにキーは渡らない。
拡張が未導入のときは、キーを Pi に渡さず、worker の選択は行わない。

Claude Code の worker は対象外にしている。
Agent ツールの `PreToolUse` フックが返す `updatedInput` が無視され、サブエージェントの `effort:` も効かないため、公式の手段では起動ごとに制御できない。
