# エージェント指示の配布（sync-agents）

このリポジトリは、すべてのエージェントに共通する global な指示の正本を持ち、`just sync-agents`（`scripts/sync_agents.py`）で各エージェントの設定ディレクトリに配る。
`scripts/sync_agents.py`、`ROOT_*` のファイル、`.claude/settings.*.json` を変える前に読む。

## 正本のファイル

正本は repo root に置き、`ROOT_*` という目印の名前にして、エージェントが直接読まないようにする。

- **base**：`ROOT_AGENTS.md`。どのエージェントでも常に読まれる短い指示
- **overlay**：`ROOT_CLAUDE.md`。Claude 専用で、先頭の `@AGENTS.md` で base を読み込む
- **spoke**：`ROOT_AGENTS_docs_agents_*.md`。必要なときだけ読む詳細（TDD、commit、Python など）
- **hooks**：`ROOT_AGENTS_hooks_*` と、それを登録する `.claude/settings.hooks.json`。hook による機械的な強制。hook の正本はこの 1 つで、Codex 向けの登録は sync がここから作る
- **settings の断片**：`.claude/settings.shared.json`、`.claude/settings.shared.{macos,linux,windows}.json`、`.claude/settings.profiles/<key>.json`（ADR 0037）

`ROOT_AGENTS_<x>_<y>` という名前のファイルやディレクトリは、`<agent>/<x>/<y>` に配る（`_` を `/` に読み替える）。

## 配布先

| 正本 | 配布先 |
| --- | --- |
| base | `~/.codex/AGENTS.md`、`~/.gemini/GEMINI.md`、`~/.claude*/AGENTS.md` |
| overlay | `~/.claude*/CLAUDE.md` |
| spoke | `<agent>/docs/agents/*` |
| hooks | Claude 系（`~/.claude*`）と Codex（`~/.codex`） |
| settings | Claude 系だけ |

`~/.gemini/GEMINI.md` は、Gemini CLI と Antigravity CLI（`agy`）が共有する global な指示である（google-gemini/gemini-cli#16058）。
既存の gemini への配布が、そのまま Antigravity を兼ねる。

base の中の `docs/agents/` への参照は、配布のときにその home の絶対パスへ書き換える。
相対パスのままだと、作業中のプロジェクトの側で解決されて外れるからである。

配布先を直接編集しても、次の sync で上書きされる。
global な規則を変えるときは、正本を編集して `just sync-agents` を実行する。

## hooks と settings.json の併合

settings.json は利用者のキーを壊さないよう、その場で併合する（配布の manifest では追跡しない）。

sync が所有する hook の block は、すべての command が `<agent>/hooks/` を指すか、agent-hook（`docs/plan/agent-hooks-go.md`）の実行ファイルを実行するものだけである。
実行ファイルは、home ごとの安定パス `.../dotfiles/agent-hooks/current/<home>/agent-hook`（版への symlink）である。
Codex では、版の `.../dotfiles/agent-hooks/releases/<版 ID>/agent-hook` も、位置を保つ併合が入る PR 3d.2 までは所有する。
Claude の handler が版を直接指していたら、それは利用者のものとして残す（sync は安定パスしか書かない）。
render が受け付けるパスも同じで、harness の `registration.layouts`（`stable` と `release`）が決める。
Windows では名前が `.exe` で終わり、POSIX では終わらない。
数えるのは、render がその harness に描く形で、絶対パスのその実行ファイルをプログラムとして実行する handler だけである（`_runs_agent_hook_release`）。
形は、Claude では exec 形式（`args` があり、`command` がパスそのもの）だけ。
Codex では sh の `'...'`（`'` は `'\''`）、PowerShell の `& '...'`（`'` は `''`）、cmd の `"..."` の 3 つだけ。
プログラムは command の先頭に置き、その後は ASCII の空白 1 つか command の終わりである（render が書くとおり。sh は空白・タブ・改行でしか語を分けないので、NBSP などはプログラム名の一部になる）。
プログラムより後ろは比べない（雛形を変えても、前の雛形で描いた handler を所有し続け、revert しても重複しない）。
render が書かない member を持つ handler は、command が `<agent>/hooks/` を指していても数えない（Claude は `type`・`command`・`args`・`timeout`・`onFailure`、Codex は `type`・`command`・`timeout` だけを書く。Codex の `commandWindows` は Windows で実行するものを変える）。
harness がパス以外として読む文字を含むパスは数えない。

