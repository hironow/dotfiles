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

TypeSafe の API キーは、`TYPESAFE_API_KEY=...` と書いた `~/.config/jev/env` に置く。
起動のたびに読むので、書き換えてもシェルを開き直す必要はない。
環境変数の `TYPESAFE_API_KEY`（または `TYPESAFE_AI_API_KEY`）があれば、そちらを優先する。
worker のフックと `codex-jev` は、キーの環境変数を除いた環境で動くので、このファイルからしかキーを読めない。
`~/.config/jev/env` がない機体では、これまでの `~/.env` を読む（ファイルがあるのに読めないときは、`~/.env` に戻らない）。

置き場所が `~/.config` なのは、Codex の Windows のサンドボックスのためである。
サンドボックスは Codex を使うたびに、ホーム直下のほぼすべての項目へ `CodexSandboxUsers` の読み取りの許可を付け直す。
除外は `.ssh`、`.aws`、`.config` などの固定の一覧だけで、`~/.env` は入っていない。
サンドボックスの中ではモデルが決めたコマンドが動くので、この許可のあるキーのファイルは、Jev は読まない。

```sh
mkdir -p ~/.config/jev
grep '^TYPESAFE_API_KEY=' ~/.env > ~/.config/jev/env   # ~/.env から移す場合
chmod 600 ~/.config/jev/env                              # macOS と Linux
```

他人が読めるキーのファイルからは読まない。
macOS と Linux では、所有者だけが読み書きできる 0600 にする。
Windows では、所有者が自分で、自分、SYSTEM、Administrators のほかにアクセス許可がないことを求める。
`~/.config` の下に作ったファイルは、既定の権限で満たすことが多い。
満たさないときは、Jev が起動時に `~/.config/jev/env must be owned by you` と表示するので、`icacls` で許可の一覧を見て、継承を外して自分だけに許可する。

```powershell
icacls "$HOME\.config\jev\env"                                             # 許可の一覧を見る
icacls "$HOME\.config\jev\env" /inheritance:r /grant:r "${env:USERNAME}:F"  # 継承を外して自分だけに許可する
```

キーはリポジトリに置かない。
依頼文は Jev に送られるので、パスワードなどを含めない。

## 使い方

macOS と Linux の zsh、または Windows の PowerShell で、作業リポジトリに移動して実行する。

```sh
j-cc '失敗しているパーサのテストを修正して'
j-pi '失敗しているパーサのテストを修正して'
```

新しいセッションは、依頼文がないと起動しない。
通常起動のモデル設定、権限、承認、計画レビューの規則は変えない。
Claude Code に利用上限が出ても、別のアカウントや従量課金には切り替えない。

### 以前のセッションを再開する

`-c`（`--continue`）と `-r`（`--resume`）は、Claude Code と Pi の同名のオプションと同じ意味で、同じように書く。

```sh
j-cc -c                                   # このディレクトリの直近のセッションを続ける
j-cc -c '次はエラー処理も直して'          # 続けて、依頼文を送る
j-cc -r                                   # 一覧から選ぶ
j-cc -r <セッションの ID か名前> '依頼文'
j-pi -c '依頼文'
j-pi -r                                   # 一覧から選ぶ
```

Claude Code の `-r` は直後の 1 語をセッションの ID か名前（一覧の検索語）として読むので、`j-cc -r` も同じに読む。
Pi の `-r` は値を取らないので、`j-pi -r` に続く語は依頼文になる。
再開したセッションにも、新しいセッションと同じモデル、システムプロンプトの規則、worker の設定（`j-cc` の worker のフック、`j-pi` のキーの受け渡し）、headroom の proxy を付ける。
素の `claude -c` や `pi -c` で再開すると、これらは付かない。

