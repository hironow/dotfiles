# dotfiles

Repository of configurations for Zsh, mise, just, AI agents, and more, plus scripts to deploy them to macOS, Linux, Windows, and Dev Containers.

## Structure

Tools managed by mise use the sources of truth in this repository to keep versions and configurations consistent.
OS packages such as Podman use native installation paths and check the minimum version.

| Source | Role |
| --- | --- |
| `install.sh` / `bootstrap.ps1` | Detect the OS and run initial setup (ADR 0005, ADR 0039; Podman exception in ADR 0067) |
| `config/mise/config.toml` | Pin versions of host tools (`just`, `uv`, `prek`, `vp`, `markdownlint-cli2`, `node`, five AI CLIs, etc.) across all three OSes (ADR 0006) |
| `config/mise/image-tools.toml` | Hold the single source for `/etc/mise/config.toml` baked into the Dev Container, verified tarballs, and Linux bootstrap versions. The matching section in `install.sh` is generated from this file, and `just lint` / `just check` detect drift (ADR 0060) |
| `.devcontainer/devcontainer.json` | Trixie / Podman sandbox shared by CI and IDEs (ADR 0001, ADR 0002, ADR 0067) |
| `dump/<host>/` | Per-OS package lists (Homebrew, Scoop, gcloud, etc.; ADR 0030) |
| `ROOT_*` / `dump/harness/` | Sources of truth for agent instructions, hooks, skills, and Claude plugins ([`docs/agent-sync.md`](./docs/agent-sync.md)) |

Related docs:

- [`docs/agent-sync.md`](./docs/agent-sync.md): Distributing agent instructions, hooks, skills, and plugins
- [`docs/cli-tools.md`](./docs/cli-tools.md): Installing, supported platforms for, and choosing between Hunk, rg, fd, sd, mq, witr, jq, yq, and fq
- [`docs/runbook/jev-launchers.md`](./docs/runbook/jev-launchers.md): Procedures for `j-cc` / `j-pi`, rtk, and headroom
- [`docs/runbook/ollama-windows-wsl.md`](./docs/runbook/ollama-windows-wsl.md): Sharing Ollama between Windows and WSL and what checks cover
- [`docs/runbook/windows-host.md`](./docs/runbook/windows-host.md): Notes for running on native Windows
- [`docs/runbook/ca-doctor.md`](./docs/runbook/ca-doctor.md) / [`docs/runbook/kernel-doctor.md`](./docs/runbook/kernel-doctor.md): How to read the CA and kernel lines in `just doctor`
- [`docs/portless-urls.md`](./docs/portless-urls.md): List of `https://<name>.localhost` aliases for local UIs
- [`docs/adr/`](./docs/adr/): Architecture Decision Records (ADRs)
- [`tools/README.md`](./tools/README.md): Helper tools such as RTTM conversion
- `docs/intent.md`: Intent of current work (written only by the operator; not tracked in git)

## Setup

### Mac, Linux, and WSL

You only need `curl` and `git`.
On Mac, install Homebrew first.

```shell
bash -c "$(curl -fsSL https://raw.githubusercontent.com/hironow/dotfiles/main/install.sh)"

# To skip heavy tools
INSTALL_SKIP_HOMEBREW=1 INSTALL_SKIP_GCLOUD=1 INSTALL_SKIP_ADD_UPDATE=1 bash ./install.sh
```

`install.sh` installs mise (pinned version, SHA-verified, in `~/.local/bin`), runs `mise install` for tools, and symlinks configurations.
Podman 5 or later is also required, installed via Homebrew on Mac and OS packages on Linux.
Root or non-interactive `sudo -n` is required only when installing missing Podman packages on Linux.
If permissions are missing, it stops. Do not run all of `install.sh` with sudo.
If the apt or dnf Podman candidate is below 5, it stops immediately without installing anything (Ubuntu 24.04 and RHEL 8 ship 4.9, so `install.sh` also stops here; do not use Podman on WSL until upgrading the distribution).
On WSL, `wl-clipboard` (for copying in Pi and Herdr) is also installed with root or `sudo -n`, but if that fails, it prints instructions and continues.
`just deploy` adds `~/.local/bin` to `~/.zprofile` (zsh login shells do not read `~/.profile`).
In WSL zsh (an interactive shell that reads `.zshrc`), mise does not read the Windows home mise config (`/mnt/c/Users/<user>/.config/mise`). It reads `mise.toml` in repos under `/mnt/c`. `zsh -lc` and `bash -lc`, which do not read `.zshrc`, are out of scope.