- cmd の `%` と `!`。
- Claude の exec 形式の `${`。
- PowerShell の `‘` `’` `‚` `‛`（単引用符として読む）と `*` `?` `[` `]`（パスが無いとワイルドカードとして別の実行ファイルを探す）。
- 制御文字。

Windows のパスは `\` と `/` を同じ区切りとして比べ、POSIX のパスは書いたとおりに比べる（POSIX では `\` はファイル名の文字）。
引数、代入、リダイレクトでそのパスに触れるだけの command は、利用者のものとして残す。
その block は毎回、最新の断片で置き換える（hook のコマンドを変えても、古い block が重複して残らない）。
利用者が作った block は残す。
`<agent>/hooks/` のファイルのうち、先頭に第三者のインストーラの見出し（`# installed by herdr` など、`THIRD_PARTY_HOOK_HEADERS`）があるものは、そのインストーラのものとして扱う。
そのファイルは消さず、それを呼ぶ block も置き換えない。

settings の断片は、hook の併合の直後に 4 つの層を合成して 1 つの状態にし、settings.json へ併合する。
後の層が勝つ。

1. `settings.shared.json`：すべての OS とプロファイル
2. `settings.shared.<os>.json`：実行している OS（ファイルがなければ空）
3. `settings.profiles/<AgentTarget.key>.json`：プロファイルごと
4. `<agent home>/settings.sync-local.json`：その機体だけの最後の上書き（git では追跡しない）

- `env` は、合成したあとの内容で丸ごと置き換える（断片から消えたキーは settings.json からも消える）。機体固有の `env` は 4 に書く。`settings.local.json` はプロジェクトのスコープでしか読まれないので、user スコープの逃がし先にならない。
- `settings` の中は、キーごとに後の層が勝つ。両方が dict のときだけ、1 段だけ深く併合する（shared の `permissions.deny` を残したまま、プロファイルが `permissions` の別のキーを足せる）。
- settings.json には、トップレベルのキーを追加か更新だけする（`enabledPlugins` など、断片にないキーは残す）。
- 断片から外したトップレベルのキーは、その断片の `retired` に書く（例：`.claude/settings.profiles/work-c.json`）。`retired` は移行 ID ごとに、キーと、断片がそれまでに書いた値をすべて並べる。sync は各 home で移行を 1 回だけ評価し、キーがまだそのどれかの値なら消す。評価した ID は、settings.json より先に home の `settings.sync-state.json`（sync が所有する）へ記録する。そのため、あとで利用者が同じ値を設定し直しても消さない。初回の評価の時点で利用者が同じ値を選んでいた場合は区別できないので、残したい値は 4 に書く。
- `env` の正本は断片である。repo の `.claude/settings.json` は `env` を持たず、global から受け継ぐ。

## hook を変えるとき

hook の正本は `ROOT_AGENTS_hooks_*.sh` と、command guard の `ROOT_AGENTS_hooks_block-prohibited-commands.py` である。
unit test は `tests/unit/test_agent_hooks.py` にある。
配布先の `~/.claude/hooks/*` を直接編集しても、次の sync で上書きされる。
正本を直し、test を足してから `just sync-agents` を実行する。

