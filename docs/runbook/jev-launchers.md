# Jev で Claude Code と Pi を起動する

`j-cc` と `j-pi` は、最初の依頼文を Jev に問い合わせてから Claude Code と Pi を起動する。
Jev の答えから、セッションと worker の Sonnet 5.5 の思考レベルと、Codex の worker のモデルと reasoning effort を選ぶ。
通常の `claude` と `pi` の動作は変えない。

## 初回準備

`just deploy` を実行し、新しいシェルを開く。
Pi の拡張が未導入と表示された場合は、`just pi-extensions-install` を実行する。
`just deploy` は導入済みの Pi の拡張を更新しないので、更新は `just update-all`（中で `pi update --extensions`）で行う。
Pi の拡張とその依存は npm の 7 日の隔離を受けない（`just harden-env` が `~/.pi/agent/npm/.npmrc` に `min-release-age=0` を書く）。
更新が `ETARGET` で止まる機体は、`just harden-env` を実行してからやり直す。
機体ごとに拡張の版がずれると、同じ設定でも片方だけ失敗することがある。

TypeSafe の API キーは、`TYPESAFE_API_KEY=...` と書いた `~/.env` に置く。
起動のたびに読むので、書き換えてもシェルを開き直す必要はない。
環境変数の `TYPESAFE_API_KEY`（または `TYPESAFE_AI_API_KEY`）があれば、そちらを優先する。
worker のフックと `codex-jev` は、キーの環境変数を除いた環境で動くので、`~/.env` からしかキーを読めない。

他人が読める `~/.env` からは読まない。
macOS と Linux では、所有者だけが読み書きできる 0600 にする（`chmod 600 ~/.env`）。
Windows では、所有者が自分で、自分、SYSTEM、Administrators のほかにアクセス許可がないことを求める。
ホーム直下に作ったファイルは、既定の権限で満たすことが多い。
満たさないときは、`icacls` で許可の一覧を見て、継承を外して自分だけに許可し、残ったほかのアカウントの明示的な許可を外す。

```powershell
icacls "$HOME\.env"                                             # 許可の一覧を見る
icacls "$HOME\.env" /inheritance:r /grant:r "${env:USERNAME}:F"  # 継承を外して自分だけに許可する
icacls "$HOME\.env" /remove:g "<一覧に残ったアカウント>"            # 例: <PC 名>\CodexSandboxUsers
```

Codex の Windows のサンドボックスは、ホームのファイルに `CodexSandboxUsers` の読み取りの許可を付けることがある。
サンドボックスの中ではモデルが決めたコマンドが動くので、この許可を残したキーのファイルは、Jev は読まない。
`j-cc`、`j-pi`、`codex-jev` は Codex を起動する前にキーを読むので、この許可を外しても Codex の worker は動く。
許可が付け直されたときは、Jev が起動時に `~/.env must be owned by you` と表示するので、同じ手順で外す。

キーはリポジトリに置かない。
依頼文は Jev に送られるので、パスワードなどを含めない。

## 使い方

macOS と Linux の zsh、または Windows の PowerShell で、作業リポジトリに移動して実行する。

```sh
j-cc '失敗しているパーサのテストを修正して'
j-pi '失敗しているパーサのテストを修正して'
```

依頼文がないと起動しない。
既存のセッションを再開するのではなく、新しいセッションを始める。
通常起動のモデル設定、権限、承認、計画レビューの規則は変えない。
Claude Code に利用上限が出ても、別のアカウントや従量課金には切り替えない。

## 思考レベルの選び方

起動時に Jev へ 1 回だけ問い合わせる。
問いは次の 2 つで、1 回の呼び出しにまとめる。

- **難しさ**（Score、3 段階）：単純な変更から、原因不明で複数のサービスにまたがる作業まで
- **厳密な構造**（Noul）：JSON スキーマなど、形式の誤りが利用側を壊す作業か