On a fresh Ubuntu installation in WSL, run the following once afterward.
To apply the `wsl-conf` systemd setting, you also need `wsl --shutdown` on Windows.

```bash
# If install.sh could not install wl-clipboard (requires WSLg)
sudo apt-get update && sudo apt-get install -y wl-clipboard
# Install zsh and make it the login shell (.zshrc and j-cc / j-pi require zsh)
sudo apt-get install -y zsh && chsh -s "$(command -v zsh)"
# After opening a new terminal (install.sh already installed sheldon via mise)
sheldon lock

just harden-env   # Per-machine supply-chain protections (7-day quarantine for npm and uv, GOPROXY). Untracked
just wsl-conf     # Show the /etc/wsl.conf diff and sudo edit steps (exclude Windows PATH, enable systemd)

# After reopening WSL following wsl --shutdown, enable the unprivileged Podman API
# Stops without installing if the apt Podman candidate is below 5 (Ubuntu 24.04 has 4.9)
just podman-install
systemctl --user enable --now podman.socket

just doctor       # Verify: zsh, PATH-windows (WSL only), WSLg clipboard, Podman, and toolset
```

`just harden-env` writes a 7-day quarantine (`min-release-age=7`, `exclude-newer = "7 days"`) to `~/.npmrc` and `~/.config/uv/uv.toml`.
It exempts Pi extensions and their dependencies from the quarantine (putting `min-release-age=0` in `~/.pi/agent/npm/.npmrc`).
Each project's `pyproject.toml` declares its own 7-day quarantine for committed lockfiles.

### Container runtime

Standardize on Podman 5 or later as the runtime engine and mise-managed `podman-compose` as the Compose provider (the CLI that interprets and runs the configuration).
Do not fall back automatically to a Docker engine.
`just podman-install` only installs Podman and does not clone, deploy configs, or sync agent homes.
On Windows, use an exception that installs only Podman via winget (ADR 0067). The package is the upstream MSI `Podman.CLI`, installed for all users into `C:\Program Files\Podman`.
On Windows, `just podman-install` aligns with the latest `Podman.CLI` on every run. If the old `RedHat.Podman` is installed, it removes it first (the new MSI will not install while the old version is present; container, image, and machine data remain). If a machine is running, it stops without removing it. A UAC prompt appears.
Do not add a 7-day wait to Podman or the dedicated `podman-compose` / Dev Container CLI install environments, while keeping the quarantine for project dependencies and lockfiles unchanged.

The operator initializes and starts machines on macOS and Windows separately.
Install scripts and shell startup do not touch machines and do not delete existing Docker data.
On native Windows, you can run without a machine by keeping only the CLI and running containers with Podman on WSL.
Therefore, when the CLI is 5 or later and cannot reach the runtime engine, `just doctor` outputs INFO if native Windows has no machines (ADR-0077).
It outputs WARN when a machine exists but is unreachable, when the machine list cannot be read, or on any other OS.
If the reachable engine is below 5, it outputs ERR on any OS.
In a sandbox, you must pass the socket for the selected engine explicitly.
See [Dev Container guide](./.devcontainer/README.md) for steps and the permission scope of passing the socket.

### Windows (native)

Install on a clean machine with one line of PowerShell (ADR 0039).

```powershell
# To use another host's scoop manifest, set first: $env:DOTFILES_HOST = '<host>'
irm https://raw.githubusercontent.com/hironow/dotfiles/main/bootstrap.ps1 | iex
```

