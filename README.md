# dotfiles

Zsh、mise、just、AI エージェントなどの設定と、それを macOS、Linux、Windows、Dev Container に配る仕組みをまとめたリポジトリ。

## 構成

すべての環境が、このリポジトリの正本から同じバージョンの道具と設定を入れる。
OS ごとに違うのは導入の経路だけである。

| 正本 | 役割 |
| --- | --- |
| `install.sh` / `bootstrap.ps1` | OS を判定して初期導入する（ADR 0005、ADR 0039） |
| `config/mise/config.toml` | host に入れる道具（`just`、`uv`、`prek`、`vp`、`markdownlint-cli2`、`node`、5 つの AI CLI など）の版を 3 OS で揃える（ADR 0006） |
| `config/mise/image-tools.toml` | Dev Container が bake する `/etc/mise/config.toml`、検証つき tarball、Linux bootstrap の版を 1 か所に持つ。`install.sh` の該当領域はここから生成し、`just lint` / `just check` が食い違いを検出する（ADR 0060） |
| `.devcontainer/devcontainer.json` | CI と IDE が共有するサンドボックスの定義（ADR 0001、ADR 0002） |
| `dump/<host>/` | OS ごとのパッケージ記録（Homebrew、Scoop、gcloud など。ADR 0030） |
| `ROOT_*` / `dump/harness/` | エージェントの指示、hook、skill、Claude プラグインの正本（[`docs/agent-sync.md`](./docs/agent-sync.md)） |

関連文書:

- [`docs/agent-sync.md`](./docs/agent-sync.md): エージェント指示、hook、skill、プラグインの配布
- [`docs/runbook/jev-launchers.md`](./docs/runbook/jev-launchers.md): `j-cc` / `j-pi`、rtk、headroom の手順
- [`docs/runbook/ollama-windows-wsl.md`](./docs/runbook/ollama-windows-wsl.md): Windows と WSL の Ollama 共有と検査範囲
- [`docs/runbook/windows-host.md`](./docs/runbook/windows-host.md): native Windows で動かすときの注意点
- [`docs/runbook/ca-doctor.md`](./docs/runbook/ca-doctor.md) / [`docs/runbook/kernel-doctor.md`](./docs/runbook/kernel-doctor.md): `just doctor` の CA と kernel の行の読み方
- [`docs/portless-urls.md`](./docs/portless-urls.md): ローカル UI の `https://<name>.localhost` 別名一覧
- [`docs/adr/`](./docs/adr/): 設計判断の記録（ADR）
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
sudo は要らない。`install.sh` 全体を sudo で実行しない。
例外は WSL の `wl-clipboard`（Pi と Herdr のコピー用）で、root か非対話の `sudo -n` で入れる。パスワードが要るときは、導入コマンドを表示して先へ進む。
`just deploy` は `~/.zprofile` に `~/.local/bin` を足す（zsh のログインシェルは `~/.profile` を読まない）。

WSL の素の Ubuntu では、続けて次を一度だけ実行する。
`wsl-conf` と Docker を効かせるには、Windows 側で `wsl --shutdown` も要る。

```bash
# install.sh が wl-clipboard を入れられなかった場合（WSLg が必要）
sudo apt-get update && sudo apt-get install -y wl-clipboard
# zsh を入れてログインシェルにする（.zshrc と j-cc / j-pi は zsh 前提）
sudo apt-get install -y zsh && chsh -s "$(command -v zsh)"
# 新しいターミナルを開いてから（sheldon は install.sh が mise で導入済み）
sheldon lock

just harden-env   # 機体ごとの供給網対策（npm と uv の 7 日の隔離、GOPROXY）。追跡しない
just wsl-conf     # /etc/wsl.conf の差分と sudo での編集手順を表示する（Windows の PATH を入れない、systemd を有効化）

# WSL の中で Docker を動かす（just test と Dev Container のサンドボックス用）
sudo apt-get update && sudo apt-get install -y docker.io
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"   # 次の wsl --shutdown のあとで効く

just doctor       # 確認: zsh、PATH-windows（WSL のみ）、WSLg の clipboard、docker、道具一式
```

`just harden-env` は `~/.npmrc` と `~/.config/uv/uv.toml` に 7 日の隔離（`min-release-age=7`、`exclude-newer = "7 days"`）を書く。
Pi の拡張とその依存は隔離から外す（`~/.pi/agent/npm/.npmrc` に `min-release-age=0` を置く）。
コミットする lock の 7 日の隔離は、各 project の `pyproject.toml` が自分で宣言する。

### Windows（native）

