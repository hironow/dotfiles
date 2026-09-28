# tofu/tailnet

The tailnet's policy file (`tailscale_acl.this`, [`acl.hujson`](./acl.hujson)),
and nothing else. Stacks that put a device on the tailnet mint their own tagged
auth keys; this stack says which tags exist, who may issue them, and what each
may reach.

## Operating it

```sh
just tailnet-init                  # backend: the exe project's state bucket, prefix tailnet
just tailnet-test                  # offline: mock provider, no credentials
just tailnet-plan                  # needs TAILSCALE_API_KEY (or an OAuth client) and the exe project's ADC
just tailnet-plan-summary --expect-changes expected-changes/<list>.txt
just tailnet-apply                 # OPERATOR ONLY, the saved plan above
```

`terraform.tfvars` and `backend.hcl` are gitignored; see
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

## Where the state lives, and what that ties it to

The state sits in the exe project's state bucket under the prefix `tailnet`,
encrypted with the KMS key exe-platform owns, like exe-cluster's. The tailnet
therefore depends on the exe project: if that project, its bucket or its key
goes, this state goes with it.

To move it first, with the credentials of both places:

1. `just tailnet-init`, then `tofu state pull > tailnet.tfstate` (decrypted
   through the current key);
2. point `backend.hcl` and `state_kms_key` at the new bucket and key, and run
   `tofu init -migrate-state`, or push the pulled file with `tofu state push`
   after a plain `init`;
3. `just tailnet-plan` must then say "No changes".

If the state were lost anyway, nothing on the tailnet changes: import the ACL
again (`adopt_live_acl`, on by default) and the next plan shows only the
difference from `acl.hujson`.
