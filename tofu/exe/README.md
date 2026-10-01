# tofu/exe/

OpenTofu stack provisioning `exe.hironow.dev`.

## Retirement (Phase 7)

This stack is being retired. Its configuration now only lets go of what
outlives it and destroys the rest, run from the old project's step sheet:

- Forgotten, never destroyed (`removed` blocks, `destroy = false`): the
  tailnet's ACL (tofu/tailnet imports it), the shared Workload Identity
  pool `github` (it pre-existed this stack, and other repositories use
  it), and the eight Cloudflare objects, which the operator parks
  unmanaged.
- `tofu plan -destroy` ignores `removed` blocks, so those ten leave the
  state first, in one targeted plan held to
  `expected-changes/retire-2-forget.txt`; the destroy comes after.
- The database is started and unprotected first
  (`expected-changes/retire-1-database.txt`), so its deletion leaves a
  30-day final backup.
- No step needs a Cloudflare API token: nothing here reads a Cloudflare
  attribute any more.

## Inputs

Source of truth: [`variables.tf`](./variables.tf). Defaults shown are
the values currently committed; values without a default are
operator-supplied via `terraform.tfvars`.

### Deployment scope

| Variable | Default | Description |
|---|---|---|
| `stack_mode` | (required, `terraform.tfvars`) | `active` or `mothballed` (ADR 0034): mothballed stops Cloud SQL and removes the VM + uptime monitoring |
| `gcp_project_id` | `gen-ai-hironow` | GCP project (single-project, single-stack) |
| `gcp_region` | `asia-northeast1` | Primary region |
| `gcp_zone` | `asia-northeast1-a` | Primary zone |
| `domain` | `exe.hironow.dev` | Cloudflare-managed apex |
| `sandbox_subdomain` | `sandbox.hironow.dev` | Wildcard parent for Coder app preview hostnames |
| `tailnet` | (required, `terraform.tfvars`, e.g. `hironow.github`) | Tailscale tailnet identifier |
| `owner_email` | `hironow365@gmail.com` | CF Access allowlist + uptime alert recipient |

### Control-plane VM

| Variable | Default | Description |
|---|---|---|
| `machine_type` | `e2-small` | GCE machine type for the `exe-coder` VM |
| `preemptible` | `true` | Use SPOT (24h auto-stop, ~70% discount) |
| `vm_image` | `projects/ubuntu-os-cloud/global/images/family/ubuntu-2404-lts-amd64` | Control-plane VM image (ubuntu-24.04 LTS) |
| `boot_disk_size_gb` | `30` | Boot disk GiB (validated 20-200) |
| `coder_version` | `v2.31.11` | Pinned Coder server release tag (see [ADR 0007](../../docs/adr/0007-coder-server-install-hardening.md)) |
| `coder_sha256` | (in `variables.tf`) | sha256 of `coder_<ver>_linux_amd64.tar.gz` from release's `checksums.txt` |

### Cloud SQL data plane (ADR 0010)

| Variable | Default | Description |
|---|---|---|
| `cloud_sql_tier` | `db-f1-micro` | Postgres instance tier (ENTERPRISE edition; ENTERPRISE_PLUS rejects f1-micro) |
| `cloud_sql_postgres_version` | `POSTGRES_16` | Postgres major version |
| `cloud_sql_disk_size_gb` | `10` | Initial SSD disk size; auto-resize is enabled |
| `cloud_sql_proxy_version` | `v2.21.3` | Pinned cloud-sql-proxy v2 release |
| `cloud_sql_proxy_sha256` | (in `variables.tf`) | sha256 of the linux/amd64 binary |

## Files

| Path | Purpose |
|---|---|
| [`main.tf`](./main.tf) | Backend (GCS), providers, VPC/subnet/Service-Networking-API enablement |
| [`variables.tf`](./variables.tf) | Input variables (incl. Coder + cloud-sql-proxy pins) |
| [`outputs.tf`](./outputs.tf) | Workspace SA email, AR repo, control-plane URL, Cloud SQL connection name, IAM DB user, uptime check / alert policy names |
| [`coder.tf`](./coder.tf) | Control-plane VM + startup_script: systemd units for `coder.service`, `cloudflared-exe.service`, `cloud-sql-proxy.service` (apt-key fingerprint pinned), `deny-all-ingress` firewall, `roles/{logging.logWriter,monitoring.metricWriter,compute.instanceAdmin.v1,iam.serviceAccountUser}` on the VM SA |
| [`cloudsql.tf`](./cloudsql.tf) | Cloud SQL Postgres instance (`exe-coder-pg`, ENTERPRISE, ZONAL, private-IP-only via VPC peering), IAM DB user (`google_sql_user.coder_iam` for `--auto-iam-authn`), `cloudsql.client` + `cloudsql.instanceUser` on the VM SA, Postgres-admin bootstrap secret (ADR 0010) |
| [`monitoring.tf`](./monitoring.tf) | Cloud Monitoring uptime check on `/healthz` (5 min, 3 regions), email alert policy on 2 consecutive failures |
| [`tailscale.tf`](./tailscale.tf) | Tagged auth keys (`tag:exe-coder` / `tag:exe-workspace` / `tag:agent`), ACL bootstrap, 90-day rotation |
| [`cloudflare.tf`](./cloudflare.tf) | Tunnel + Access policy + DNS records + CF Access service tokens |
| [`artifact_registry.tf`](./artifact_registry.tf) | Dev container image AR repo (`devcontainer:main` + `devcontainer:<sha>`) |
| [`iam.tf`](./iam.tf) | Workload Identity Federation (GHA → AR) + workspace SA + AR reader/writer grants |
| [`locals.tf`](./locals.tf) | Hostnames, tag names, common labels |
| [`.terraform.lock.hcl`](./.terraform.lock.hcl) | Provider plugin lockfile (tracked) |

## State

Backend: GCS bucket `gs://gen-ai-hironow-tofu-state/exe/`
(bucket creation is a one-time bootstrap step; see
[`../../exe/scripts/bootstrap.sh`](../../exe/scripts/bootstrap.sh)).

State encryption: native `tofu` state encryption (1.7+) with passphrase
from `~/.config/tofu/exe.passphrase` (0600 mode, gitignored).

## Lifecycle

```bash
just exe-plan            # tofu plan
just exe-apply           # tofu apply
just exe-down            # tofu destroy (keeps state)
just exe-plan-mothball   # targeted plan of the mothball slice -> mothball.tfplan
just exe-apply-mothball  # apply the saved mothball plan file
just exe-apply-wake      # start Cloud SQL alone (wake step 1)
```

Mothball / wake workflow: [runbook.md › Mothball / wake](../../exe/docs/runbook.md#mothball--wake-idle-cost).

## Related docs

- [`../../exe/docs/architecture.md`](../../exe/docs/architecture.md)
  — full architecture diagram and trust boundary table
- [`../../exe/docs/runbook.md`](../../exe/docs/runbook.md) —
  operator workflow (apply, smoke, key rotation, Coder bump)
- [`../../docs/adr/`](../../docs/adr/) — architectural decisions
  (debian-12 dev container, prebuilt image, Actions hardening,
  tailnet routing, install path, mise pinning, Coder hardening)
- [`../../tests/exe/test_startup_script.py`](../../tests/exe/test_startup_script.py)
  — heredoc extraction + bash lint + systemd-analyze for the
  control-plane startup script