まっさらな機体に PowerShell の 1 行で導入する（ADR 0039）。

```powershell
# scoop の manifest を別の host のものにする場合は先に: $env:DOTFILES_HOST = '<host>'
irm https://raw.githubusercontent.com/hironow/dotfiles/main/bootstrap.ps1 | iex
```

`bootstrap.ps1` は scoop、git、just、jq、mise、pwsh を入れ、HTTPS で `~\dotfiles` に clone する。
続けて `add-scoop`、`deploy`、`harden-env`、`sync-agents`、`restore-skills-lock`、`doctor` を実行する。
何度実行しても安全であり、終わったら新しい pwsh を開く（`$PROFILE` はそこで効く）。

- **`just deploy`（Windows）**: `starship.toml`、`gitignore-global`、`config/mise/config.toml` をコピーし、pwsh の `$PROFILE`（mise activate、starship init、`MISE_NODE_COREPACK=0`、`j-cc` / `j-pi`）を書き、mise の道具と Pi の拡張を入れ、`aliases.gitconfig` を `[include]` で読み込ませる。
- **`just harden-env`（Windows）**: `%APPDATA%\uv\uv.toml`、User PATH の Git `usr\bin` と `cmd`、telemetry 無効化の環境変数、必要に応じた `CLAUDE_CODE_GIT_BASH_PATH` も設定する（詳細: [`docs/runbook/windows-host.md`](./docs/runbook/windows-host.md)）。
- **Scoop**: `dump/<host>/scoop.json` に記録し、`just add-scoop` で復元する。
- **Ollama**: Windows と WSL が共存する機体では、Windows の Scoop `extras/ollama-full` に一本化する。WSL は loopback のブリッジまたは共有 loopback を使い、Linux 版の本体やモデルは持たない。構成違反は `just doctor` が検出する（詳細: [`docs/runbook/ollama-windows-wsl.md`](./docs/runbook/ollama-windows-wsl.md)）。

SSH 鍵を設定したら、remote を SSH に替えて submodule を取得する。

```powershell
git -C ~/dotfiles remote set-url origin git@github.com:hironow/dotfiles.git
git -C ~/dotfiles submodule update --init
```

## 日常の操作

```shell
just help                       # recipe の一覧

just sync-agents-preview        # エージェント指示の配布を試す（書き込まない）
just sync-agents                # ~/.claude などへ配る（all で全エージェント）
just claude-plugins-install     # 各 Claude の home に必須プラグインを入れる（deploy も実行する）
just lint-claude                # 配る Claude 設定の検査（ADR 0029）

just update-all                 # 道具を更新する（mise、gh、Pi の拡張など）
just dump                       # 導入済みのパッケージを dump/<host>/ に記録する
just add-brew                   # macOS: 記録から復元する
just add-scoop                  # Windows: 記録から復元する（ADR 0032）

just self-check                 # 軽い健全性検査（with_tests=1 で Docker のテストも）
just doctor                     # 道具、PATH、OS 固有の設定、AI の道具、CA、kernel を診断する（ERR があれば exit 1）
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
| `just ci` | `just check`（Python・Go・shell・Markdown・JS/TS の lint、Pi 拡張・Go のテスト、Quint のモデル）、Claude 設定検査、unit テスト、semgrep 規則テスト、IaC テスト、指示量予算、skill 宣言、emulator の lint、禁止トークン | 不要 |
| `just ci-all` | `ci` + Dev Container のサンドボックステスト + `install.sh` の検証（単独は `just test-install`） | 要る |
| `just ci-emu` | emulator 群の lint、起動、高速テスト、e2e | 要る |
| `just check-all` | prek の hook と `ci-all`（push 前の最終ゲート） | 要る |
| `just test` | Dev Container 内のサンドボックステスト（`just test-mark marker=validate` のように `install`、`validate`、`versions`、`deploy`、`check` で絞れる） | 要る |

`tests/unit/` は native Windows でも通る（POSIX 専用の検査は skip する）。

`just doctor` の行は `OK`、`WARN`、`ERR`、`INFO` のどれかで始まる。
`WARN` はその機体で手を動かすべきこと、`INFO` は検査の範囲と事実で、`INFO` は終了コードを変えない（ADR 0066）。

## Jev でのコーディングセッション

作業リポジトリで `j-cc '依頼文'` または `j-pi '依頼文'` を実行すると、依頼に応じて Claude Code・Pi の思考レベルと Codex worker のモデルを選んで起動する。
`-c`（直近のセッションを続ける）と `-r`（選んで再開する）もそのまま使える。
`j-cc` のセッションは rtk（コマンド出力の圧縮）と headroom の proxy（モデルへの送信内容の圧縮）の両方を通る。
初回準備、キーの置き場所、動作確認（`just jev-headroom-verify rtk`）は [`docs/runbook/jev-launchers.md`](./docs/runbook/jev-launchers.md) にある。

## skill

skill は自作（[hironow/skills](https://github.com/hironow/skills)）もサードパーティも `dump/harness/skill-lock.json` で宣言管理する（ADR 0038、ADR 0043、[`docs/agent-sync.md`](./docs/agent-sync.md)）。
実体は skills CLI が `~/.agents/skills`（store）に置き、`skills-place` が各エージェントの home（`~/.claude*`、`~/.codex`、`~/.gemini`）へ相対 symlink を張る（張れない環境では追跡つきのコピー）。
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

`just dump-skills-lock` はその機体の store 全体から宣言を作り直すため、差分を確認してからコミットする。
サードパーティは必要な skill だけを宣言する（例: `googleworkspace/cli` は `gws-shared` と主要 9 サービスに絞り、`persona-*` と `recipe-*` は入れない）。
`just env=a skills ls -g` のように `just skills` で home ごとの一覧を参照できる（`env=p` は `~/.claude`、`a`〜`d` は `~/.claude-work-a`〜`-d`）。
`just skills` は参照だけに使い、追加には使わない。

## ローカル開発スタック

`emulator/`（データストアとインスペクタ）と `telemetry/`（OTel、Grafana、Loki、Prometheus、Tempo）はこのリポジトリにある（ADR 0014）。
API や SaaS の emulator は `vercel-labs/emulate` を `bunx` 経由で動かす（ADR 0016、ADR 0055）。
Docker の VM（OrbStack か podman machine）のメモリに収めるため、重いサービスと amd64 のサービスは既定では起動しない。

```shell
just emu-up                          # 既定は GCP の中核だけ（firebase、spanner、pgadapter、postgres。別名 emu-up-lite）
just emu-up-only firebase-emulator   # 名指しで起動する
just emu-up-group search             # 中核に機能群を足す（bigtable search graph vector ml inspect exporters full）
just emu-up-full                     # 重いものも含む全データサービス（対話用の *-cli は除く）
just emu-check                       # 状態と接続先
just emu-stop                        # firebase のデータを書き出して止める

