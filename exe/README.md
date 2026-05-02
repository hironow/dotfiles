# exe/

Runtime artifacts and configuration for `exe.hironow.dev` — a personal
self-hosted clone of [exe.dev](https://exe.dev) layered on top of:

- **Coder** (Apache-2.0) — workspace orchestrator
- **Tailscale** — mesh VPN with tagged auth keys for AI agent delegation
- **Cloudflare Tunnel + Access** — identity-aware reverse proxy

The Coder workspace template references this repository's
`.devcontainer/devcontainer.json` (image + features form on
debian-12) — the same SoT consumed by local IDE and CI — so the
agent's environment matches CI exactly.

## Layout

| Path | Purpose |
|---|---|
| [`coder/`](./coder/) | Coder workspace template (gcp-vm-container, prebuilt image) |
| [`cloudflared/`](./cloudflared/) | Tunnel ingress doc (rules live in OpenTofu) |
| [`tailscale/`](./tailscale/) | ACL (`acl.hujson`), tag definitions for the four-tag Pattern A model |
| [`scripts/`](./scripts/) | `cdr` CF-Access wrapper + bootstrap / teardown / smoke shell |
| [`docs/`](./docs/) | [Architecture](./docs/architecture.md) + [Runbook](./docs/runbook.md) |

## Provisioning

Infrastructure (GCE, IAM, Secret Manager, Cloudflare DNS, Tailscale
auth keys, Artifact Registry, Workload Identity Federation) is
declared in [`../tofu/exe/`](../tofu/exe/) and applied with
OpenTofu. This directory holds the runtime artifacts the stack
consumes (template HCL, ACL, scripts).

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

## Related docs

- [`docs/architecture.md`](./docs/architecture.md) — full
  architecture with trust boundary table
- [`docs/runbook.md`](./docs/runbook.md) — operator playbook
- [`../docs/intent.md`](../docs/intent.md) — requester intent
  (why this stack exists)
- [`../docs/adr/`](../docs/adr/) — Architecture Decision Records
- [`../tofu/exe/README.md`](../tofu/exe/README.md) — IaC overview
