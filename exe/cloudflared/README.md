# exe/cloudflared/

Cloudflare Tunnel ingress configuration for `exe.hironow.dev`.

The tunnel and its ingress rules are managed entirely by OpenTofu
(see [`../../tofu/exe/cloudflare.tf`](../../tofu/exe/cloudflare.tf))
— there are no static config files in this directory. Tunnel
credentials live in GCP Secret Manager
(`exe-cloudflared-credentials`); the `cloudflared` daemon on the
control-plane VM fetches them at startup via `gcloud secrets
versions access`.

## Ingress rules

Defined in `cloudflare_zero_trust_tunnel_cloudflared_config.exe`:

| Hostname | Origin | Notes |
|---|---|---|
| `exe.hironow.dev` | `http://localhost:7080` | Coder UI, gated by Cloudflare Access OIDC; only `var.owner_email` is admitted |
| catch-all | `http_status:404` | Returns 404 for anything not matched (incl. accidental `*.sandbox.hironow.dev` until P-mode lands) |

Both real routes use `http2_origin = true` and
`no_tls_verify = true` (loopback origin, TLS terminates at the CF
edge).

## Related docs

- [`../docs/architecture.md`](../docs/architecture.md) — full edge / tunnel diagram and trust boundary table
- [`../docs/runbook.md`](../docs/runbook.md) — operator workflow
  (tunnel credential rotation, debugging tunnel state)
- [`../../tofu/exe/cloudflare.tf`](../../tofu/exe/cloudflare.tf)
  — actual IaC
