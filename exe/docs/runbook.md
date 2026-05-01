# Runbook — exe.hironow.dev

Operational procedures for the stack defined in
[`tofu/exe`](../../tofu/exe/) and accompanying scripts in
[`exe/scripts`](../scripts/).

## Prerequisites

The operator's local machine needs:

| Tool | Why |
|---|---|
| `tofu` ≥ 1.10 | apply / plan / state encryption |
| `gcloud` | bucket creation, VM describe, Secret Manager |
| `dig`, `curl` | smoke checks |
| `jq` | parse `tofu output -json` in smoke.sh |
| `shellcheck` (dev only) | lint scripts |
| `tailscale` (optional) | tailnet reachability check |

Auth state:

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project gen-ai-hironow
```

Required env vars (set per shell session, never committed):

```bash
export CLOUDFLARE_API_TOKEN='...'   # zone:read, dns:edit, access:edit, tunnel:edit on hironow.dev
export TAILSCALE_API_KEY='...'      # OAuth client w/ auth_keys:write,acl:read
export TF_VAR_cf_account_id='...'   # Cloudflare account ID
export TF_VAR_tailnet='...'         # tailnet identifier, e.g. user@github
```

## First-time setup

```bash
just exe-bootstrap                          # enable APIs, create state bucket, gen passphrase
cp tofu/exe/terraform.tfvars.example tofu/exe/terraform.tfvars
$EDITOR tofu/exe/terraform.tfvars           # fill in cf_account_id, tailnet
just exe-init                               # tofu init
just exe-plan                               # review the plan
just exe-apply                              # apply
just exe-smoke                              # confirm health
```

After the first apply succeeds:

1. Visit `https://exe.hironow.dev/` — should redirect to Cloudflare
   Access OIDC.
2. Log in as `owner_email` — the Coder UI loads (allow ~2 minutes on
   first boot for the binary download + embedded postgres init).
3. Retrieve the auto-generated admin password from the VM:

   ```bash
   gcloud compute ssh exe-coder --zone=asia-northeast1-a \
     --command='sudo cat /var/lib/coder/.admin_password'
   ```

   Use it for the first login, then change it via the Coder UI.
4. From a Tailscale-connected device, `ssh exe-coder` (Tailscale SSH).

## Daily operations

| Task | Command |
|---|---|
| Plan diff | `just exe-plan` |
| Apply | `just exe-apply` |
| Inspect outputs | `just exe-output` (or `just exe-output -json`) |
| Smoke checks | `just exe-smoke` |
| Stop the VM (cheap pause) | `just exe-teardown vm` |
| Recreate the VM | `just exe-apply` (idempotent) |

## Tailscale auth-key rotation

The keys rotate automatically every 90 days because of:

```hcl
resource "time_rotating" "tailscale_keys" {
  rotation_days = 90
}
```

To force a rotation immediately:

```bash
cd tofu/exe
tofu apply -replace=time_rotating.tailscale_keys
cd -
just exe-apply        # picks up new keys, rebuilds VM if startup-script changed
just exe-smoke
```

Old key versions stay in Secret Manager. Destroy them only after
confirming no agent or VM is still authenticated with them:

```bash
gcloud secrets versions list exe-tailscale-coder-authkey
gcloud secrets versions destroy <N> --secret=exe-tailscale-coder-authkey
```

## Cloudflare tunnel credentials rotation

The tunnel secret is a `random_id`. To rotate:

```bash
cd tofu/exe
tofu apply -replace=random_id.tunnel_secret
cd -
just exe-apply        # writes a new credentials JSON to Secret Manager
just exe-teardown vm  # force VM restart so cloudflared picks up the new file
just exe-apply
just exe-smoke
```

## Incident — Tailscale ACL locked me out

The `tailscale_acl` resource pushes `exe/tailscale/acl.hujson` on every
`tofu apply`. A bad ACL can cut your operator devices out of the
tailnet. Two safety nets:

1. **Tailscale's built-in 24h grace period** — for 24 hours after a
   destructive ACL change, an admin signed in to
   <https://login.tailscale.com/admin/acls> can click "Revert" and
   restore the previous policy. Use this first.
2. **`lifecycle.prevent_destroy = true`** is set on
   `tailscale_acl.this`, so `tofu destroy` cannot remove the ACL in
   one go. To intentionally destroy, remove the lifecycle block in a
   separate commit, then run destroy.

If the grace period is gone:

1. Sign in to the Tailscale admin UI from a device that already
   carries `tag:owner` (laptop, phone). The UI itself is reachable
   over the public internet via SSO; tailnet connectivity is not
   required to log in.
2. Edit the ACL JSON directly to add a permissive rule that lets your
   current device class back in.
3. Then fix the source acl.hujson and re-apply.

## Incident — Access policy locked me out

If the Cloudflare Access policy is misconfigured and `owner_email` no
longer matches:

1. Use the Cloudflare dashboard to set the application's **Bypass**
   policy to your IP for 1 hour.
2. Fix `var.owner_email` (or the include rule in `cloudflare.tf`).
3. `just exe-apply`.
4. Remove the bypass.

## Incident — VM is preempted

Preemptible VMs auto-stop within 24h. To recover:

```bash
just exe-apply
just exe-smoke
```

Preemption preserves the boot disk (`auto_delete = true` only fires on
explicit destroy), so the next boot replays the startup-script and
re-joins the tailnet.

To switch off preemption permanently:

```hcl
# tofu/exe/terraform.tfvars
preemptible = false
```

then `just exe-apply`.

## Tearing it down

| Goal | Command |
|---|---|
| Pause for the night | `just exe-teardown vm` |
| Tear the whole stack but keep state | `just exe-teardown stack` |
| Wipe everything including state bucket | `just exe-teardown nuke` (asks to type `NUKE`) |

After `nuke`, run `just exe-bootstrap` again to start over.

## Cost monitoring

GCS state bucket and Secret Manager are essentially free. The VM is
the only meaningful cost line. To check this month's GCE spend:

```bash
gcloud billing budgets list 2>/dev/null   # if budgets are configured
gcloud beta billing accounts list
# Or use the GCP console -> Billing -> Reports filtered by labels:
#   stack=exe, managed-by=opentofu
```

The `common_labels` declared in
[`tofu/exe/locals.tf`](../../tofu/exe/locals.tf) is propagated to the
VM, disk, and Secret Manager secrets, which makes label-based cost
attribution work out of the box.
