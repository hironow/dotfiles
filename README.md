# dotfiles

My configuration for Zsh, Mise, Just, and more.

## Architecture overview

Three environments share one source of truth (`config/mise/config.toml` +
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
                          |  - config/mise/config.toml (tool pins)    |
                          |  - .devcontainer/    (image SoT)    |
                          |  - dump/<host>/      (brew/gcloud)  |
                          +-------------------------------------+
```

```
凡例:

- install.sh: uname で mac / linux / windows を振り分ける (ADR 0005)
- `config/mise/config.toml`: just / uv / prek / vp / markdownlint-cli2 / node と 5 つの AI CLI (codex / antigravity / claude / copilot / pi) を 3 OS で同じバージョンに pin する (ADR 0006)
- Artifact Registry: main への merge 時に GitHub Actions が WIF 認証で image を push し、Coder workspace VM が docker pull する
- Dev container: CI とローカル IDE で同じ image (Dev Container の節を参照)
```

詳細は以下を参照:

- [`docs/adr/`](./docs/adr/) — Architecture Decision Records
- [`exe/docs/architecture.md`](./exe/docs/architecture.md) — exe.hironow.dev 全体図 (Cloudflare + Tailscale + Coder + GCP)
- [`exe/docs/runbook.md`](./exe/docs/runbook.md) — 運用手順 (operator workflow)
- [`exe/coder/templates/dotfiles-devcontainer/README.md`](./exe/coder/templates/dotfiles-devcontainer/README.md) — Coder template の push / create
- [`exe/scripts/README.md`](./exe/scripts/README.md) — `cdr` wrapper (CF Access service token 経由で `coder` CLI を実行)
- [`tools/README.md`](./tools/README.md) — RTTM converter / simple server などの補助ツール
- `docs/intent.md` — リクエスト元の意図 (operator-only, gitignored)

## Installation

Requires `curl` and `git`.

```shell
bash -c "$(curl -fsSL https://raw.githubusercontent.com/hironow/dotfiles/main/install.sh)"
```

**Windows native** は、まっさらな機体から PowerShell 1 行で導入できる ([ADR 0039](docs/adr/0039-windows-bootstrap-ps1.md)):

```powershell
# scoop manifest の host を変える場合は先に: $env:DOTFILES_HOST = '<host>'
irm https://raw.githubusercontent.com/hironow/dotfiles/main/bootstrap.ps1 | iex
```

bootstrap は scoop / git / just / jq / mise / pwsh を入れ、HTTPS で `~\dotfiles` に clone する。
続けて `add-scoop` → `deploy` → `harden-env` → `sync-agents` → `restore-skills-lock` → `doctor` を実行する。
何度実行しても安全である。
完了後は新しい pwsh セッションを開く (`$PROFILE` はそこで効く)。

SSH 鍵を設定したあとに、次を実行する。
vendored submodule は SSH URL のため、bootstrap は触らない。

```powershell
git -C ~/dotfiles remote set-url origin git@github.com:hironow/dotfiles.git
git -C ~/dotfiles submodule update --init
```

> [!NOTE]
> Mac、Linux、Windows ([WSL](https://learn.microsoft.com/en-us/windows/wsl/) 内の Linux) を一級でサポートする。
> Mac は Homebrew が前提で、operator が先に入れる。以降は install.sh が自動で進める。
>
> Windows native の `just deploy` は、`corepack enable`、`starship.toml` / `gitignore-global` / `config/mise/config.toml` の配置、`$PROFILE` への mise activate / starship init（starship は mise 管理のため、この順）/ `MISE_NODE_COREPACK=0` の注入、global mise toolset の install、`aliases.gitconfig` の `[include]` 配線を行う。
> scoop は、host ごとの manifest (`dump/<host>/scoop.json`) の dump と、`just add-scoop` による復元に対応する。
> 基本の recipe は完走し、`just ci` も green になる (一部のテストは Linux / WSL / CI 限定で skip)。
> 詳細は [ADR 0018](docs/adr/0018-windows-native-mvp.md)、[ADR 0039](docs/adr/0039-windows-bootstrap-ps1.md) と、0019 / 0022 / 0024 / 0030 / 0031 / 0032 / 0033。

## usage

```shell
# just (task runner)
just help

just sync-agents-preview
just sync-agents

# lint the distributed Claude config (official `claude plugin validate --strict` + effective-settings check, ADR 0029)
just lint-claude

just update-all
just dump
# restore packages from a recorded manifest (per-host)
just add-brew          # macOS
just add-scoop         # Windows: scoop import dump/<host>/scoop.json (ADR 0032)

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

### CI gates

```shell
# fast gate (no Docker): fmt/lint, semgrep, claude config lint, unit tests, IaC tests, instruction budget, skills lock check
# (the claude config lint also runs as the `Claude Config Lint` GitHub workflow, ADR 0029)
just ci

# full non-emulator matrix: ci + devcontainer sandbox + install verification (Docker)
just ci-all

# emulator suite: lint + bring up emulators + fast + e2e (Docker + emulator uv env)
just ci-emu

# everything-non-emulator gate (prek hooks + ci-all); used by pre-push/CI
just check-all
```

### install options

```shell
# full install
bash ./install.sh

# lightweight (skip heavy tools)
INSTALL_SKIP_HOMEBREW=1 INSTALL_SKIP_GCLOUD=1 INSTALL_SKIP_ADD_UPDATE=1 bash ./install.sh
```

## Jev opt-in coding sessions

作業リポジトリから `jev-claude '依頼文'` または `jev-pi '依頼文'` で起動する。
鍵の設定、初回準備、提供元の切替は [Jev 起動コマンドの手順](docs/runbook/jev-launchers.md) を参照。

## setup for https localhost

```shell
# check A record for localhost -> 127.0.0.1
dig localhost.hironow.dev

# create/update cert for https
sudo certbot certonly --manual --preferred-challenges dns -d localhost.hironow.dev --config-dir ~/dotfiles/private/certificates

# check simple-server for https localhost
cd tools/simple-server
sudo mise x -- go run main.go
```

## Local emulators, telemetry & portless

`emulator/` (datastore and inspector emulators) and `telemetry/` (OTel, Grafana, Loki, Prometheus, Tempo) live in this repo ([ADR 0014](./docs/adr/0014-vendor-emulator-telemetry-from-submodules.md)).
`emulate` (vercel-labs/emulate) adds API/SaaS emulators through an npx wrapper ([ADR 0016](./docs/adr/0016-integrate-emulate-api-emulators-via-npx.md)).

```shell
# datastore / inspector emulators (emulator/compose.yaml)
# Lite default = GCP core (firebase+spanner+pgadapter+postgres); heavy/amd64
# services are opt-in so the OrbStack VM stays under its memory cap.
just emu-up               # detached, lite (== emu-up-lite); emu-start = clean+prebuild+up+wait
just emu-up-only firebase-emulator   # only Firebase (e.g. reuse Pub/Sub :9399 from another repo)
just emu-up-group search  # lite + a capability group (bigtable search graph vector ml inspect exporters full)
just emu-up-full          # the whole heavy stack (excludes interactive *-cli)
just emu-check            # status + endpoints
just emu-stop             # stop (with firebase export)

# telemetry stack (telemetry/compose.yaml)
just tel-up               # start; just tel-down to stop

# API/SaaS emulators (vercel-labs/emulate, base port 4100, foreground)
just emu-api              # 9 API emulators on 4100-4108 (see emulator/emulate/README.md)
```

HTTP UIs get stable `https://<name>.localhost` URLs through [portless](https://github.com/vercel-labs/portless) ([ADR 0015](./docs/adr/0015-adopt-portless-for-local-dev-urls.md)); aliases live in [`config/portless-aliases.yaml`](./config/portless-aliases.yaml).
TCP wire protocols (postgres / bolt / gRPC) cannot be routed and keep their ports.

```shell
just portless-trust       # one-time: trust the portless CA
just portless-up          # start proxy + register aliases (firebase.localhost, grafana.localhost, ...)
just portless-ls          # list active routes; just portless-down to tear down
```

Registering an alias starts nothing.
The `https://*.localhost` URLs respond only after the backing stack is up (`just emu-up`, `just tel-up`, `just emu-api`).
`portless service install` runs the proxy at login so routes survive reboots.

## Dev Container

`.devcontainer/devcontainer.json` (debian-12, Microsoft-curated features, and the local `dotfiles-tools` feature) defines the [Dev Container](https://containers.dev/).
The same file drives CI (`devcontainers/ci`) and the Coder workspace template, which pulls a prebuilt image from Artifact Registry ([ADR 0002](./docs/adr/0002-coder-prebuilt-image.md); no envbuilder), so the three environments stay aligned.

The container has `just`, `mise`, `prek`, `ruff`, `shellcheck`, `markdownlint-cli2`, Node.js (LTS) and five AI agent CLIs (`codex`, `antigravity`, `claude`, `copilot`, `pi`).
That makes it a sandbox for agents running `just fmt|lint|check|test`.
Auth for the CLIs is operator-side, once per workspace ([runbook](./exe/docs/runbook.md#ai-agent-cli-authentication)).

- **Claude Code**: run `/devcontainer`
- **VS Code / Cursor**: install the Dev Containers extension, then `Reopen in Container`
- **JetBrains**: `File > Remote Development > Dev Containers`

`postCreateCommand` runs `just install-hooks` when the clone has a `.git`, so prek hooks are wired automatically.
A failure does not stop the container.

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

skill は自作 ([hironow/skills](https://github.com/hironow/skills)) もサードパーティも宣言管理する
([ADR 0038](docs/adr/0038-declarative-third-party-skills.md) → [ADR 0043](docs/adr/0043-self-authored-skills-through-the-skills-cli.md))。
実体は skills CLI が `~/.agents/skills` (store) に置き、git は宣言 `dump/harness/skill-lock.json` だけを追跡する。
各 agent home (`~/.claude*`, `~/.codex`, `~/.gemini`) には、`skills-place` が store への相対 symlink を張る (張れない環境では追跡付きのコピー)。
同名の skill は hironow/skills が優先される (`skills-lock-check` が `ci` で検証する)。

```bash
just restore-skills-lock  # 新しいマシン: 宣言から store に復元し、home に配置する
just skills-place         # home の symlink を張り直す (冪等)
just skills-update        # hironow/skills の merge 後など: store を更新して home に配置する

# 追加: CLI には store だけを書かせ (-a universal)、宣言を更新してから配置する
bunx skills add <repo> -g -s <name> -y -a universal
just dump-skills-lock
just skills-place
```

`just dump-skills-lock` は、その機体の store 全体から宣言を作り直す。
store が宣言とずれていると無関係な差分も出るので、差分を確認する。

サードパーティは、必要な skill だけを宣言している。

- `wandb/skills`: `wandb-primary` は hironow/skills の fork が優先される。宣言するのは `wandb-autoresearch` と `wandb-eval-tables`。
- `googleworkspace/cli`: 95 個のうち、`gws-shared` と主要 9 サービス (gmail / calendar / drive / docs / sheets / slides / tasks / forms / people) だけを宣言する。`persona-*` と `recipe-*` は、skill 一覧が長くなるため入れない。
- `vercel-labs/agent-browser`: [使い方](https://github.com/vercel-labs/agent-browser?tab=readme-ov-file#agentsmd--claudemd)。

`just skills` は、`CLAUDE_CONFIG_DIR` を切り替えて CLI を呼ぶ (`env=p` は `~/.claude`、`a` から `d` は `~/.claude-work-a` から `-d`)。
参照 (`just env=a skills ls -g`) に使い、追加には使わない。home に直接書き込み、store と宣言から外れるためである。

Skill catalog refs.

- <https://skills.sh/>

## git setup

```bash
# avoid merge commits when pulling
git config --global pull.rebase true
```

## fresh WSL provisioning

A bare WSL2 Ubuntu box (not a devcontainer) needs a few one-time steps. The
bootstrap now self-provisions `mise` and the `config/mise/config.toml` toolset, so most of it
is a single command.

```bash
# 1. Prereqs: WSL2 Ubuntu with `curl` and `git` only.

# 2. Bootstrap: installs mise (pinned, SHA-verified, ~/.local/bin), runs
#    `mise install`, and symlinks the dotfiles. No sudo, no devcontainer needed.
bash -c "$(curl -fsSL https://raw.githubusercontent.com/hironow/dotfiles/main/install.sh)"

# 3. Machine-local supply-chain hardening (flatt mirror + 7-day quarantine).
#    Writes ~/.config/uv/uv.toml + ~/.npmrc; idempotent and NOT tracked.
just harden-env

# 4. WSL config: keep the Windows PATH out of WSL and enable systemd.
#    `wsl-conf` previews config/wsl/wsl.conf against /etc/wsl.conf and prints
#    the sudo edit; then, from Windows PowerShell, reload with `wsl --shutdown`.
just wsl-conf

# 5. WSL-native Docker (for `just test` / the devcontainer sandbox). With
#    systemd enabled by step 4, start the daemon after installing docker.io:
sudo apt-get update && sudo apt-get install -y docker.io
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"   # effective after the next `wsl --shutdown`

# 6. Verify the box.
just doctor    # expect PATH-windows OK, docker reachable, tools present
```

Notes:

- Steps 4-5 need `sudo` plus a Windows-side `wsl --shutdown`; the rest is
  sudo-free.
- `just harden-env` sets a personal `exclude-newer`. Committed locks stay
  span-less via `just relock-uv` (ADR 0028); the dependency-free root lock is
  regenerated with the personal config out of the way.

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