command guard、files guard、secrets guard には Go への移植がある（`tools/agent-hooks`、計画は `docs/plan/agent-hooks-go.md`。まだどの harness にも配線していない）。
binary `agent-hook <harness> pre --hook <id>`（guard と rtk）と `agent-hook <harness> post --hook formatter` は、Claude、Codex、agy の payload を読んで、それぞれの harness が読む形で答える（agy は guard と formatter だけ）。
Pi には、Pi の中で動く拡張（shim、PR 4 で配る）が shim protocol（`tools/agent-hooks/shim/`）の request を送り、binary は同じ protocol の形で答える（guard と formatter と rtk。rtk は vendored の `config/pi/extensions/rtk.ts` と同じ振る舞いで、その振る舞いを `just pi-rtk-corpus` で corpus にしてある）。
Pi は tool の path を書く前に解決するので、binary も同じに解決したファイルを判定する（`tools/agent-hooks/internal/pipath`。Pi 1.4.0 自身の答えを `just pi-paths-corpus` で corpus にしてある）。
元の guard と同じ判定をすることを、`tools/agent-hooks/internal/guardcorpus/` の corpus で確かめている。
harness ごとの定義（payload の schema、答え、hook ごとの対応状況）は `tools/agent-hooks/harnesses/` にある（`README.md` が書き方を説明する）。
同じ scenario を全 harness に通す conformance suite（`tools/agent-hooks/internal/conformance/`）が、定義の誤りを知らせる。
binary は実行ごとに、決まった値だけの行を 1 行ずつ `$XDG_STATE_HOME/dotfiles/agent-hooks/logs/<UTC の日付>.jsonl`（既定は `~/.local/state/...`）に書く（path、command、内容は書かない。Windows ではまだ書かない）。`just agent-hooks-log` が直近の行を表で出す。
`just agent-hooks-build` が、この機体向けの binary を再現できる release として `~/.local/share/dotfiles/agent-hooks/releases/<release ID>/agent-hook` に作る（`agent-hook selftest` を通ったものだけ。同じ場所への build は 1 つずつ走る。Windows ではまだ作らない）。`just agent-hooks-build check PATH` は作り直して bytes を比べる。Claude の home を release に配線する手順は、下の「agent-hook の配線（Claude）」にある。Codex はまだ配線しない（PR 3d.2）。
guard、rtk の hook、formatter かその test、または `guard-codex.sh` を変えたら corpus を書き直し、Go 側も同じ判定に直す。
command guard は `just command-guard-corpus`、files guard と secrets guard は `just file-guards-corpus`、binary に通す payload は `just hook-payload-corpus`、rtk の hook と formatter は `just tool-hooks-corpus` で書き直す。
`tests/unit/test_command_guard_corpus.py`、`tests/unit/test_file_guards_corpus.py`、`tests/unit/test_hook_payload_corpus.py`、`tests/unit/test_tool_hooks_corpus.py`、Go の test が、ずれを知らせる。
旧スクリプトのバグは binary で直す（所有者の決定、2026-11-04）。
直し方は旧スクリプトへの名前付きの修正として `scripts/old_script_fixes.py` に置き、corpus を書き直すときは旧スクリプトと直した版の両方を走らせる。
答えが違う所は `fixed-<名前>` の差分 ID になり、binary は直した版の答えを返す。
どの差分 ID にも種類と理由があることを `tests/unit/test_corpus_differences.py` が確かめ、Go の corpus の test は `parity/` と差分 ID の名前で subtest を分ける（`go test -run '/fixed-'` で直した所だけを見られる）。
旧スクリプトでは再現できない修正（hook の panic で guard が止める、など）は binary だけの修正として同じ test に登録し、それを確かめる Go の test を名指しする。

1 つの hook だけを試すには、JSON を標準入力で渡す。
`exit=2` は止める、`exit=0` は通すという意味である。

```sh
echo '{"tool_input":{"command":"npm install"}}' | bash ~/.claude/hooks/block-prohibited-commands.sh; echo "exit=$?"
echo '{"tool_input":{"file_path":"config.yml"}}' | bash ~/.claude/hooks/block-prohibited-files.sh; echo "exit=$?"
```

## agent-hook の配線（Claude）

