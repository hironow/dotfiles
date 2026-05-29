# emulate — API/SaaS emulators

Local, stateful drop-in replacements for SaaS APIs via
[vercel-labs/emulate](https://github.com/vercel-labs/emulate), integrated as a
thin `npx` wrapper (not vendored — kept current via npm, pinned to a version).

This complements the datastore emulators in [`../`](../README.md) (postgres,
bigtable, spanner/pgadapter, neo4j, qdrant, elasticsearch, firebase) with
auth / commerce / messaging API emulators, useful for agent + `payments/`
(ACP, AP2) development.

## Run

```sh
just emu-api                 # full requested set on base port 4100 (foreground)
just emu-api services=github,google,slack,apple,microsoft   # confirmed-only subset
```

`just emu-api` runs `npx -y emulate@0.6.0 --service <list> --port 4100 --seed emulate.config.yaml`
on the host, binding to `127.0.0.1` from base port `4100` upward. Stop with Ctrl+C.

> Host `npx` (not a compose service) is used on purpose: `emulate` is a Node CLI
> and binding it directly on the host avoids container localhost-binding pitfalls.

## Services & ports

| Status (emulate@0.6.0) | Services |
|------------------------|----------|
| Confirmed in published CLI | `github` `google` `slack` `apple` `microsoft` (also `vercel` `aws`) |
| Requested, plugins shipped as deps but **unverified** in published CLI | `stripe` `clerk` `okta` `resend` |

Ports are assigned as `base + index` in emulate's internal registry order for the
**enabled subset**; per-service ports cannot be pinned. **Verify the actual
mapping from the first-run log**, then enable + correct the emulate entries in
[`../../config/portless-aliases.yaml`](../../config/portless-aliases.yaml) and
re-run `just portless-up` to expose them as `https://<service>.localhost`.

If `emu-api` errors on `stripe`/`clerk`/`okta`/`resend` (not exposed by the
published CLI), drop them from `services=`.

## Config

[`emulate.config.yaml`](./emulate.config.yaml) holds `tokens:` + per-service seed
data. Regenerate a canonical starter with `npx emulate@0.6.0 init` if the schema
changes in a newer version.
