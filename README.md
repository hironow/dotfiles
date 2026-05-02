# dotfiles

My configuration for Zsh, Mise, Just, and more.

## Architecture overview

Three environments share one source of truth (`mise.toml` +
`.devcontainer/devcontainer.json` + `install.sh`). Each runs the
same tools at the same versions; only the install path per OS
differs.

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
                          |  - mise.toml         (tool pins)    |
                          |  - .devcontainer/    (image SoT)    |
                          |  - dump/             (brew/gcloud)  |
                          +-------------------------------------+
```

```
Legend / 凡例:

- Mac host: operator のメインマシン (Homebrew 前提)
- Dev container: .devcontainer/devcontainer.json + features/dotfiles-tools をビルドした image (CI とローカル IDE で同一)
- Coder workspace: exe.hironow.dev で立ち上がる cloud dev 環境。Artifact Registry 上の prebuilt image を docker pull する
- install.sh OS dispatch: uname → mac / linux / windows で step_* 関数を切り替える (ADR 0005)
- mise.toml: just / uv / prek / vp / markdownlint-cli2 / node + 5 AI CLI (codex / gemini / claude / copilot / pi) を 3 OS 同一バージョンに pin (ADR 0006)
- .devcontainer/: dev container 仕様の SoT (debian-12 + Microsoft-curated features + ローカル feature)
- Artifact Registry: GitHub Actions が main merge 時に WIF 認証で image push、Coder workspace VM が docker pull
```

詳細は以下を参照:

- [`docs/intent.md`](./docs/intent.md) — リクエスト元の意図
- [`docs/adr/`](./docs/adr/) — Architecture Decision Records (0001–0007、debian-12 / prebuilt image / Actions 強化 / tailnet routing / install path / mise pin / Coder server hardening)
- [`exe/docs/architecture.md`](./exe/docs/architecture.md) — exe.hironow.dev 全体図 (Cloudflare + Tailscale + Coder + GCP)
- [`exe/docs/runbook.md`](./exe/docs/runbook.md) — 運用手順 (operator workflow)
- [`exe/coder/templates/dotfiles-devcontainer/README.md`](./exe/coder/templates/dotfiles-devcontainer/README.md) — Coder template の push / create
- [`exe/scripts/README.md`](./exe/scripts/README.md) — `cdr` wrapper (CF Access service token 経由で `coder` CLI を実行)
- [`tools/README.md`](./tools/README.md) — RTTM converter / simple server などの補助ツール

## Installation

Requires `curl` and `git`.

```shell
bash -c "$(curl -fsSL https://raw.githubusercontent.com/hironow/dotfiles/main/install.sh)"
```

> [!NOTE]
> Mac, Linux, Windows([WSL](https://learn.microsoft.com/en-us/windows/wsl/)内Linux)へ対応。Windows native (scoop) は OS dispatch hook のみで実装は TODO。
> Mac は Homebrew が前提条件 (操作者が手動で先にインストール)、それ以降は install.sh が自動。

## usage

```shell
# just (task runner)
just help

just sync-agents-preview
just sync-agents

just update-all
just dump

# diagnostics
just self-check
# run with quick validate tests (needs Docker)
just self-check with_tests=1
just doctor
just validate-path-duplicates

# uv on mise
mx uv sync

# just on mise
mx just --list

# mise env
mx dotenvx run -- mise set
# mise env with github credentials (use gh extension)
gh do -- mise set

# set env by dotenvx (encrypted)
mx dotenvx set HELLO World
# set env by mise (plain, unencrypted)
mx mise set WORLD=hello
```

### tests (docker required)

```shell
# run all sandbox tests
just test

# run by pytest marker (install/validate/versions/deploy/check)
just test-mark marker=validate

# verify install.sh (docker required)
just test-install
```

### install options

```shell
# full install
bash ./install.sh

# lightweight (skip heavy tools)
INSTALL_SKIP_HOMEBREW=1 INSTALL_SKIP_GCLOUD=1 INSTALL_SKIP_ADD_UPDATE=1 bash ./install.sh
```

## setup for https localhost

```shell
# check A record for localhost -> 127.0.0.1
dig localhost.hironow.dev

# create/update cert for https
sudo certbot certonly --manual --preferred-challenges dns -d localhost.hironow.dev --config-dir ${config_root}/private/certificates