just tel-up                          # telemetry を起動する（停止は just tel-down）
just emu-api                         # API emulator を 4100-4108 で前面に起動する（emulator/emulate/README.md）
```

HTTP の UI には [portless](https://github.com/vercel-labs/portless) で `https://<name>.localhost` の固定 URL を付ける（ADR 0015、ADR 0054）。
初回に `portless trust`（必要なら `portless service install`）を実行し、`portless proxy start` のあとで別名を登録する。
別名の一覧と対象外の TCP ポートは [`docs/portless-urls.md`](./docs/portless-urls.md) にある。

## Dev Container

`.devcontainer/devcontainer.json`（Debian 12、Microsoft 公式 feature、ローカルの `dotfiles-tools` feature）が [Dev Container](https://containers.dev/) と CI（`devcontainers/ci`）の共通環境を定義する（ADR 0002）。
中には `just`、`mise`、`prek`、`ruff`、`shellcheck`、`markdownlint-cli2`、Node.js（LTS）、5 つの AI CLI（`codex`、`antigravity`、`claude`、`copilot`、`pi`）が入る。
CLI の認証はコンテナごとに operator が一度行う。
clone に `.git` があれば、`postCreateCommand` が `just install-hooks` で prek の hook を入れる。

- Claude Code: `/devcontainer`
- VS Code / Cursor: Dev Containers 拡張で `Reopen in Container`
- JetBrains: `File > Remote Development > Dev Containers`

## MCP

Chrome DevTools の MCP は必須プラグイン（`dump/harness/claude-plugins.json`）が入れるので、ここには書かない。

```bash
claude mcp add -s user -t http deepwiki https://mcp.deepwiki.com/mcp

# ドキュメント系（user スコープ）
claude mcp add -s user -t http bun https://bun.com/docs/mcp
claude mcp add -s user -t http cloudflare https://docs.mcp.cloudflare.com/mcp
claude mcp add -s user -t http vercel https://mcp.vercel.com
claude mcp add -s user -t http livekit-docs https://docs.livekit.io/mcp
claude mcp add -s user -t http openai https://developers.openai.com/mcp
# Google Cloud: https://developers.google.com/knowledge/mcp#gcloud-cli
# 手元の MCP 接続の設定で、一度だけ行う。tofu が管理する本番のリソースには使わない
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
