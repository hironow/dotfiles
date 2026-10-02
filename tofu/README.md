# tofu/

OpenTofu (1.10+) infrastructure-as-code stacks. Each subdirectory is an
isolated stack with its own backend / state file.

| Stack | Purpose |
|---|---|
| [`tailnet/`](./tailnet/) | The tailnet's policy file, and nothing else. State in the old personal project's bucket under a passphrase; see its README for why not the private project's |

`tailnet/` is the only stack here. The exe stacks that used to sit beside it are
operated from elsewhere now, and the Coder stack before them is destroyed — the
section below is the record of what that destruction deliberately left behind.

## The retired stack, and what it left outside IaC

The GCE workspace stack that used to live in `exe/` is **destroyed**: its state
is empty and the project it ran in holds none of its resources.

Two sets of objects deliberately outlived it, and neither is in any state file,
so no `tofu plan` here will mention them:

- **The tailnet's ACL**, which `tailnet/` took over by import. It was dropped
  from the old stack's state first (a `removed` block with `destroy = false`), so
  the policy never had two owners and never had none.
- **Eight Cloudflare objects** — a tunnel and its config, two DNS records, two
  Access policies, a service token and an Access application. The operator
  decided to keep them in place rather than destroy them, so they were dropped
  from the state the same way. **They are unmanaged: nothing in this repo reads,
  plans or deletes them**, and no recipe here needs a Cloudflare API token. If
  they are ever to be adopted again, they are imported like any pre-existing
  resource; if they are to go, that is done in Cloudflare.

The rule the two cases share: anything that entered a stack's state through an
`import` block pre-existed that stack, so it is forgotten rather than destroyed.

## Conventions

- `tofu` CLI only — never `terraform` (license boundary).
- Remote state in GCS bucket per stack; state encryption enabled.
- `terraform.tfvars` is gitignored. Real values live in GCP Secret
  Manager and are wired in via `data "google_secret_manager_secret_version"`.
- `.terraform.lock.hcl` IS tracked (HashiCorp recommends this so
  every operator + CI run resolves the same provider plugin
  versions). The runtime cache dir `.terraform/` and state files
  stay ignored.
- Every storage sink declares an explicit bound, which
  `scripts/check_storage_bounds.py` enforces in `just check`.
- Run `tofu fmt -recursive` before commit.

## Related docs

- [`tailnet/README.md`](./tailnet/README.md) — the tailnet stack, its state and
  its guards
- [`../docs/adr/`](../docs/adr/) — Architecture Decision Records
