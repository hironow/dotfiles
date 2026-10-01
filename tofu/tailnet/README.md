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
  it there, the way this stack took it over from the retired exe stack.
- Both break-glass rules and the owner's rule are pinned by
  [`tests/acl.tofutest.hcl`](./tests/acl.tofutest.hcl).

## Where the state lives, and why not with exe

The state sits in the OLD personal project's state bucket
(`gen-ai-hironow-tofu-state`) under the prefix `tailnet`, encrypted by
passphrase: pbkdf2 over `~/.config/tofu/tailnet.passphrase`, aes_gcm, enforced
for the state and for saved plans. `just _tailnet-encryption` assembles the
`TF_ENCRYPTION` payload; the passphrase in `main.tf` is a sentinel, so a run
without it fails closed rather than writing state nobody can read back.

Generate the passphrase once, on each machine that plans this stack:

```sh
umask 077 && openssl rand -base64 48 > ~/.config/tofu/tailnet.passphrase
```

It is the same mechanism the retired Coder stack used, with its own passphrase
file: that stack's goes when the stack does.

Not the exe project's bucket or KMS key, although this stack's ACL once
belonged to a stack in that project. This repo is public and that project is
private: its bucket is named after it, and its KMS key belongs to it, so either
would put a private identifier in a public repo's backend and tie the two
lifetimes together. The old personal project's bucket already holds other
stacks' state and outlives the Coder retirement.

If the passphrase is lost, the state is unreadable — but nothing on the tailnet
changes. Start a fresh state, import the ACL again (`adopt_live_acl`, on by
default) and the next plan shows only the difference from `acl.hujson`.

To move the state to another bucket later, with access to both:

1. `just tailnet-init`, then `tofu state pull > tailnet.tfstate` (decrypted
   through the current passphrase);
2. point `backend "gcs"` at the new bucket and run `tofu init -migrate-state`,
   or push the pulled file with `tofu state push` after a plain `init`;
3. `just tailnet-plan` must then say "No changes".