# check simple-server for https localhost
cd tools/simple-server
sudo mise x -- go run main.go
```

## Dev Container

This repo ships a [Dev Container](https://containers.dev/) declared in
`.devcontainer/devcontainer.json` (debian-12 + Microsoft-curated
features + local `dotfiles-tools` feature). The same file drives CI
(`devcontainers/ci` action) and the Coder workspace template
(prebuilt image pulled from Artifact Registry — no envbuilder per
[ADR 0002](./docs/adr/0002-coder-prebuilt-image.md)), so all three
environments stay aligned. Open it to get an isolated environment
with `just`, `mise`, `prek`, `ruff`, `shellcheck`,
`markdownlint-cli2`, Node.js 24, and 5 AI agent CLIs
(`codex`, `gemini`, `claude`, `copilot`, `pi`) already provisioned
— useful as an AI agent sandbox for `just fmt|lint|check|test`.
Auth for the AI CLIs is operator-side and runs once per workspace;
see [`exe/docs/runbook.md`](./exe/docs/runbook.md#ai-agent-cli-authentication).

- **Claude Code**: run `/devcontainer`
- **VS Code / Cursor**: install the Dev Containers extension, then `Reopen in Container`
- **JetBrains**: `File > Remote Development > Dev Containers`

The `postCreateCommand` runs `mise trust && mise install && just install-hooks`,
so prek hooks are wired into the clone automatically.

## Tools

- [Tools](./tools/README.md): Collection of utility scripts and tools (e.g., RTTM converter, simple server).

## references

- [mise](https://github.com/jdx/mise)
- [uv](https://github.com/astral-sh/uv)
- [gh do](https://github.com/k1LoW/gh-do)
- [localhost](https://blog.jxck.io/entries/2020-06-29/https-for-localhost.html)
- [dotenvx](https://dotenvx.com/)
- [browser toolbox](https://toolbox.googleapps.com/)
- [smarthome webrtc tool](https://smarthome-webrtc-validator.withgoogle.com/)
- [trickle ice checker](https://webrtc.github.io/samples/src/content/peerconnection/trickle-ice/)

## mcp setup

```bash
claude mcp add -s user chrome-devtools bunx chrome-devtools-mcp@latest
claude mcp add -s user -t http deepwiki https://mcp.deepwiki.com/mcp

# latest documentation MCP per user
claude mcp add -s user -t http bun https://bun.com/docs/mcp
claude mcp add -s user -t http cloudflare https://docs.mcp.cloudflare.com/mcp
claude mcp add -s user -t http vercel https://mcp.vercel.com
claude mcp add -s user -t http livekit-docs https://docs.livekit.io/mcp
claude mcp add -s user -t http openai https://developers.openai.com/mcp
# -- Google Cloud: https://developers.google.com/knowledge/mcp#gcloud-cli
YOUR_PROJECT_ID=<your-project-id>
gcloud beta services mcp enable developerknowledge.googleapis.com --project=$YOUR_PROJECT_ID
# -- needs credentials setup
# gcloud auth login
# gcloud auth application-default login
gcloud services api-keys create --project=$YOUR_PROJECT_ID --display-name="DK API Key"
YOUR_API_KEY=<your-keyString>
claude mcp add google-dev-knowledge -s user -t http https://developerknowledge.googleapis.com/mcp --header "X-Goog-Api-Key: $YOUR_API_KEY"
# -- AWS: https://awslabs.github.io/mcp/servers/aws-knowledge-mcp-server/
claude mcp add -s user -t http aws-knowledge-mcp-server https://knowledge-mcp.global.api.aws
# -- k6: https://grafana.com/docs/k6/latest/release-notes/v1.6.0/#introducing-mcp-k6-ai-assisted-k6-script-writing-mcp-k6
claude mcp add --scope=user --transport=stdio k6 -- docker run --rm -i grafana/mcp-k6

# specific (needs copy for other agents' directory) per project
claude mcp add -s project -t http jaeger http://localhost:16687/mcp
```

MCP catalog refs.

- <https://hub.docker.com/u/mcp>
- <https://mcpmarket.com/en/categories/official>

## skill setup

justfile経由で `CLAUDE_CONFIG_DIR` を切り替えつつ操作できる:

```bash
just skills ls                # デフォルトconfigでスキル一覧
just skills add <repo> --all  # スキル追加
just env=a skills ls -g       # ~/.claude-work-a 向け
just env=b skills ls -g       # ~/.claude-work-b 向け
just env=c skills ls -g       # ~/.claude-work-c 向け
just env=d skills ls -g       # ~/.claude-work-d 向け
just env=p skills ls -g       # ~/.claude (personal) 向け
```

```bash
just skills add vercel-labs/agent-skills
just skills add modelcontextprotocol/ext-apps
just skills add wandb/skills
just skills add https://github.com/googleworkspace/cli
# browser: https://github.com/vercel-labs/agent-browser?tab=readme-ov-file#agentsmd--claudemd
just skills add vercel-labs/agent-browser
```

Skill catalog refs.

- <https://skills.sh/>

## git setup

```bash
# avoid merge commits when pulling
git config --global pull.rebase true
```

## win setup (WSL)

```bash
# install vscode cli for wsl
curl -Lk 'https://code.visualstudio.com/sha/download?build=stable&os=cli-alpine-x64' -o vscode_cli.tar.gz
tar -xzf vscode_cli.tar.gz
mv code ~/.local/bin/code-cli

# login vscode tunnel
~/.local/bin/code-cli tunnel user login

# check vscode tunnel initial setup
code-cli tunnel --accept-server-license-terms --name test-my-wsl

# start service
code-cli tunnel service install
code-cli tunnel status
```

## dotenvx setup (for LLM)

```bash
# init
sudo chmod 600 .env.keys
dotenvx set HELLO "WORLD"

# change to -rw-------
sudo chmod 600 .env.keys

# then: NG
dotenvx decrypt --stdout
EACCES: permission denied, open '.env.keys'

# then: OK
sudo dotenvx decrypt --stdout
```

As a defensive measure, I want to not trust the deny option of various agents (experimental).

## markdown+

- <https://docs.github.com/en/contributing/writing-for-github-docs/using-yaml-frontmatter>
- <https://github.com/mdx-js/mdx>