答えはこのリポジトリのコードで思考レベルに直す。
[Anthropic の Sonnet 5.5 の推奨](https://platform.claude.com/docs/en/build-with-claude/effort#recommended-effort-levels-for-claude-sonnet-5-5)に合わせ、明確な作業は `medium`、難しい作業と厳密な構造が要る作業は `high` にする。
`xhigh` と `max` は、評価で改善を確かめるまで選ばない。

| 条件 | 思考レベル |
| --- | --- |
| 厳密な構造の確率が 0.7 以上 | `high` |
| 難しさの確信度が 0.5 未満（Jev にも判断がつかない） | `medium` |
| 難しさのスコアが 1.5 以上（最上位の段階に近い） | `high` |
| 上記以外 | `medium` |

Jev に届かないときと、応答を解釈できないときも `medium` にする。
NaN、無限大、数値に直すとあふれる値は採用しない。
厳密な構造の確率が有効に 0.7 以上なら、難しさの値が無効でも `high` にする。
閾値は `scripts/jev_core.py` にあり、Pi の拡張も同じ値を使う（`tests/unit/jev_effort_cases.json` が一致を確かめる）。

## worker ごとの選択

セッションだけでなく、worker を 1 つ起動するたびに、その依頼を Jev に送って思考レベルを選び直す。
判定と、Jev に届かないときの `medium` は、起動時と同じである。

### Pi

`j-pi` で起動した Pi では、`subagent` が worker を起動するたびに `task` を Jev に送る。
起動元の Sonnet 5.5 のモデル名に `:medium` か `:high` を付けて worker を起動する。
モデルを明示した起動は、Sonnet 5.5 の提供元で suffix がない場合にだけ付ける。
ほかのモデル、`:low` などの suffix が付いた起動、`workflowScript` の中の子、管理操作には触れない。

API キーは Pi の起動時に拡張へ 1 回だけ渡し、拡張が読み込み直後に環境から消す。
bash ツールと worker の子セッションには、キーが渡らない。
拡張が未導入なら、キーを Pi に渡さず、worker の選択もしない。

### Claude Code

Claude Code の Agent ツールには effort の引数がなく、サブエージェントの effort は定義ごとに固定される。
そこで `j-cc` は、次の 2 つをそのセッションにだけ注入する（`--settings` と `--agents`。グローバル設定は変えない）。

- `worker-medium` と `worker-high`：effort だけが違う worker の定義
- `PreToolUse` フック（`scripts/jev_claude_hook.py`）：既定の worker の起動を、Jev が選んだほうの定義に差し替える

差し替えるのは、`subagent_type` が `general-purpose`、`worker`、または未指定の起動だけである。
`Explore`、自作のエージェント、`model` を明示した起動には触れない。
フックは権限の判定を返さないので、承認の確認は省かれない。
失敗したときは何も変えず、Claude が送ったとおりに起動する。
Claude Code は Windows でもフックを Git Bash で実行するので、フックのコマンドはパスを `/` 区切りで渡す。

## Codex の worker のモデルと effort

`j-cc` と `j-pi` から Codex を worker として呼ぶと、起動ごとに Jev が `gpt-6` 系のモデルと reasoning effort を選ぶ。
使い分けは [OpenAI のモデル案内](https://learn.chatgpt.com/docs/models?surface=cli)に合わせる。

| モデル | 向く作業 | 基本の effort |
| --- | --- | --- |
| `gpt-6-astra` | 曖昧で、深い分析や大きな成果物が要る、最も難しい作業 | `low` |
| `gpt-6.1-sol` | 時間とコストも管理したい複雑な作業（Astra に近い性能で単価が低い） | `medium` |
| `gpt-6-luna` | 明確で反復的な作業（抽出、分類、変換、絞った変更） | `high` |

Sol は 6.1（`gpt-6.1-sol`）を使う。
6.0 の `gpt-6-sol` は OpenAI の推奨から外れたので使わない。

Jev には、思考レベルと同じ 2 つの問いに「明確で反復的か」と「複数の段階で最後まで判断が要るか」を足した 4 つを、1 回で問う。

| 条件 | 選択 |
| --- | --- |
| 難しさの確信度が 0.5 未満、または応答がない | `gpt-6.1-sol` / `medium` |
| 難しさが 1.5 以上、複数段階が 0.7 以上、確信度が 0.8 以上 | `gpt-6-astra` / `low` |
| 難しさが 1.5 以上（上に当たらない） | `gpt-6.1-sol` / `high` |
| 明確で反復的が 0.7 以上（難しくない） | `gpt-6-luna` / `high` |
| 上記以外 | `gpt-6.1-sol` / `medium` |

厳密な構造が要る（0.7 以上）なら、Sol は `high`、Astra は `medium` に一段上げる。
Astra は Sol より単価がはるかに高いので、確信度が高いときだけ選ぶ。
閾値は `scripts/jev_core.py` にあり、`tests/unit/jev_codex_cases.json` の実測で固定している。

### Claude Code から

`codex:codex-rescue` の依頼文の先頭に `--model` と `--effort` を足し、プラグインのラッパーがそのまま Codex に渡す。
依頼文にすでに `--model` か `--effort` があれば、そちらを優先して何もしない。
`--effort` は、プラグインが受け付ける `xhigh` までに収まる。
この経路には、Claude Code に Codex のプラグイン（`codex:codex-rescue`）が入っている必要がある。

### Pi から

Pi に組み込みの `codex-exec` と `codex-exec-writer` は、モデルを上書きできない（引数がコードで固定され、`config.toml` も読まない）。
代わりに `just deploy` が、`~/.pi/agent/agents/` に次の 2 つを生成する。

- `codex-jev`：読み取り専用（`codex-exec` に相当）
- `codex-jev-writer`：ワークスペースに書き込める（`codex-exec-writer` に相当）

どちらも実行の直前に Jev へ問い合わせ、`codex exec -m <model> -c model_reasoning_effort=<effort>` を起動する（サンドボックスなどの引数は組み込みと同じ）。
Python とスクリプトの絶対パスを定義に埋め込むので、`sh` は要らず、Windows でも同じ定義が動く。
選択は実行時に行うので、`workflowScript` の中の子でも効く。
`j-pi` で起動した Pi では、`subagent` から `codex-exec` と `codex-exec-writer` を直接呼ぶと、自動でこの 2 つに切り替わる。
選ばれたモデルは、実行の stderr の先頭行（`Jev: codex gpt-6.1-sol / medium (read-only)`）で確かめられる（Pi の run では `external-*.stderr.log` に残る）。

## Pi の提供元と切り替え

Pi は、認証済みの提供元を GitHub Copilot、Anthropic（Claude Code のサブスク）、OpenRouter の順に使う。
Cursor は、ログインしていても使わない。
Pi が Cursor の提供元にツールを渡さない（`Tool not available` と答える）ので、そこでは worker の起動も、コマンドの実行も、編集もできないからである。
Claude Code のサブスクは Claude Code 自身のために残したいので、ほかのサブスクより後にする。
OpenRouter は従量課金なので最後にする。

次の提供元へ切り替えるのは、429 のステータスか、既知の機械的な上限エラーを確認したときだけである。
「quota exceeded」のような曖昧な文章や、認証エラーやサーバーエラーと矛盾するステータスでは切り替えず、元のエラーを表示する。
切り替え先の認証済みの提供元がなければ、元のエラーを表示する。

## 動作確認

Agent ツールで `updatedInput` が効くか、`effort` が実際に効くかは、実際のリクエストでしか確かめられない。

```sh
just jev-claude-verify
```

名前なしと名前ありの worker、`codex:codex-rescue` を 1 つずつ起動し、モデルの返答ではなく Claude Code が残す記録で判定する。
記録とは、フック自身のログ、各サブエージェントの `agent-*.meta.json`（実際に使われた `agentType` と `name`）、各リクエストに記録された effort である。

| 結果 | 終了コード | 意味 |
| --- | --- | --- |
| `PASS` | 0 | 名前なしの worker の定義と選んだ effort、Codex の呼び出し引数を確認できた（確認できたのは、実行した機体についてだけ） |
| `FAIL` | 1 | スキーマの拒否、worker の定義や effort の不一致を確認した（利用上限が同時に出ても、こちらを優先する） |
| `BLOCKED` | 2 | 提供元のエラーイベントで利用上限を確認した、または CLI が未ログインで終了した（結果イベントが `Not logged in`）。リセット後かログイン後にやり直す。会話の中の引用は対象外 |
| `PARTIAL` | 3 | worker の effort の証拠が足りないか、親と同じ `medium` で効果を区別できない。`/tasks` でも確かめる |

一致した名前なしの worker には、それぞれ effort の記録が要る。
ただし、各フックの起動と全 worker の一対一の対応は検証しないので、`PASS` は全起動の差し替えを証明しない。
Codex については、companion を呼ぶツールの引数に選んだ `--model` と `--effort` があることを確かめるが、下流の全 API リクエストに同じ effort が届いたことまでは証明しない。
名前ありの worker（teammate）の effort が違う場合は、別に警告を出す。

### Pi の worker

Pi の worker の思考レベルは、次で確かめる。

```sh
just jev-pi-verify
```

`j-pi` と同じ起動を非対話（`pi -p`）で 1 回行い、難しい依頼で worker を 1 つ起動させる（セッション自体は `medium`）。
判定は、セッションの記録ではなく、pi-subagents が run ごとに残す `subagent-artifacts/<run>_worker_meta.json` の `model`（worker が実際に動いたモデル）と終了コードで行う。
セッションの記録には、拡張が書き換える前の起動の引数が残るので、書き換えの結果を示せないからである。

| 結果 | 終了コード | 意味 |
| --- | --- | --- |
| `PASS` | 0 | worker が `:high`（Jev の選択。セッションの `medium` より上）で最後まで動いた |
| `FAIL` | 1 | subagent を呼んだのに worker の記録がない、モデルに effort の suffix がない、または worker が失敗した |
| `BLOCKED` | 2 | キーか拡張がない、利用上限で worker の前に止まった、またはモデルが subagent を呼ばなかった（1 回だけ自動でやり直す） |
| `PARTIAL` | 3 | worker が `medium` で動き、セッションと区別できない |
