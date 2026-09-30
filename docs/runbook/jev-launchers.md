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
NaN、無限大、数値への変換でオーバーフローする値は採用しない。
独立した有効な構造の確率が 0.7 以上なら、難しさの値が無効でも `high` にする。
閾値は `scripts/jev_core.py` にあり、Pi の拡張と同じ値を使う。
両者の一致は `tests/unit/jev_effort_cases.json` で確認している。
Pi は認証済みの GitHub Copilot、Cursor、OpenRouter の順に選ぶ（最初の2つはサブスク、OpenRouter は従量課金）。
Pi は明示的な 429 ステータスか、既知の機械的な上限エラー種別を確認した場合だけ、次の認証済み提供元へ切り替える。
曖昧な「quota exceeded」などの文章や、認証・サーバーエラーを含む矛盾したステータスでは切り替えず、元のエラーを表示する。
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

## Claude Code の worker 起動ごとの選択

`jev-claude` で起動した Claude Code でも、既定の worker（`general-purpose`）を起動するたびに、`prompt` を Jev に送り、思考レベルを選ぶ。

Claude Code の Agent ツールには effort の引数がなく、サブエージェントの effort は定義ごとに固定される。
そのため次の2つを、このセッションにだけ注入している（`--settings` と `--agents`。グローバル設定は変えない）。

- `worker-medium` と `worker-high`: effort だけが違う worker の定義。
- `PreToolUse` フック（`scripts/jev_claude_hook.py`）: 既定の worker の起動を、Jev が選んだ方の定義に差し替える。

差し替えるのは `subagent_type` が `general-purpose`、`worker`、または未指定の起動だけ。
`Explore` や自作のエージェント、`model` を明示した起動には触れない。
判定は Pi と同じコード（`scripts/jev_core.py`）を使う。
フックは権限の判定を返さないため、承認の確認は省略されない。
失敗したときは何も変えず、Claude が送った起動のまま実行する。
Windows では、キーを環境変数からしか読めないため、この差し替えは行われない。

### 動作確認

`updatedInput` が Agent ツールで効くか、`effort` が実際に効くかは、実リクエストでしか確認できない。
次のコマンドを実行する。

```sh
just jev-claude-verify
```

判定は、モデルの返答ではなく Claude Code が残す記録で行う。
フック自身のログ、各サブエージェントの `agent-*.meta.json`（実際に使われた `agentType` と `name`）、各リクエストに記録された effort である。
名前なしと名前ありの worker を1つずつ起動する。

| 結果 | 終了コード | 意味 |
| --- | --- | --- |
| `PASS` | 0 | 名前なしの worker の定義と選んだ effort を確認できた。CI と Windows の確認は別 |
| `FAIL` | 1 | スキーマ拒否、worker の定義や effort の不一致を確認した。利用上限が同時に出てもこちらを優先する |
| `BLOCKED` | 2 | provider のエラーイベントで利用上限を確認した、または CLI が未ログインで終了した（結果イベントが `Not logged in`）。リセット後、またはログイン後にやり直す。会話中の引用は対象外 |
| `PARTIAL` | 3 | worker の effort の証拠が不足するか、親と同じ `medium` で効果を区別できない。`/tasks` でも確認する |

一致した名前なし worker は、それぞれに effort の記録が必要である。
ただし、各フックの起動と全 worker の一対一対応は検証していないため、`PASS` は全起動の差し替えを証明しない。
名前ありの worker（teammate）の effort が異なる場合は、別に警告を出す。
