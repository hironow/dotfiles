# exe/scripts/

Operational scripts for `exe.hironow.dev` (added in subsequent commits):

- `bootstrap.sh` — first-time provisioning (tofu apply + cloudflared login)
- `teardown.sh` — destroy GCE workspace, keep Cloudflare/Tailscale state
- `smoke.sh` — post-deploy connectivity checks (Tailscale up, CF Access OK, SSH reachable)

All scripts must be idempotent (per `scripts-guidelines` in CLAUDE.md).
