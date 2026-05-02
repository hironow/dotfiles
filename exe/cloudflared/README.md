# exe/cloudflared/

Cloudflare Tunnel ingress for `exe.hironow.dev`. The tunnel +
ingress rules are managed in
[`../../tofu/exe/cloudflare.tf`](../../tofu/exe/cloudflare.tf);
credentials live in Secret Manager (`exe-cloudflared-credentials`).

See [`../docs/architecture.md`](../docs/architecture.md) for the
full ingress table and trust boundary, and
[`../docs/runbook.md`](../docs/runbook.md) for tunnel operations.