`bootstrap.ps1` checks for Podman 5 or later first and installs `Podman.CLI` via winget if missing (if already installed, it leaves it as is; use `just podman-install` to update to latest).
Next, it installs scoop, git, just, jq, mise, and pwsh, and clones to `~\dotfiles` over HTTPS.
Then it runs `add-scoop`, `deploy`, `harden-env`, `sync-agents`, `restore-skills-lock`, and `doctor`.
It is safe to run repeatedly; when done, open a new pwsh (where `$PROFILE` takes effect).

- **`just deploy` (Windows)**: Copies `starship.toml`, `gitignore-global`, and `config/mise/config.toml`, writes pwsh `$PROFILE` (`mise activate`, `starship init`, `MISE_NODE_COREPACK=0`, `j-cc` / `j-pi`), installs mise tools and Pi extensions, and loads `aliases.gitconfig` via `[include]`.
- **`just harden-env` (Windows)**: Also configures `%APPDATA%\uv\uv.toml`, Git `usr\bin` and `cmd` in User PATH, telemetry-disabling environment variables, and `CLAUDE_CODE_GIT_BASH_PATH` when needed (details: [`docs/runbook/windows-host.md`](./docs/runbook/windows-host.md)).
- **Scoop**: Records packages in `dump/<host>/scoop.json` and restores them with `just add-scoop`.
- **Ollama**: On machines with both Windows and WSL, standardize on Windows Scoop `extras/ollama-full`. WSL uses a loopback bridge or shared loopback and does not keep a Linux binary or models. `just doctor` detects configuration violations (details: [`docs/runbook/ollama-windows-wsl.md`](./docs/runbook/ollama-windows-wsl.md)).

After setting up SSH keys, switch the remote to SSH and fetch submodules.
Because `.gitmodules` sets `update = none` on all submodules so Dependabot clones do not stall on them, pass `--checkout` when fetching.

```powershell
git -C ~/dotfiles remote set-url origin git@github.com:hironow/dotfiles.git
git -C ~/dotfiles submodule update --init --checkout
```

## Daily operations

```shell
just help                       # List recipes

just sync-agents-preview        # Preview agent instruction sync (dry-run)
just sync-agents                # Sync to ~/.claude, etc. (all for every agent)
just claude-plugins-install     # Install required plugins into each Claude home (also runs deploy)
just lint-claude                # Validate Claude configs to distribute (ADR 0029)

just update-all                 # Update tools (mise, gh, Pi extensions, etc.)
just dump                       # Record installed packages in dump/<host>/
just add-brew                   # macOS: restore from record
just add-scoop                  # Windows: restore from record (ADR 0032)

just self-check                 # Light sanity check (with_tests=1 includes Podman tests)
just doctor                     # Diagnose tools, PATH, OS-specific settings, AI tools, CA, and kernel (exit 1 on ERR)
just validate-path-duplicates   # Check for duplicate PATH entries

mx uv sync                      # mx is a zsh alias for `mise exec --`
mx dotenvx run -- mise set      # Load encrypted .env into mise environment
gh do -- mise set               # Do the same with GitHub credentials
mx dotenvx set HELLO World      # Encrypt and write to .env
mx mise set WORLD=hello         # Write to mise environment without encryption
```

### Tests and CI gates

| Command | Description | Podman |
| --- | --- | --- |
| `just ci` | `just check` (Python, Go, shell, Markdown, and JS/TS lint; Pi extension and Go tests; Quint models), Claude config check, unit tests, semgrep rule tests, IaC tests, instruction budget, skill declarations, emulator lint, and forbidden tokens | No |
| `just ci-all` | `ci` + Dev Container sandbox tests + `install.sh` check (`just test-install` standalone) | Yes |
| `just ci-emu` | Emulator lint, startup, fast tests, and e2e | Yes |
| `just check-all` | prek hooks + `ci-all` (manual final gate before push; not a git hook, ADR 0085) | Yes |
| `just test` | Sandbox tests inside Dev Container (filter with `install`, `validate`, `versions`, `deploy`, or `check`, e.g., `just test-mark validate`) | Yes |

`tests/unit/` passes on native Windows too (POSIX-only checks are skipped).

