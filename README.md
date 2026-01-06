# dotfiles

My configuration for Zsh, Mise, Just, and more.

## Installation

Requires `curl` and `git`.

```shell
bash -c "$(curl -fsSL https://raw.githubusercontent.com/hironow/dotfiles/main/install.sh)"
```

> [!NOTE]  
> Mac, Linux, Windows([WSL](https://learn.microsoft.com/en-us/windows/wsl/)内Linux)へ対応

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

## setup

```shell
# check A record for localhost -> 127.0.0.1
dig localhost.hironow.dev

# create/update cert for https
sudo certbot certonly --manual --preferred-challenges dns -d localhost.hironow.dev --config-dir ${config_root}/private/certificates

# check simple-server for https localhost
cd tools/simple-server
sudo mise x -- go run main.go
```

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
# root
claude mcp add -s user chrome-devtools bunx chrome-devtools-mcp@latest
claude mcp add -s user -t http deepwiki https://mcp.deepwiki.com/mcp
claude mcp add -s user -t http bun https://bun.com/docs/mcp

# per project
## ... anything
```
