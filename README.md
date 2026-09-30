# dotfiles

Zsh、mise、just などの設定と、それを Mac、Linux、Windows、Dev Container、Coder workspace に配る仕組みをまとめたリポジトリ。

## 構成

3 つの環境が、同じ正本（`config/mise/config.toml`、`.devcontainer/devcontainer.json`、`install.sh`）から同じバージョンの道具を入れる。
OS ごとに違うのは、導入の経路だけである。

```
   +---------------+     +-----------------+     +------------------+
   |   Mac host    |     |  Dev container  |     |  Coder workspace |
   |  (daily       |     |  (CI sandbox    |     |  (exe.hironow.   |
   |   driver)     |     |   + IDE)        |     |   dev)           |
   +-------+-------+     +--------+--------+     +---------+--------+
           |                      |                        |
   brew + mise          devcontainer.json         docker pull prebuilt
   (just deploy)        + features/                image (Artifact Reg.)
                        dotfiles-tools             then docker run
                                                   (--volume /home:/root)
           |                      |                        |
           +----------+-----------+------------+-----------+
                                              |
                                              v
                          +-------------------------------------+
                          |  Single source of truth (this repo) |
                          |                                     |
                          |  - install.sh        (OS dispatch)  |
                          |  - config/mise/config.toml (pins)   |
                          |  - .devcontainer/    (image SoT)    |
                          |  - dump/<host>/      (brew/gcloud)  |
                          +-------------------------------------+
```

凡例:

- Mac host: 普段使いの機体（日常の作業機）
- Dev container: CI と IDE が共有するサンドボックス（CI とエディタの実行環境）
- Coder workspace: exe.hironow.dev 上の作業環境（リモート開発環境）
- install.sh (OS dispatch): `uname` で mac / linux / windows を振り分ける（OS 判定。ADR 0005）
- config/mise/config.toml (pins): just、uv、prek、vp、markdownlint-cli2、node と 5 つの AI CLI（codex、antigravity、claude、copilot、pi）のバージョンを 3 OS で揃える（バージョン固定。ADR 0006）
- Artifact Reg.: main への merge で GitHub Actions が push した image を、Coder の VM が pull する（イメージ置き場）

関連文書:

- [`docs/adr/`](./docs/adr/): 設計判断の記録（ADR）
- [`docs/runbook/jev-launchers.md`](./docs/runbook/jev-launchers.md): Jev を使った `j-cc` / `j-pi` の手順
- [`exe/docs/architecture.md`](./exe/docs/architecture.md): exe.hironow.dev の全体図（Cloudflare、Tailscale、Coder、GCP）
- [`exe/docs/runbook.md`](./exe/docs/runbook.md): exe.hironow.dev の運用手順
- [`exe/coder/templates/dotfiles-devcontainer/README.md`](./exe/coder/templates/dotfiles-devcontainer/README.md): Coder template の push と作成
- [`exe/scripts/README.md`](./exe/scripts/README.md): `cdr`（Cloudflare Access のサービストークン経由で `coder` CLI を実行するラッパー）
- [`tools/README.md`](./tools/README.md): RTTM 変換などの補助ツール
- `docs/intent.md`: いま取り組んでいる作業の意図（operator だけが書く。git では追跡しない）

## 導入

### Mac、Linux、WSL

`curl` と `git` があればよい。
Mac は Homebrew を先に入れておく。

```shell
bash -c "$(curl -fsSL https://raw.githubusercontent.com/hironow/dotfiles/main/install.sh)"

# 重い道具を省く場合
INSTALL_SKIP_HOMEBREW=1 INSTALL_SKIP_GCLOUD=1 INSTALL_SKIP_ADD_UPDATE=1 bash ./install.sh
```

`install.sh` は mise（固定版、SHA 検証つき、`~/.local/bin`）を入れ、道具を `mise install` し、設定を symlink する。
sudo は要らない。

WSL の素の Ubuntu では、続けて次を一度だけ行う。
`wsl-conf` と Docker の手順は sudo と、Windows 側での `wsl --shutdown` が要る。

```bash
just harden-env   # 機体ごとの供給網対策（npm と uv の 7 日の隔離、PyPI ミラー、GOPROXY）。追跡しない
just wsl-conf     # /etc/wsl.conf の差分と sudo での編集手順を表示する（Windows の PATH を入れない、systemd を有効化）

# WSL の中で Docker を動かす（just test と Dev Container のサンドボックス用）
sudo apt-get update && sudo apt-get install -y docker.io
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"   # 次の wsl --shutdown のあとで効く

just doctor       # 確認: PATH-windows が OK、docker に届く、道具がそろう
```

