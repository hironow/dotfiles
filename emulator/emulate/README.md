# emulate: SaaS API emulators

Local, stateful stand-ins for SaaS APIs (GitHub, Google, Slack, Apple,
Microsoft, Stripe, Clerk, Okta, Resend) from
[vercel-labs/emulate](https://github.com/vercel-labs/emulate). They complement
the datastore emulators in [`../README.md`](../README.md).

```sh
just emu-api                                # all nine services, foreground
just emu-api services=github,google,slack   # a subset
just emu-api-stop                           # stop a backgrounded run
```

The recipe runs a pinned `emulate` with `bunx` on the host, not in Docker
([ADR 0055](../../docs/adr/0055-run-emulate-with-bunx.md)). It binds to
`127.0.0.1`. Ports start at 4100 and follow the `--service` order (base +
index), so the default set uses 4100-4108. If the published CLI rejects a
service, drop it from `services=`.

[`../../docs/portless-urls.md`](../../docs/portless-urls.md) lists the port
of each service and its `https://<service>.localhost` alias. If you change the
service set or order, update those ports too.

[`emulate.config.yaml`](emulate.config.yaml) holds the `tokens:` and the seed
data for each service. If a newer `emulate` changes the schema, generate a
fresh starter with `bunx emulate@<version> init`.
