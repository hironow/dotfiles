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

## Coder workspace template

Push the `dotfiles-devcontainer` template (or update an existing
version):

```bash
cdr templates push exe-dotfiles-devcontainer \
  -d exe/coder/templates/dotfiles-devcontainer \
  --variable project_id=gen-ai-hironow \
  --variable workspace_sa_email=$(just exe-output -raw exe_workspace_sa_email) \
  --variable coder_internal_url=$(just exe-output -raw coder_internal_url) \
  --message "<release note>" \
  --yes
```

Create / update / delete a workspace:

```bash
cdr create my-ws --template exe-dotfiles-devcontainer --yes
cdr ssh my-ws.dev
cdr delete my-ws --yes
```

Pre-merge testing of dev container changes:

1. Push the branch and let `publish-devcontainer.yaml` build a
   `:<sha>` image into Artifact Registry (or run a local
   `devcontainer build` and push manually).
2. Push a throwaway template version pinning that sha:

   ```bash
   cdr templates push exe-dotfiles-devcontainer \
     -d exe/coder/templates/dotfiles-devcontainer \
     --variable image=$(just exe-output -raw artifact_registry_repo)/devcontainer:<sha> \
     --variable project_id=gen-ai-hironow \
     --variable workspace_sa_email=$(just exe-output -raw exe_workspace_sa_email) \
     --variable coder_internal_url=$(just exe-output -raw coder_internal_url) \
     --yes
   cdr create my-ws --template exe-dotfiles-devcontainer --yes
   ```

3. Once verified, push another version with `:main` to revert.

The previous `git_branch` parameter (envbuilder-only) is gone:
the prebuilt-image template doesn't clone at workspace boot;
operator branch testing happens via the image tag instead.

## Tailscale auth-key rotation

The keys rotate automatically every 90 days because of:

```hcl
resource "time_rotating" "tailscale_keys" {
  rotation_days = 90
}
```

To force a rotation immediately, use the `just exe-replace` wrapper
so `TF_ENCRYPTION` is set; calling `tofu` directly will fail with a
state-decrypt error once encryption is active.

```bash
just exe-replace time_rotating.tailscale_keys
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

The tunnel secret is a `random_id`. Rotate via the `just exe-replace`
wrapper so `TF_ENCRYPTION` is supplied (raw `tofu apply` fails once
state is encrypted):

```bash
just exe-replace random_id.tunnel_secret
just exe-apply        # writes a new credentials JSON to Secret Manager
just exe-teardown vm  # force VM restart so cloudflared picks up the new file
just exe-apply
just exe-smoke
```

## Logging in via the Coder CLI

Two-layer auth: every request must carry **(a) the Cloudflare Access
service token** in HTTP headers AND **(b) the Coder session token**.
The Coder CLI does NOT pass arbitrary headers by default. Use the
`cdr` wrapper at [`exe/scripts/cdr`](../scripts/cdr) — it pulls the
service-token credentials from Secret Manager (cached for 5 min),
exports `CODER_HEADER_COMMAND`, then exec's `coder` with the original
arguments.

### Setup (once)

```bash
# 1. Install the Coder CLI via Homebrew. Mac is assumed to have
#    Homebrew preinstalled (per ADR 0005). The upstream
#    `curl https://coder.com/install.sh | sh` convenience installer
#    is intentionally NOT recommended here — the same TOFU concerns
#    that drove ADR 0007 on the control-plane VM apply to operator
#    machines too.
brew install coder/coder/coder

# 2. Symlink the cdr wrapper into ~/.local/bin.
just exe-cdr-install

# 3. Issue a Coder API token in the UI:
#    https://exe.hironow.dev/settings/tokens -> '+ Add token'
#    Copy the token once (it is not shown again).

# 4. First login. cdr handles all CF Access plumbing internally.
cdr login https://exe.hironow.dev --token <CODER_API_TOKEN>
```

### Day-to-day

```bash
cdr users list
cdr templates list
cdr workspaces list
cdr ssh <workspace>
```

The Coder session token persists in `~/.config/coderv2/session` after
the first `cdr login`, so subsequent commands need only the wrapper
(which re-reads CF Access headers each invocation; rotated service-
token credentials propagate within 5 minutes via the cache).

### Coder VS Code extension

The extension uses an external "Header Command" to inject extra HTTP
headers into every Coder API request — perfect for the CF Access
service token. After `just exe-cdr-install` symlinks the helper into
`~/.local/bin/cdr-header`, configure the extension to call it:

1. **Cmd+,** (macOS) / **Ctrl+,** to open Settings.
2. Search **`Coder: Header Command`**.
3. Set the value to the absolute path to `cdr-header`:

   ```text
   /Users/<you>/.local/bin/cdr-header
   ```

4. Save. Reload the window if the extension was already running.

The extension invokes the script before each request, the script
returns

   ```text
   CF-Access-Client-Id=<id>
   CF-Access-Client-Secret=<secret>
   ```

(secrets fetched from Secret Manager and cached for 5 min in
`~/.cache/exe-coder-cli/`), and the extension attaches those as HTTP
headers. After this, `Remote-SSH` and the Coder dashboard inside
VS Code work transparently.

### Manual flag form (if cdr is unavailable)

```bash
export CF_ACCESS_CLIENT_ID="$(gcloud secrets versions access latest \
  --secret=exe-coder-cli-client-id)"
