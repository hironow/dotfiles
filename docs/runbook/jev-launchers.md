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
Pi は認証済みの提供元を、GitHub Copilot、Cursor、Anthropic（Claude Code のサブスク）、OpenRouter の順に選ぶ。
Claude Code のサブスクは、Claude Code 自身のために残すので、ほかのサブスクより後にする。
OpenRouter は従量課金なので最後にする。
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

## Codex の worker のモデルと effort

`jev-claude` と `jev-pi` から Codex を worker として呼ぶときは、起動ごとに Jev が `gpt-6` のモデルと reasoning effort を選ぶ。
[OpenAI のモデル案内](https://learn.chatgpt.com/docs/models?surface=cli)の使い分けに合わせる。

| モデル | 向く作業 | 基本の effort |
| --- | --- | --- |
| `gpt-6-astra` | 最も難しい、複数の段階にわたる作業 | `low` |
| `gpt-6-sol` | 日常から複雑なコーディング、曖昧で難しい作業 | `medium` |
| `gpt-6-luna` | 明確で反復的な作業（抽出、分類、変換、絞った変更） | `high` |

Jev には、Claude の worker と同じ「難しさ」と「厳密な構造が必要か」に、「明確で反復的か」と「複数段階で最後まで判断が要るか」を足した4つを、1回の呼び出しで問う。
判定は次のとおり。

| 条件 | 選択 |
| --- | --- |
| 難しさの確信度が 0.5 未満、または応答なし | `gpt-6-sol` / `medium` |
| 難しさが 1.5 以上、複数段階が 0.7 以上、確信度が 0.8 以上 | `gpt-6-astra` / `low` |
| 難しさが 1.5 以上（上に当たらない） | `gpt-6-sol` / `high` |
| 「明確で反復的」が 0.7 以上（難しくない） | `gpt-6-luna` / `high` |
| 上記以外 | `gpt-6-sol` / `medium` |

厳密な構造が必要（0.7 以上）なら、`sol` は `high`、`astra` は `medium` に一段上げる。
Astra は Sol の約5倍の単価なので、確信度が高いときだけ選ぶ。
閾値は `scripts/jev_core.py` にあり、`tests/unit/jev_codex_cases.json` の実測値で固定している。

### Claude

`codex:codex-rescue` の依頼文の先頭に、`--model` と `--effort` を足す。
プラグインのラッパーは、この2つをそのまま Codex に渡す。
依頼文に `--model` か `--effort` がすでにあれば、そちらを優先して何もしない。
`--effort` の値は、プラグインが受け付ける `xhigh` までに収まる。

### Pi

Pi 組み込みの `codex-exec` と `codex-exec-writer` は、モデルを上書きできない（引数がコードで固定され、`config.toml` も無視する）。
代わりに、`just deploy` が `~/.pi/agent/agents/` に次の2つを配置する。

- `codex-jev`: 読み取り専用。`codex-exec` に相当する。
- `codex-jev-writer`: ワークスペースへの書き込み可。`codex-exec-writer` に相当する。

どちらも、実行の直前に Jev へ問い合わせ、`codex exec -m <model> -c model_reasoning_effort=<effort>` を起動する（サンドボックスなどの引数は組み込みと同じ）。
選択は実行時に行うので、`workflowScript` の中の子でも効く。
`jev-pi` で起動した Pi では、`subagent` の直接の呼び出しで `codex-exec` と `codex-exec-writer` が、自動でこの2つに切り替わる。
選ばれたモデルは、run の `external-*.stderr.log` の先頭行（`Jev: codex gpt-6-sol / medium (read-only)`）で確認できる。
Windows では、`sh` を使うため配置しない。

### 動作確認（利用上限のリセット後に一度）

`updatedInput` が Agent ツールで効くか、`effort` が実際に効くかは、実リクエストでしか確認できない。
次のコマンドを実行する。

```sh
just jev-claude-verify
```

判定は、モデルの返答ではなく Claude Code が残す記録で行う。
フック自身のログ、各サブエージェントの `agent-*.meta.json`（実際に使われた `agentType` と `name`）、各リクエストに記録された effort である。
名前なしと名前ありの worker、`codex:codex-rescue` を1つずつ起動する。

| 結果 | 終了コード | 意味 |
| --- | --- | --- |
| `PASS` | 0 | 名前なしの worker が差し替え後の定義で起動し、選んだ effort が記録された。Codex には `--model` と `--effort` が届いた。マージしてよい |
| `FAIL` | 1 | 差し替えが効かない、または effort が効かない。`updatedInput` が Agent で無視されている場合は何も変わらないだけで害はないが、この機能は動かないのでマージしない |
| `BLOCKED` | 2 | Claude の利用上限。リセット後にやり直す |
| `PARTIAL` | 3 | 動いているが effort を確認できない。`jev-claude '...'` で worker を動かし、`/tasks` の worker の行を目で確認する |

名前ありの worker（teammate）は、effort が落ちるという報告がある（anthropics/claude-code#64706）。
名前なしで正しければ `PASS` とし、名前ありが落ちたときは警告を出す。
