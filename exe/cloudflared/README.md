# exe/cloudflared/

Cloudflare Tunnel ingress configuration for `exe.hironow.dev`.

- `config.yaml` — ingress rules (added in subsequent commits)
- `cert.pem` / `*.json` — credentials, never committed (gitignored).
  The real values live in GCP Secret Manager; the tunnel daemon
  retrieves them at startup.

Tunnel routing target: the Coder workspace's HTTP/SSH ports, exposed
only to identities authenticated by Cloudflare Access (Zero Trust).