export CF_ACCESS_CLIENT_SECRET="$(gcloud secrets versions access latest \
  --secret=exe-coder-cli-client-secret)"

# Coder CLI parses --header on '='. Use 'Name=Value', NOT 'Name: Value'.
coder login https://exe.hironow.dev --token <CODER_API_TOKEN> \
  --header "CF-Access-Client-Id=${CF_ACCESS_CLIENT_ID}" \
  --header "CF-Access-Client-Secret=${CF_ACCESS_CLIENT_SECRET}"

# Persist for shell session (also '=' separator, not ':'):
export CODER_HEADER_COMMAND='printf "CF-Access-Client-Id=%s\nCF-Access-Client-Secret=%s\n" "$CF_ACCESS_CLIENT_ID" "$CF_ACCESS_CLIENT_SECRET"'

coder users list
```

To rotate the service token (e.g. on suspected compromise):

```bash
just exe-replace cloudflare_zero_trust_access_service_token.coder_cli
just exe-apply
# then re-export CF_ACCESS_CLIENT_ID / CF_ACCESS_CLIENT_SECRET on the
# laptop from Secret Manager (the new versions have replaced the old).
```

## `WARN: CODER_TELEMETRY is deprecated` in coder.service journal

This is upstream noise from Coder's serpent CLI library. Telemetry is
in fact disabled (look for `telemetry disabled, unable to notify of
security issues` in the same journal). Both escape paths trip the
warning:

- `Environment=CODER_TELEMETRY_ENABLE=false` (current) →
  `WARN: CODER_TELEMETRY is deprecated`
- `ExecStart=... --telemetry=false` (tried, reverted) →
  `WARN: --telemetry-enable is deprecated`, plus a
  `command not found` regression in GCE's metadata-script-runner
  heredoc handling.

The env path is the safer of the two and what the unit currently
uses. Re-evaluate when Coder fixes the alias-warning logic in
serpent (track upstream).

## Stale exe-coder devices in the tailnet

`tailscale_tailnet_key.exe_coder` is `ephemeral = true`, so the VM
self-removes from the tailnet on every stop (preemptible 24h cycle,
manual `just exe-down`, `just exe-replace ...`). New boot creates a
fresh device.

If older deploys (before the fix) left stale `exe-coder-N` entries:

1. Confirm the active device is *Connected* in
   <https://login.tailscale.com/admin/machines>.
2. For each stale `exe-coder-N` row, click the menu → **Remove device**.
3. The MagicDNS name `exe-coder.<tailnet>.ts.net` resolves to the
   active device automatically; downstream consumers do not need
   updating.

## My laptop's `tailscale status` doesn't list `exe-coder`

If the device is **visible in <https://login.tailscale.com/admin/machines>**
but absent from local `tailscale status`, the laptop is on the
right tailnet but ACL rules are filtering peer visibility.

```bash
# Sanity: same tailnet, same identity
tailscale status --json | jq -r '.CurrentTailnet.Name'   # expected: hironow.github
tailscale status --json | jq '.BackendState'             # expected: "Running"

# Effective capabilities (admin / owner / etc.)
tailscale status --json | jq '.Self.Capabilities'

# Peer list (exe-coder should be in here once ACLs allow)
tailscale status --json | jq '.Peer | [.[] | .HostName]'

# Direct ping by MagicDNS name
tailscale ping exe-coder
```

The ACL is set up with **two** break-glass rules so a user is
guaranteed reach to `tag:exe-coder` regardless of how their identity
got mapped:

1. `autogroup:admin` — anyone with the admin role on this tailnet.
   GitHub-OAuth tailnets like `hironow.github` produce identities of
   the form `<gh-username>@github`, NOT the email used to sign in,
   so this is the rule that actually matches.
2. `group:owners = ["hironow365@gmail.com"]` — explicit email
   allowlist as a redundant secondary path.

If neither path produces visibility, force a re-fetch of the policy
on the laptop:

```bash
tailscale down && tailscale up
# or, to fully reset:
sudo tailscale set --auto-update=false
sudo tailscale logout && sudo tailscale up
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