macOS、Linux、WSL では、`just sync-agents` が Claude の home（`claude`、`work-a`〜`work-d`）を agent-hook の binary に配線する。
登録は home ごとの安定パス `~/.local/share/dotfiles/agent-hooks/current/<home>/agent-hook`（release への symlink）を exec 形式で指す。
native Windows はまだ配線せず、今のスクリプトを登録したまま、そう 1 行出す。
Codex（`hooks.json`）は PR 3d.2 まで今のままである。

1 回の sync は、次の順に進む（`scripts/agent_hook_sync.py`）。

1. `~/.local/state/dotfiles/agent-hooks/switch.lock` をとる（30 秒待って取れなければ、持ち主を名指しして止まる）。`hookrelease switch`、install、uninstall、gc も同じロックをとる。
2. 前の run が残した変更の記録（`switch-<home>.json`）をすべて片付け、記録ごとに何をしたかを 1 行出す（終わっていれば確かめて消し、途中なら元に戻す）。片付かない記録があれば、そこで run 全体が止まる。
3. settings の断片（`settings.shared.json`、OS 版、profile、各 home の `settings.sync-local.json`）が `hooks` を持っていたら、何も書かずに止まる。
4. release を作って確かめる（`hookrelease build` と `check`）。Go が無いか失敗したら、release なしで進む。
5. home ごとに、読み直した状態から計画を立て、書く直前にもう一度読んで確かめる。状態を読めない home（壊れた `settings.json`、`hooks` が配列でないなど形の違うもの、link の場所にあるただのファイル）は、その home だけが止まる。

計画は次のどれかで、home ごとに 1 行出す（`scripts/agent_hook_plan.py`）。

- `register`：登録を release の描く形に書き換える（初めての配線、雛形の変更、配線済みの home に rtk 自身の hook `rtk hook claude` が戻ったとき。併合がそれを外す）。
- `link`：登録はそのまま、link だけ新しい release へ移す。
- `nothing`：変えるものが無い。
- `keep`：release が無いが、配線は残す（`hooks` は何も変えない。位置も、rtk 自身の hook も）。
- `scripts`：release が無く、まだ配線していない home は、今のスクリプトのまま。
- `uninstalled`：uninstall の印がある home は、今のスクリプトのまま。
- `stop`：印があるのに配線されているなど、人が決める状態。その home の hook の登録は変えない（ファイルの配置と共有設定の併合はする）。ほかの home は進め、run は exit 1 で終わる。

登録を書き換える変更（register、install、unregister）は、link、`settings.json`、uninstall の印を 1 つの変更として記録しながら進める（`scripts/agent_hook_wiring.py`）。印は変わらない変更（register）でも記録し、どの段でも確かめる（途中で印が作られたら止まる）。
途中で止まっても、次の run が元か新しい状態のどちらかにそろえる。
戻すときは `settings.json` の `hooks` の値だけを戻し、ほかのキー（sync の共有設定や、他のプログラムが書いた値）は今のまま残す。変更の前に `settings.json` が無かった home でも、ファイルは消さず、`hooks` の無いファイルが残る。
link は消さない。設定の再読み込みを取りこぼした Claude の session も、link をたどれる。
変更の途中で他のプログラムが `hooks` を書き換えていたら、記録を残して止まる。
`settings.json` は 1 回だけ書く（hook の部分と共有設定の併合をまとめた値。`settings.sync-state.json` を先に書く）。
登録の変更が終わらなかった home（戻した、破棄した、止まった）では、そのあと何も消さない。戻した登録が名指すスクリプトを消さないためである。
macOS では、書いたものを `F_FULLFSYNC` でディスクまで届ける（`fsync` はドライブのキャッシュで止まる）。

