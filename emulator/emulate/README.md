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
just emu-api services=github,google,slack   # custom subset
```

`just emu-api` runs `npx -y emulate@0.8.0 --service <list> --port 4100 --seed emulate.config.yaml`
on the host, binding to `127.0.0.1` from base port `4100` upward. Stop with Ctrl+C.

> Host `npx` (not a compose service) is used on purpose: `emulate` is a Node CLI
> and binding it directly on the host avoids container localhost-binding pitfalls.

## Services & ports

All requested services run on `emulate@0.8.0` (verified). Ports are deterministic:
`base + index` in the `--service` order used by `just emu-api`, so the default set
maps as:

| Port | Service | | Port | Service |
|------|---------|-|------|---------|
| 4100 | github    | | 4105 | stripe |
| 4101 | google    | | 4106 | clerk  |
| 4102 | slack     | | 4107 | okta   |
| 4103 | apple     | | 4108 | resend |
| 4104 | microsoft | |      |        |

These ports are pre-registered in
[`../../config/portless-aliases.yaml`](../../config/portless-aliases.yaml) — run
`just portless-up` to expose them as `https://<service>.localhost`. If you change
the `services=` set/order, update those alias ports to match.

## Config

[`emulate.config.yaml`](./emulate.config.yaml) holds `tokens:` + per-service seed
data. Regenerate a canonical starter with `npx emulate@0.8.0 init` if the schema
changes in a newer version.