思考レベルは、依頼文があれば新しいセッションと同じく Jev が選ぶ。
依頼文がなければ Jev には問い合わせず、`medium` で再開する。
前のセッションの思考レベルは引き継がない。
ほかのオプション（`--fork-session` など）は受け付けないので、使うときは `claude` や `pi` を直接起動する。

## 思考レベルの選び方

起動時に Jev へ 1 回だけ問い合わせる（依頼文のない再開では問い合わせない）。
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
`just deploy` が、存在するすべての Claude の home にタグで固定した版を入れる（宣言は `dump/harness/claude-plugins.json`、ADR 0048）。
入っていない home は `just doctor` の `claude-plugins` が知らせるので、`just claude-plugins-install` で入れる。

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

## headroom（j-cc と Codex の worker）

`j-cc` は、起動する Claude とその worker のリクエストを headroom の proxy に通し、モデルに届く内容を圧縮する。
`ANTHROPIC_BASE_URL` を渡すのは、その Claude のプロセスにだけである。
`ANTHROPIC_BASE_URL` が `api.anthropic.com` 以外を指すと Claude Code の Remote Control が使えなくなるので、素の `claude` は直結のままにする。
`j-pi` から起動する Codex の worker（`codex-jev`）も、同じ proxy を通す（`codex exec` に `-c openai_base_url=http://127.0.0.1:<port>/v1` と `OPENAI_BASE_URL` を付ける。`--ignore-user-config` なので、設定ファイルではなくコマンドラインで渡す）。
`j-pi` 自身の通信は経由しない。
Anthropic の経路は pi-background-tasks が公式の `https://api.anthropic.com` 以外を拒む。
GitHub Copilot の経路は、ログインのトークンから毎回接続先を決め直すので、拡張から向け先を変えられないからである。
headroom は mise で入る（`pypi:headroom-ai`）。

`j-cc` と Codex の worker は起動のたびに、次の順で proxy を用意する。

1. `~/.cache/jev/headroom.json` に記録したポートの `/health` が、準備のできた headroom の proxy を返せば、それを使う
2. そうでなければ、空いているポートで `headroom proxy --host 127.0.0.1` を起動し（beacon は off）、準備ができたらポートを記録する。出力は `~/.cache/jev/headroom-proxy.log` に追記する
3. headroom がない、または起動できないときは、そう表示して headroom なしで起動する

`j-pi` も起動のときに同じ手順で proxy を用意する（Pi 自身の通信は通さず、Codex の worker が準備のできた proxy を使えるようにするため）。
`j-cc` と `j-pi` は起動のたびに dashboard の URL（`http://127.0.0.1:<port>/dashboard`）を表示し、その起動で proxy を新しく立てたときだけブラウザで開く。
ブラウザで開かないようにするには `JEV_HEADROOM_DASHBOARD=off` を付けて起動する（URL は表示する）。
あとから開くには `just headroom-dashboard` を使う（素の `headroom dashboard` は既定のポート 8787 を開くので、この proxy の dashboard は開けない）。

proxy は `j-cc` が終わっても残り、次の起動で使い回す（起動にかかる数秒は初回だけ）。
使わないときは `JEV_HEADROOM=off` を付けて起動する。
セッションの途中で proxy が止まると、そのセッションはモデルに届かなくなるので、`j-cc` を起動し直す（新しい proxy が立つ）。
`j-cc` をほぼ同時に 2 つ起動すると、proxy が 2 つ立つことがある（それぞれ自分の proxy を使う）。

headroom の版は固定してあり（`config/mise/config.toml`）、上げるのは手作業である。
上げたら `just doctor` で 2 つの約束を確かめる。
`headroom-telemetry` は、headroom 自身が beacon を off と答えるか（`headroom telemetry --json`）を見る。
`headroom-cli` は、`headroom proxy --help` に `jev_headroom.proxy_command` が渡すフラグが載っているかを見る。
`/health` の答えの形は、proxy が動いていれば `headroom-proxy` が確かめる（形が変わると、`j-cc` は proxy を待ったあと headroom なしで起動する）。
Codex の worker の経路は、`just jev-headroom-verify` で確かめる。