`just harden-env` は `~/.npmrc` と `~/.config/uv/uv.toml` を書き、個人の `exclude-newer` を設定する。
コミットする lock は `just relock-uv` で期間指定なしに保つ（ADR 0028）。

### Windows（native）

まっさらな機体に、PowerShell の 1 行で入る（ADR 0039）。

```powershell
# scoop の manifest を別の host のものにする場合は先に: $env:DOTFILES_HOST = '<host>'
irm https://raw.githubusercontent.com/hironow/dotfiles/main/bootstrap.ps1 | iex
```

bootstrap は scoop、git、just、jq、mise、pwsh を入れ、HTTPS で `~\dotfiles` に clone する。
続けて `add-scoop`、`deploy`、`harden-env`、`sync-agents`、`restore-skills-lock`、`doctor` を実行する（Windows の `harden-env` は、`%APPDATA%\uv\uv.toml` と、User の PATH にある Git の `usr\bin` と `cmd` も整える）。
何度実行しても安全であり、終わったら新しい pwsh を開く（`$PROFILE` はそこで効く）。

`just deploy` は Windows では次を行う。

- `starship.toml`、`gitignore-global`、`config/mise/config.toml` を置く（symlink ではなくコピー）
- pwsh の `$PROFILE` に、mise activate、starship init（mise の管理下なので mise activate より後）、`MISE_NODE_COREPACK=0`、`j-cc` / `j-pi` のブロックを書く
- mise の道具一式と、Pi の拡張を入れる
- `aliases.gitconfig` を `[include]` で読み込ませる

scoop の中身は `dump/<host>/scoop.json` に記録し、`just add-scoop` で復元する。
`tests/unit/` は native Windows でも通る（POSIX 専用の検査は skip する）。

SSH 鍵を設定したら、remote を SSH に替え、submodule を取得する（submodule は SSH の URL なので bootstrap は触らない）。

```powershell
git -C ~/dotfiles remote set-url origin git@github.com:hironow/dotfiles.git
git -C ~/dotfiles submodule update --init
```

## 日常の操作

```shell
just help                       # recipe の一覧

just sync-agents-preview        # エージェント指示の配布を試す（書き込まない）
just sync-agents                # ~/.claude などへ配る
just lint-claude                # 配る Claude 設定の検査（ADR 0029）

just update-all                 # 道具を更新する
just dump                       # 導入済みのパッケージを dump/<host>/ に記録する
just add-brew                   # macOS: 記録から復元する
just add-scoop                  # Windows: 記録から復元する（ADR 0032）

just self-check                 # 軽い健全性検査（with_tests=1 で Docker のテストも）
just doctor                     # 道具、PATH、Windows 固有の設定を診断する
just validate-path-duplicates   # PATH の重複を検査する

mx uv sync                      # mx は `mise exec --` の zsh alias
mx dotenvx run -- mise set      # 暗号化した .env を mise の環境に読む
gh do -- mise set               # GitHub の認証情報つきで同じことをする
mx dotenvx set HELLO World      # 暗号化して .env に書く
mx mise set WORLD=hello         # 暗号化せずに mise の環境に書く
```

### テストと CI ゲート

| コマンド | 内容 | Docker |
| --- | --- | --- |
| `just ci` | `just check`（Python、Go、shell、Markdown、JS/TS の lint、Pi 拡張のテスト、Go のテスト、Quint のモデル）、Claude 設定の検査、unit テスト、semgrep の規則テスト、IaC のテスト、portless の文書、指示量の予算、skill 宣言、emulator の lint、禁止トークン | 不要 |
| `just ci-all` | `ci` と Dev Container のサンドボックステストと `install.sh` の検証（単独では `just test-install`） | 要る |
| `just ci-emu` | emulator 群の lint、起動、高速テスト、e2e | 要る |
| `just check-all` | prek の hook と `ci-all`（push 前の最終ゲート） | 要る |
| `just test` | Dev Container の中のサンドボックステスト（`just test-mark marker=validate` のように install、validate、versions、deploy、check で絞れる） | 要る |

## Jev でのコーディングセッション

作業リポジトリで `j-cc '依頼文'` または `j-pi '依頼文'` を実行すると、依頼に合わせて Claude Code と Pi の思考レベル、Codex のモデルを選んで起動する。
キーの置き場所、初回準備、提供元の切り替えは [runbook](docs/runbook/jev-launchers.md) にある。

## skill