Lines from `just doctor` start with `OK`, `WARN`, `ERR`, or `INFO`.
`WARN` means something to act on on that machine, `INFO` is check scope and facts, and `INFO` does not change the exit code (ADR 0066).

## Coding sessions with Jev

Running `j-cc 'your request'` or `j-pi 'your request'` in a working repository selects the thinking level for Claude Code or Pi and the model for the Codex worker based on the request, and starts the session.
`-c` (resume the most recent session) and `-r` (choose a session to resume) also work as usual.
`j-cc` sessions go through both rtk (command output compression) and the headroom proxy (compressing payloads sent to the model).
Initial setup, key locations, and verification (`just jev-headroom-verify rtk`) are in [`docs/runbook/jev-launchers.md`](./docs/runbook/jev-launchers.md).

## skill

Both custom ([hironow/skills](https://github.com/hironow/skills)) and third-party skills are declared in `dump/harness/skill-lock.json` (ADR 0038, ADR 0043, [`docs/agent-sync.md`](./docs/agent-sync.md)).
The skills CLI places the actual files in `~/.agents/skills` (the store), and `skills-place` creates relative symlinks to each agent home (`~/.claude*`, `~/.codex`, `~/.gemini`), or tracked copies where symlinks are unsupported.
For same-named skills, hironow/skills takes precedence (checked by `skills-lock-check` in `just ci`).
As an exception, Codex's `hatch-pet` places the [official openai/skills version](https://github.com/openai/skills/tree/49f948faa9258a0c61caceaf225e179651397431/skills/.curated/hatch-pet) directly at `~/.codex/skills/hatch-pet` and updates it with Codex's bundled `skill-installer`.
`skills-place` leaves this directory in place and reports it as 1 diff against the store (exit code 1).

```bash
just restore-skills-lock  # New machine: restore from declaration into store and place in homes
just skills-place         # Recreate home symlinks (idempotent)
just skills-update        # After merging hironow/skills, etc.: update store and place

# Adding a skill: let the CLI write only to the store (-a universal), update the declaration, then place
bunx skills add <repo> -g -s <name> -y -a universal
just dump-skills-lock
just skills-place
```

`just dump-skills-lock` rebuilds the declaration from the entire store on that machine, so review the diff before committing.
For third-party skills, declare only the needed skills (for example, narrow `googleworkspace/cli` to `gws-shared` and the 9 main services, excluding `persona-*` and `recipe-*`).
You can list each home with `just skills`, as in `just env=a skills ls -g` (`env=p` is `~/.claude`, `a` through `d` are `~/.claude-work-a` through `-d`).
Use `just skills` only for inspection, not for adding skills.

## Local development stack

`emulator/` (datastores and inspectors) lives in this repository (ADR 0014). `telemetry/` simply runs one upstream `grafana/otel-lgtm` container with no custom config (ADR 0072).
API and SaaS emulators run `vercel-labs/emulate` via `bunx` (ADR 0016, ADR 0055).
On macOS and Windows, heavy and amd64 services do not start by default so everything fits in the Podman machine memory.

```shell
just emu-up                          # Default is GCP core only (firebase, spanner, pgadapter, postgres; alias emu-up-lite)
just emu-up-only firebase-emulator   # Start a named service
just emu-up-group search             # Add a capability group to core (bigtable search graph vector ml inspect full)
just emu-up-full                     # All data services including heavy ones (excludes interactive *-cli services)
just emu-check                       # Status and endpoints
just emu-stop                        # Export firebase data and stop

just tel-up                          # Start telemetry (Grafana on :3000; stop with just tel-down)
just emu-api                         # Start API emulators in foreground on 4100-4108 (emulator/emulate/README.md)
```

HTTP UIs get fixed `https://<name>.localhost` URLs via [portless](https://github.com/vercel-labs/portless) (ADR 0015, ADR 0054).
Run `portless trust` (and `portless service install` if needed) on first setup, then register aliases after `portless proxy start`.
The list of aliases and excluded TCP ports is in [`docs/portless-urls.md`](./docs/portless-urls.md).

## Dev Container

`.devcontainer/devcontainer.json` (Debian 12, official Microsoft features, and the local `dotfiles-tools` feature) defines the shared environment for [Dev Container](https://containers.dev/) and CI (`devcontainers/ci`) (ADR 0002).
It includes `just`, `mise`, `prek`, `ruff`, `shellcheck`, `markdownlint-cli2`, Node.js (LTS), and five AI CLIs (`codex`, `antigravity`, `claude`, `copilot`, `pi`).
The operator authenticates each CLI once per container.
If the clone has `.git`, `postCreateCommand` installs prek hooks via `just install-hooks`.

- Claude Code: `/devcontainer`
- VS Code / Cursor: `Reopen in Container` via the Dev Containers extension
- JetBrains: `File > Remote Development > Dev Containers`

## MCP

`just deploy` registers the remote MCP servers declared in `dump/harness/mcp-servers.json` with Claude Code (every home), Codex, Pi and Antigravity (`just agent-mcp-install`, ADR 0087).

- A server that a Claude plugin already carries (context7, cloudflare, vercel) is left to that plugin in Claude Code.
- A server that needs a browser sign-in (cloudflare, vercel) asks for it once in each agent. Codex signs in as soon as the server is added, so the run prints that command for Codex instead of running it.
- A server that needs an API key (google-dev-knowledge) is never registered. The run prints its setup steps for each agent that lacks it.
- Chrome DevTools MCP comes from a required plugin (`dump/harness/claude-plugins.json`).

Set up by hand:

```bash
# k6: https://grafana.com/docs/k6/latest/release-notes/v1.6.0/#introducing-mcp-k6-ai-assisted-k6-script-writing-mcp-k6
claude mcp add --scope=user --transport=stdio k6 -- podman run --rm -i docker.io/grafana/mcp-k6

# Jaeger v2, per project (also copy to other agent config directories)
claude mcp add -s project -t http jaeger http://localhost:16686/api/ai/mcp/
```

## Other settings

### HTTPS for localhost

```shell
dig localhost.hironow.dev   # Ensure the A record points to 127.0.0.1
sudo certbot certonly --manual --preferred-challenges dns -d localhost.hironow.dev --config-dir ~/dotfiles/private/certificates
cd tools/simple-server && sudo mise x -- go run main.go   # Verify HTTPS response
```

### git

```bash
git config --global pull.rebase true   # Avoid merge commits on pull
```

### VS Code tunnel on WSL

```bash
curl -Lk 'https://code.visualstudio.com/sha/download?build=stable&os=cli-alpine-x64' -o vscode_cli.tar.gz
tar -xzf vscode_cli.tar.gz && mv code ~/.local/bin/code-cli
~/.local/bin/code-cli tunnel user login
code-cli tunnel --accept-server-license-terms --name test-my-wsl   # Initial check
code-cli tunnel service install && code-cli tunnel status
```

### Preventing reads of dotenvx keys without sudo

Without relying on agent deny settings, block reading `.env.keys` without sudo (experimental).

```bash
dotenvx set HELLO "WORLD"
sudo chmod 600 .env.keys
dotenvx decrypt --stdout        # EACCES: permission denied, open '.env.keys'
sudo dotenvx decrypt --stdout   # Readable
```

## References

- [mise](https://github.com/jdx/mise), [uv](https://github.com/astral-sh/uv), [gh do](https://github.com/k1LoW/gh-do), [dotenvx](https://dotenvx.com/)
- [HTTPS for localhost](https://blog.jxck.io/entries/2020-06-29/https-for-localhost.html)
- [browser toolbox](https://toolbox.googleapps.com/), [smarthome webrtc tool](https://smarthome-webrtc-validator.withgoogle.com/), [trickle ice checker](https://webrtc.github.io/samples/src/content/peerconnection/trickle-ice/)
- MCP list: <https://hub.docker.com/u/mcp>, <https://mcpmarket.com/en/categories/official>
- Skill list: <https://skills.sh/>
- Markdown: [YAML frontmatter](https://docs.github.com/en/contributing/writing-for-github-docs/using-yaml-frontmatter), [MDX](https://github.com/mdx-js/mdx)
