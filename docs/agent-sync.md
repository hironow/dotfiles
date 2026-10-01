# エージェント指示の配布（sync-agents）

このリポジトリは、すべてのエージェントに共通する global な指示の正本を持ち、`just sync-agents`（`scripts/sync_agents.py`）で各エージェントの設定ディレクトリに配る。
`scripts/sync_agents.py`、`ROOT_*` のファイル、`.claude/settings.*.json` を変える前に読む。

## 正本のファイル

正本は repo root に置き、`ROOT_*` という目印の名前にして、エージェントが直接読まないようにする。

- **base**：`ROOT_AGENTS.md`。どのエージェントでも常に読まれる短い指示
- **overlay**：`ROOT_CLAUDE.md`。Claude 専用で、先頭の `@AGENTS.md` で base を読み込む
- **spoke**：`ROOT_AGENTS_docs_agents_*.md`。必要なときだけ読む詳細（TDD、commit、Python など）
- **hooks**：`ROOT_AGENTS_hooks_*` と、それを登録する `.claude/settings.hooks.json`（Claude）と `.codex/hooks.json`（Codex）。hook による機械的な強制
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

sync が所有する hook の block は、command がすべて `<agent>/hooks/` を指すものだけである。
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

## Codex の hooks

Codex は `<codex home>/hooks.json` を読む。
block の形は Claude と同じで、shell の tool は `Bash`、apply_patch は `Write|Edit` に一致する。
sync は `.codex/hooks.json` の断片を、Claude の settings.json と同じ所有の規則で併合し、rtk のインストーラが書く block（`RETIRED_HOOK_COMMAND`）は外す。
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

- `just dump-skills-lock`：store から宣言を作り直す（hironow/skills の記録が消える変更は拒む）
- `just restore-skills-lock`：新しい機体で、宣言から store を復元して配置する
- `just skills-update`：hironow/skills の merge 後などに、store を更新して配置する

**Antigravity CLI（`agy`）の skill、settings、MCP**：Antigravity は、skill を `agy plugin`（`~/.gemini/antigravity-cli/plugins/<name>/skills/`）で、settings と MCP を `agy import`（`~/.gemini/antigravity-cli/settings.json` と `mcp/`）で自分で管理する（ADR 0026）。
これらを直接配ると、その自己管理を迂回して上書きしてしまうので、dotfiles は触らない。
共有するのは指示の層（`~/.gemini/GEMINI.md`）だけである。
`~/.gemini/skills/` は `skills-place` の配置先だが、Antigravity は `plugins/` から読むので使われない（害もない）。

## 実行

```bash
just sync-agents            # ~/.claude だけ（既定）
just sync-agents a b        # ~/.claude-work-a と -b も
just sync-agents all        # すべてのエージェント
just sync-agents-preview …  # 書き込まずに差分を見る
```