- `just agent-hooks-uninstall <home>...`：今のスクリプトの登録に戻し、home に印を付ける。印のある home は、sync してもスクリプトのままである。link と release は残す。release が無くても動く。
- `just agent-hooks-install <home>...`：印を消して配線し直す。release が要る。
- `just agent-hooks-gc [--delete]`：どこからも指されていない release を一覧する。指しているとみなすのは、各 home の link と、Claude と Codex の登録ファイルか変更の記録のどこかに ID が現れる release である（`$HOME`、`~`、`cd` のあとの相対パス、変数で組み立てた名前で書いたものも含む。迷えば残す）。消すのは `--delete` のときだけで、消す直前にもう一度確かめる。PR 3d.2 までは、Codex が動いている間は `--delete` を断る（消すたびに確かめ直す）。
- `just agent-hooks-test-installed [home]`：その home の link が指す release を `hookrelease check` で確かめてから、agent-hook のプロセステストを当てる。
- `just sync-agents-preview`：ロックも書き込みもせず、release も作らない。今ある release で計画を見せ、作らないと分からないことは不明と出す。
- doctor は、印のある home を INFO、残った記録を WARN で出す。

Claude の home では、sync が所有するのは安定パスの登録だけである。release を直接指す block は、利用者のものとして残す。
`scripts/sync_agents.py` は uv の project の環境で走る（PEP 723 の script ではない）。

## Codex の hooks

Codex は `<codex home>/hooks.json` を読む。
block の形は Claude と同じで、shell の tool は `Bash`、apply_patch は `Write|Edit` に一致する。
sync は `.claude/settings.hooks.json` から Codex 向けの断片を作り（`codex_fragment_from_claude`）、Claude の settings.json と同じ所有の規則で併合する。rtk のインストーラが書く block（`RETIRED_HOOK_COMMAND`）は外す。
断片は command だけを書き換える。`block-*` のガードは `guard-codex.sh` を通し、`-claude.` のスクリプトは `-codex.` の対に替え、ほかはそのまま動かす。
repo に `.codex/hooks.json` は置かない。Codex は trusted なプロジェクトの `.codex/hooks.json` も読むので、置くとこの repo の中で hook が 2 回動く（`just codex-hooks-trust --check` と doctor の `codex-hooks` が検出する）。
hook のファイルは名前で振り分ける。
名前に `-claude.` を含むファイルは Claude 系だけに、`-codex.` を含むファイルは Codex だけに配る。

exit 2 で止める guard（`block-*.sh`）は、Codex では `guard-codex.sh <guard>` を通して呼ぶ。
Codex は hook をセッションの shell で起動し、Windows ではそれが `pwsh -Command` になる。
pwsh は 0 以外の exit をすべて 1 として返すので、guard の exit 2 は Codex に失敗した hook として届き、失敗した hook は素通しになる。
`guard-codex.sh` は guard の exit 2 と stderr を、stdout の `permissionDecision: "deny"` に変える。
stdout はどの shell も通すので、OS を問わず block が効く。
guard の側は Claude の exit code の約束のまま変えない。

Codex は、hash を信頼済みとして記録した hook だけを実行する（`~/.codex/config.toml` の `hooks.state`）。
sync は `~/.codex` に配ったあと `scripts/codex_hooks_trust.py` を実行し、Codex の app-server（`hooks/list` と `config/batchWrite`）を通して、断片から作った hook だけを信頼済みにする。
配った hook のファイルが正本と 1 byte でも違うときは信頼しない。
`just codex-hooks-trust --check` は書き込まずに状態を表示する。
Windows では、続けて `scripts/codex_sandbox_tools.py` を実行し、Codex の sandbox が mise の道具（rtk など）を実行できるようにする（`docs/runbook/windows-host.md`）。
`just doctor` と `just status` も同じ検査を含む。

## sync が配らないもの

**skill**：自作（hironow/skills）もサードパーティも、`bunx skills` CLI の store（`~/.agents/skills`）に入れ、git は宣言の `dump/harness/skill-lock.json` だけを追跡する（ADR 0043）。
各 home の `skills/` には、`just skills-place` が store への相対 symlink を張る（張れなければ追跡つきのコピー）。
CLI には `-a universal` で store だけを書かせ、home には触らせない。
同名の skill は hironow/skills が優先される（`just skills-lock-check` が `just ci` の中で検査する）。
宣言は公開されるので、`just dump-skills-lock` は `gh` で非公開と分かった source の skill を宣言に入れない。公開か確かめられない source があるときは、何も書かずに失敗する。