`headroom init` と `headroom wrap` は、Claude や Codex の設定そのものに proxy への経路を書き込む。
すると素の `claude` や `codex` も proxy なしでは動かなくなり、Claude は Remote Control も使えなくなるので、ここでは使わない。
書き込まれると `just doctor` の `headroom-routing` が知らせるので、`headroom unwrap claude` か `headroom unwrap codex` で外し、`just sync-agents` を実行する。

proxy を止めるときは、記録したファイルに頼らず、自分の headroom の proxy をコマンドラインで探して止める。
止めた proxy を使っている `j-cc` のセッションは、モデルに届かなくなる。

```sh
pgrep -u "$USER" -af 'headroom proxy --host 127\.0\.0\.1'   # macOS と Linux: 一覧
kill <PID>
```

```powershell
# Windows: headroom.exe の下に python.exe が 2 つ動くので、親ごと止める
Get-CimInstance Win32_Process | Where-Object CommandLine -match 'headroom.*proxy --host 127\.0\.0\.1' | Select-Object ProcessId, ParentProcessId, Name
taskkill /T /F /PID <headroom.exe の ProcessId>
```

## rtk と headroom を両方使う

rtk はコマンドの出力を圧縮し、headroom はモデルに届く内容を圧縮する。
両方とも mise で入る基盤の道具で（ADR 0047）、効く範囲は起動のしかたで決まる。

| 起動のしかた | rtk | headroom の proxy | headroom の MCP サーバー |
| --- | --- | --- | --- |
| `j-cc`（Claude Code） | 効く（Bash の hook） | 通す（セッションと worker） | 使える |
| 素の `claude` | 効く | 通さない（Remote Control を残すため） | 使える |
| `j-pi`（Pi 自身） | 効く（Pi の bash の拡張） | 通さない（上の理由） | なし |
| `j-pi` から起動する Codex の worker | 効かない | 通す | なし |
| 素の `codex` | 効く（Codex の hook） | 通さない | なし |

`j-pi` の Codex の worker は `--ignore-user-config` で起動するので、Codex は利用者の `hooks.json` を読まない。
そのため rtk も、dotfiles の guard の hook も、この worker には効かない。

両方を使えるようにする手順は次のとおりである（`just deploy` は、headroom の MCP サーバーの登録と Codex のプラグインの導入も行う）。

```sh
just deploy
just harden-env                              # 両方の telemetry を off にする（Windows は User の環境変数にも書く）
just sync-agents && just sync-agents a b c d x   # Claude と Codex の hook を配り、Codex の hook を信頼済みにする
just doctor                                  # AI の節がすべて OK になるまで、表示される手順に従う
```

proxy は 1 つで足りる。
`j-cc` と Codex の worker は、記録ファイル（`~/.cache/jev/headroom.json`）を通して同じ proxy を使い回し、動いていなければ起動のときに自動で立てる（上の「headroom」の節）。
ログインのときに常駐させる仕組みは置かない（使うのは `j-cc` と `j-pi` の Codex の worker だけで、起動の仕組みを 2 つにしないため）。

両方が 1 つのセッションで効いていることは、次で確かめる。

```sh
just jev-headroom-verify rtk   # j-cc と同じ環境のセッションが proxy を通り、その Bash が rtk を通る
rtk gain                       # rtk が圧縮したコマンドの数と、減らせたトークン
headroom savings               # headroom が減らしたトークン（proxy をまたいで 30 日分）
```

headroom を使うときに、利用者がすることは 2 つだけである。

- モデルに届く内容を圧縮したいセッションは、`j-cc` で起動する（proxy は自動で用意される）
- どの Claude のセッションでも、headroom の MCP の道具（`mcp__headroom__headroom_compress`、`…_retrieve`、`…_stats`）が使える

