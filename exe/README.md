# exe/

Runtime artifacts and configuration for `exe.hironow.dev` — a personal
self-hosted clone of [exe.dev](https://exe.dev) layered on top of:

- **Coder** (Apache-2.0) — workspace orchestrator
- **Tailscale** — mesh VPN with tagged auth keys for AI agent delegation
- **Cloudflare Tunnel + Access** — identity-aware reverse proxy

The Coder workspace template references this repository's
`.devcontainer/devcontainer.json` (built from
`tests/docker/JustSandbox.Dockerfile`), so the agent's environment
matches CI exactly.

## Layout

| Path | Purpose |
|---|---|
| `coder/` | Coder workspace template (Terraform) |
| `cloudflared/` | Tunnel ingress config (cert + credentials live in Secret Manager) |
| `tailscale/` | ACL (`acl.hujson`), tag definitions for `tag:owner` / `tag:agent` |
| `scripts/` | Bootstrap, teardown, smoke-test scripts |
| `docs/` | Architecture and runbook |

## Provisioning

Infrastructure (GCE, IAM, Secret Manager, Cloudflare DNS, Tailscale auth
keys) is declared in [`tofu/exe/`](../tofu/exe/) and applied with
OpenTofu. This directory holds the artifacts the running stack consumes
at runtime.

## Architecture

```
+-----------+       Tailscale (tag:agent)        +---------------+
| AI Agent  |  ---------------------------->     |  Coder        |
+-----------+                                    |  workspace    |
                                                 |  on GCE       |
+-----------+       Cloudflare Access            +---------------+
| hironow   |  ---------------------------->            ^
| (laptop)  |  (Zero Trust, identity-aware)             |
+-----------+                                           |
                                                  reads .devcontainer/
                                                        |
                                                        v
                                                  +----------------+
                                                  | dotfiles repo  |
                                                  | JustSandbox    |
                                                  +----------------+
```

Legend / 凡例:

- AI Agent: 委譲先 AI Agent
- Coder workspace: 開発用ワークスペース
- Cloudflare Access: 認証付きリバースプロキシ
- Zero Trust: ゼロトラストアクセス
- dotfiles repo: 本リポジトリ