- `just dump-skills-lock`：store から宣言を作り直す（hironow/skills の記録が消える変更は拒む）
- `just restore-skills-lock`：新しい機体で、宣言から store を復元して配置する
- `just skills-update`：hironow/skills の merge 後などに、store を更新して配置する

**EGM**：通常のstore管理skillではなく、参照先を含む完全なplugin/packageとして配る。
`just egm-install` は `sync-agents all` でこの補足を各homeへ先に配り、EGMだけをネイティブCLIで導入する。
このsyncには既存の共通settingsとhooksの配布も含まれるので、先に `just sync-agents-preview all` を確認する。
Piは固定したgit packageを使い、既存installerが同じ補足とread-only reviewerを置く。
Piのglobal context fileでは、EGM用のマーカー内だけを管理して他の本文を残す。
EGMのskillを `bunx skills` で切り離して導入しない。
導入順序、ローカル方針との優先順位、レビュー分離の限界は [EGM runbook](runbook/egm.md) にある。

**Claude Code のプラグイン**：settings の断片は `enabledPlugins` と `extraKnownMarketplaces` を持たない（ADR 0037。plugin CLI が書き換えるため）。
全 home 共通のプラグインは `dump/harness/claude-plugins.json` に宣言し、`just deploy`（単独では `just claude-plugins-install`）が plugin CLI で各 home に入れる（ADR 0048、ADR 0056）。
marketplace はタグで固定する。例外は、タグの無い claude-plugins-official（追従）と、repo 相対パス（`./`）で書く dotfiles 自身の hironow-plugins である。
共通セットには home ごとの設定が要らない plugin だけを置き、script は設定項目に default の無い plugin を doctor でも WARN にする（ADR 0057）。
LSP の plugin は起動コマンドの名前しか持たないので、コマンドは mise で入れる（`config/mise/config.toml`）。typescript-lsp は、workspace の `node_modules` に `tsserver.js` を持つ TypeScript（6 系まで）がある場所でだけ動く（TypeScript 7 には `tsserver.js` が無い）。script は各 home の marketplace manifest から LSP のコマンドを集め、PATH に無いか、バージョンの問い合わせ（既定は `--version`、gopls は `gopls version`）に答えないものを doctor で WARN にする。
宣言の `disabled` は毎回、`retired` は移行 ID ごとに home で 1 回だけ無効にし、済んだ移行と schema の読み取り結果を home の `claude-plugins.sync-state.json` に記録する（install のときだけ書く）。
sync はこの 2 つのキーを書き換えない。

**Antigravity CLI（`agy`）の skill、settings、MCP**：Antigravity は、skill を `agy plugin`（`~/.gemini/antigravity-cli/plugins/<name>/skills/`）で、settings と MCP を `agy import`（`~/.gemini/antigravity-cli/settings.json` と `mcp/`）で自分で管理する（ADR 0026）。
これらを直接配ると、その自己管理を迂回して上書きしてしまうので、dotfiles は触らない。
共有するのは指示の層（`~/.gemini/GEMINI.md`）だけである。
`~/.gemini/skills/` は `skills-place` の配置先だが、Antigravity は `plugins/` から読むので使われない（害もない）。

## 実行

```bash
just sync-agents            # ~/.claude だけ（既定）
just sync-agents p a b      # 名指しした home だけ（p は ~/.claude）
just sync-agents all        # すべてのエージェント
just sync-agents-preview …  # 書き込まずに差分を見る
```

名指しすると、既定の `~/.claude` は対象から外れる。
`just sync-agents a b` は `~/.claude-work-a` と `-b` だけに配るので、`~/.claude` も要るときは `p` を足すか `all` にする。