skill は、自作（[hironow/skills](https://github.com/hironow/skills)）もサードパーティも宣言で管理する（ADR 0038、ADR 0043）。
実体は skills CLI が `~/.agents/skills`（store）に置き、git は宣言の `dump/harness/skill-lock.json` だけを追跡する。
各エージェントの home（`~/.claude*`、`~/.codex`、`~/.gemini`）には、`skills-place` が store への相対 symlink を張る（張れない環境では追跡つきのコピー）。
同名の skill は hironow/skills が優先される（`just ci` の `skills-lock-check` が検査する）。

```bash
just restore-skills-lock  # 新しい機体: 宣言から store に復元し、home に配置する
just skills-place         # home の symlink を張り直す（冪等）
just skills-update        # hironow/skills の merge 後など: store を更新して配置する

# 追加: CLI には store だけを書かせ（-a universal）、宣言を更新してから配置する
bunx skills add <repo> -g -s <name> -y -a universal
just dump-skills-lock
just skills-place
```

`just dump-skills-lock` は、その機体の store 全体から宣言を作り直す。
store が宣言とずれていると無関係な差分も出るので、差分を確認してからコミットする。

サードパーティは、必要な skill だけを宣言する。

- `wandb/skills`: `wandb-autoresearch` と `wandb-eval-tables`
- `googleworkspace/cli`: `gws-shared` と主要 9 サービス（gmail、calendar、drive、docs、sheets、slides、tasks、forms、people）。`persona-*` と `recipe-*` は skill 一覧が長くなるので入れない
- `vercel-labs/agent-browser`（[使い方](https://github.com/vercel-labs/agent-browser?tab=readme-ov-file#agentsmd--claudemd)）

`just env=a skills ls -g` のように、`just skills` は `CLAUDE_CONFIG_DIR` を切り替えて CLI を呼ぶ（`env=p` は `~/.claude`、`a` から `d` は `~/.claude-work-a` から `-d`）。
参照だけに使い、追加には使わない（home に直接書き込み、store と宣言から外れるため）。

## ローカル開発スタック

`emulator/`（データストアとインスペクタの emulator）と `telemetry/`（OTel、Grafana、Loki、Prometheus、Tempo）はこのリポジトリにある（ADR 0014）。
API や SaaS の emulator は、vercel-labs/emulate を npx 経由で動かす（ADR 0016）。

```shell
just emu-up                          # 既定は GCP の中核だけ（firebase、spanner、pgadapter、postgres。別名 emu-up-lite）
just emu-up-only firebase-emulator   # 名指しで起動する（別リポジトリから Firebase だけ借りるときなど）
just emu-up-group search             # 中核に機能群を足す（bigtable search graph vector ml inspect exporters full）
just emu-up-full                     # 重いものも含む全データサービス（対話用の *-cli は除く）
just emu-check                       # 状態と接続先
just emu-stop                        # firebase のデータを書き出して止める

just tel-up                          # telemetry を起動する（止めるのは just tel-down）
just emu-api                         # API emulator を 4100-4108 で前面に起動する（emulator/emulate/README.md）
```

重いサービスと amd64 のサービスを既定で起動しないのは、OrbStack の VM をメモリ上限内に収めるためである。

HTTP の UI には、[portless](https://github.com/vercel-labs/portless) が `https://<name>.localhost` の固定 URL を与える（ADR 0015、別名は [`config/portless-aliases.yaml`](./config/portless-aliases.yaml)）。
postgres、bolt、gRPC などの TCP のプロトコルはルーティングできないので、ポートのまま使う。

```shell
just portless-trust   # 初回だけ: portless の CA を信頼する
just portless-up      # proxy を起動して別名を登録する（firebase.localhost、grafana.localhost など）
just portless-ls      # 有効な経路の一覧（片付けは just portless-down）
```

別名を登録しても、裏のスタックは起動しない。
`https://*.localhost` が応答するのは、`just emu-up`、`just tel-up`、`just emu-api` のあとである。
`portless service install` で proxy をログイン時に起動すれば、再起動後も経路が残る。

## Dev Container

`.devcontainer/devcontainer.json`（debian 12、Microsoft 公式の feature、ローカルの `dotfiles-tools` feature）が [Dev Container](https://containers.dev/) を定義する。
同じ定義を CI（`devcontainers/ci`）と Coder の template が使い、Coder は Artifact Registry の作成済み image を pull する（ADR 0002）。

中には `just`、`mise`、`prek`、`ruff`、`shellcheck`、`markdownlint-cli2`、Node.js（LTS）と、5 つの AI CLI（`codex`、`antigravity`、`claude`、`copilot`、`pi`）が入る。
エージェントが `just fmt|lint|check|test` を実行するサンドボックスとして使う。
CLI の認証は、workspace ごとに operator が一度行う（[runbook](./exe/docs/runbook.md#ai-agent-cli-authentication)）。

- Claude Code: `/devcontainer`
- VS Code / Cursor: Dev Containers 拡張を入れて `Reopen in Container`
- JetBrains: `File > Remote Development > Dev Containers`

clone に `.git` があれば、`postCreateCommand` が `just install-hooks` で prek の hook を入れる。
失敗してもコンテナの起動は止めない。

## MCP

```bash
claude mcp add -s user chrome-devtools bunx chrome-devtools-mcp@latest
claude mcp add -s user -t http deepwiki https://mcp.deepwiki.com/mcp

# ドキュメント系（user スコープ）
claude mcp add -s user -t http bun https://bun.com/docs/mcp
claude mcp add -s user -t http cloudflare https://docs.mcp.cloudflare.com/mcp
claude mcp add -s user -t http vercel https://mcp.vercel.com
claude mcp add -s user -t http livekit-docs https://docs.livekit.io/mcp
claude mcp add -s user -t http openai https://developers.openai.com/mcp
# Google Cloud: https://developers.google.com/knowledge/mcp#gcloud-cli
YOUR_PROJECT_ID=<your-project-id>
gcloud beta services mcp enable developerknowledge.googleapis.com --project=$YOUR_PROJECT_ID
# 認証が要る: gcloud auth login / gcloud auth application-default login
gcloud services api-keys create --project=$YOUR_PROJECT_ID --display-name="DK API Key"
YOUR_API_KEY=<your-keyString>
claude mcp add google-dev-knowledge -s user -t http https://developerknowledge.googleapis.com/mcp --header "X-Goog-Api-Key: $YOUR_API_KEY"
# AWS: https://awslabs.github.io/mcp/servers/aws-knowledge-mcp-server/
claude mcp add -s user -t http aws-knowledge-mcp-server https://knowledge-mcp.global.api.aws
# k6: https://grafana.com/docs/k6/latest/release-notes/v1.6.0/#introducing-mcp-k6-ai-assisted-k6-script-writing-mcp-k6
claude mcp add --scope=user --transport=stdio k6 -- docker run --rm -i grafana/mcp-k6

# プロジェクトごと（他のエージェントの設定ディレクトリにも写す）
claude mcp add -s project -t http jaeger http://localhost:16687/mcp
```

## その他の設定

### localhost の https

```shell
dig localhost.hironow.dev   # A レコードが 127.0.0.1 を指すこと
sudo certbot certonly --manual --preferred-challenges dns -d localhost.hironow.dev --config-dir ~/dotfiles/private/certificates
cd tools/simple-server && sudo mise x -- go run main.go   # https で応答するか確かめる
```

### git

```bash
git config --global pull.rebase true   # pull で merge commit を作らない
```

### WSL の VS Code トンネル

```bash
curl -Lk 'https://code.visualstudio.com/sha/download?build=stable&os=cli-alpine-x64' -o vscode_cli.tar.gz
tar -xzf vscode_cli.tar.gz && mv code ~/.local/bin/code-cli
~/.local/bin/code-cli tunnel user login
code-cli tunnel --accept-server-license-terms --name test-my-wsl   # 初回の確認
code-cli tunnel service install && code-cli tunnel status
```

### dotenvx の鍵を sudo なしで読ませない

エージェントの deny 設定に頼らず、`.env.keys` を sudo なしでは読めないようにする（実験的）。

```bash
dotenvx set HELLO "WORLD"
sudo chmod 600 .env.keys
dotenvx decrypt --stdout        # EACCES: permission denied, open '.env.keys'
sudo dotenvx decrypt --stdout   # 読める
```

## 参考リンク

- [mise](https://github.com/jdx/mise)、[uv](https://github.com/astral-sh/uv)、[gh do](https://github.com/k1LoW/gh-do)、[dotenvx](https://dotenvx.com/)
- [localhost の https](https://blog.jxck.io/entries/2020-06-29/https-for-localhost.html)
- [browser toolbox](https://toolbox.googleapps.com/)、[smarthome webrtc tool](https://smarthome-webrtc-validator.withgoogle.com/)、[trickle ice checker](https://webrtc.github.io/samples/src/content/peerconnection/trickle-ice/)
- MCP の一覧: <https://hub.docker.com/u/mcp>、<https://mcpmarket.com/en/categories/official>
- skill の一覧: <https://skills.sh/>
- Markdown: [YAML frontmatter](https://docs.github.com/en/contributing/writing-for-github-docs/using-yaml-frontmatter)、[MDX](https://github.com/mdx-js/mdx)