全体の状態は `just doctor` の AI の節で見る。
`headroom doctor` は、headroom 自身の配線（`headroom wrap` や `headroom init` が Claude と Codex の設定に proxy を書き込む形）を前提にしている。
そのため、この環境では claude と codex を「not routed」と表示し、`headroom wrap claude` を勧めるが、それには従わない（素の `claude` も proxy を通るようになり、Remote Control が使えなくなる）。
`headroom doctor` を使うなら、記録したポート（`~/.cache/jev/headroom.json` の `port`）を `-p` で渡し、`proxy` と `version` の行だけを見る（既定の 8787 には proxy がいないので、`proxy` は失敗と出る）。

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
| `BLOCKED` | 2 | 提供元のエラーイベントで利用上限を確認した、または CLI が未ログインで終了した（結果イベントが `Not logged in`）。リセット後かログイン後にやり直す。会話の中の引用は対象外。Codex のプラグインが入っていない機体では、`codex:codex-rescue` の呼び出しに Claude Code が `not found` を返すので、Codex の経路だけ確かめられずにこれになる（worker の結果は理由に併記する） |
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
| `BLOCKED` | 2 | キーか拡張がない、利用上限で worker の前に止まった、2.6.9 より古い pi-background-tasks が anthropic の Sonnet 5.5 を拒んだ（`no Claude Code model policy`）、またはモデルが subagent を呼ばなかった（提供元のエラーがないときだけ、1 回自動でやり直す）。上限と拒否は、Pi が終了コード 0 で終わっても、セッションの記録に残る提供元のエラーから判定する |
| `PARTIAL` | 3 | worker が `medium` で動き、セッションと区別できない |

### headroom の経路

`j-cc` のセッションと worker、Codex の worker が headroom を通ることは、次で確かめる。

```sh
just jev-headroom-verify          # 3 つすべて
just jev-headroom-verify codex    # Codex の worker だけ（Jev のキーがなくても動く）
just jev-headroom-verify rtk      # 1 つのセッションで headroom と rtk の両方（Jev のキーがなくても動く）
```

確認のためだけの proxy を空いているポートで起動し、リクエストのメッセージを一時ディレクトリのログに残す（終わったら proxy を止め、ログごと消す）。
その proxy に向けて、`j-cc` と同じ環境とフックで非対話（`claude -p`）のセッションを 1 回動かし、素の worker を 1 つ起動させる。
判定は、proxy のログ（セッションと worker の最初のメッセージの目印）とフックの記録で行い、モデルの返答には頼らない。
Codex の確認では、本物の `jev_codex_exec.py` を動かし、記録ファイル（`JEV_HEADROOM_STATE_DIR`）で確認用の proxy を再利用させる。
headroom は Codex の（Responses API の）リクエストのメッセージをログに残さないが、client を `codex` と記録するので、それを数える（確認用の proxy を使うのは、この runner だけである）。
`rtk` の確認では、`j-cc` と同じ環境のセッションを空の一時ディレクトリで動かし、Bash で `ls -la` を 1 回実行させる。
proxy のログにそのセッションのリクエストがあり、rtk 自身がそのディレクトリで数えたコマンド（`rtk gain -p`）が 1 件以上あれば `PASS` である（後者を増やせるのは Claude の rtk の hook だけである）。

| 結果 | 終了コード | 意味 |
| --- | --- | --- |
| `PASS` | 0 | セッションと、`worker-<effort>` に差し替えた worker のリクエストが、両方とも proxy を通った |
| `FAIL` | 1 | proxy が起動しない、セッションか worker のリクエストが proxy を通らない、フックが差し替えを記録しない、または Bash のコマンドが rtk を通らない |
| `BLOCKED` | 2 | キー、headroom、rtk がない、利用上限、未ログインかログインの期限切れ（`claude` を起動して `/login`）、またはモデルが worker を起動しなかったか Bash を実行しなかった |
