# tofu/

OpenTofu stacks. Each subdirectory is one stack with its own backend and state.

| Stack | Purpose |
|---|---|
| [`tailnet/`](./tailnet/) | The tailnet's policy file, and nothing else |

`tailnet/` is the only stack. Some objects that a retired stack left in place
(eight Cloudflare objects) are in no state file, so no plan here shows them.
[ADR 0045](../docs/adr/0045-coder-control-plane-retired.md) lists them and the
rule behind it.

## Conventions

- Use the `tofu` CLI only, never `terraform` (license boundary). The version is
  pinned in [`config/mise/config.toml`](../config/mise/config.toml).
- State lives in a GCS bucket, with state encryption on.
- `terraform.tfvars` is gitignored. Each stack ships a
  `terraform.tfvars.example`.
- `.terraform.lock.hcl` is tracked, so every operator and CI run gets the same
  provider versions. `.terraform/`, state files and saved plans stay ignored.
- Every storage sink declares an explicit bound.
  `scripts/check_storage_bounds.py` enforces this in `just check`.
- `just test-iac` runs every stack's offline `tofu test` suite (part of
  `just ci`). Providers come from a cache, `opentofu/plugin-cache` under an
  absolute `$XDG_CACHE_HOME`, else under `~/.cache`; the IaC CI workflow keeps
  the same cache with `actions/cache`, keyed on the lock files. Only a run
  with an empty cache downloads a provider (the tailscale one comes from
  github.com release assets). OpenTofu uses a cached provider only when it
  matches the stack's `.terraform.lock.hcl`. If `tofu init` reports that a
  cached package "does not match the content of the downloaded package",
  delete that cache directory and run again.
- Run `tofu fmt -recursive` before you commit.
