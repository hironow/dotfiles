# tofu/tailnet

The tailnet's policy file (`tailscale_acl.this`, [`acl.hujson`](./acl.hujson)),
and nothing else. Stacks that put a device on the tailnet mint their own tagged
auth keys; this stack says which tags exist, who may issue them, and what each
may reach.

## Operating it

```sh
just tailnet-init                  # backend: the old personal project's state bucket, prefix tailnet
just tailnet-test                  # offline: mock provider, no credentials
just tailnet-plan                  # needs TAILSCALE_API_KEY (or an OAuth client) and that project's ADC
just tailnet-plan-summary --expect-changes expected-changes/<list>.txt
just tailnet-apply                 # OPERATOR ONLY, the saved plan above
```

`terraform.tfvars` is gitignored; see
[`terraform.tfvars.example`](./terraform.tfvars.example).

The Tailscale credential needs the policy file's read and write scopes, and
device read for the retirement sheet's tag check. It comes from the
environment only, so it never reaches the state or a saved plan.

## Guards

- `prevent_destroy`: a destroy would put the tailnet back on Tailscale's
  default policy, or lock the owner out. To move the ACL to another stack,
  drop it from this one with a `removed` block (`destroy = false`) and import
  it there.
- [`tests/acl.tofutest.hcl`](./tests/acl.tofutest.hcl) pins both break-glass
  rules and the owner's rule.

## State

The state sits in the old personal project's bucket
(`gen-ai-hironow-tofu-state`) under the prefix `tailnet`. A passphrase encrypts
the state and saved plans: pbkdf2 over `~/.config/tofu/tailnet.passphrase`,
aes_gcm, enforced. `just _tailnet-encryption` builds the `TF_ENCRYPTION`
payload. The passphrase in `main.tf` is a sentinel, so a run without
`TF_ENCRYPTION` fails closed instead of writing state nobody can read back.

Generate the passphrase once on each machine that plans this stack:

```sh
umask 077 && openssl rand -base64 48 > ~/.config/tofu/tailnet.passphrase
```

The state does not use the exe project's bucket or KMS key. This repo is
public and that project is private: either would put a private identifier in a
public backend and tie the two lifetimes together.

If the passphrase is lost, the state is unreadable, but nothing on the tailnet
changes. Start a fresh state and import the ACL again (`adopt_live_acl`, on by
default). The next plan shows only the difference from `acl.hujson`.

To move the state to another bucket, with access to both:

1. Run `just tailnet-init`, then `tofu state pull > tailnet.tfstate`
   (decrypted with the current passphrase).
2. Point `backend "gcs"` at the new bucket and run `tofu init -migrate-state`,
   or run a plain `init` and push the pulled file with `tofu state push`.
3. Run `just tailnet-plan`. It must say "No changes".
