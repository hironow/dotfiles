# Portless URLs

[portless](https://github.com/vercel-labs/portless) gives each local HTTP UI a
stable URL, `https://<name>.localhost`. Run `portless` directly; dotfiles has no
wrapper recipes. mise installs it (`npm:portless` in `config/mise/config.toml`).

## Set up once

Run `portless trust` to add the portless CA to the system trust store, so HTTPS
works without warnings. To start the proxy at login, run
`portless service install`.

## Register the aliases

Start the proxy with `portless proxy start`, then register each local UI. This
list is the one place that names the aliases:

```sh
# emulator (emulator/compose.yaml)
portless alias firebase 4000 --force        # Firebase Emulator Suite UI
portless alias neo4j 7474 --force           # Neo4j Browser (HTTP)
portless alias a2a-inspector 8081 --force   # A2A Inspector UI
portless alias mcp-inspector 6274 --force   # MCP Inspector UI
portless alias mlflow 5252 --force          # MLflow UI
portless alias qdrant 6333 --force          # Qdrant REST and dashboard
portless alias elasticsearch 9200 --force   # Elasticsearch REST
# telemetry (telemetry/compose.yaml)
portless alias grafana 3010 --force         # Grafana
portless alias prometheus 9091 --force      # Prometheus
portless alias tempo 3200 --force           # Tempo HTTP API
portless alias loki 3100 --force            # Loki HTTP API
# emulate API emulators (`just emu-api`, base port 4100)
portless alias github 4100 --force
portless alias google 4101 --force
portless alias slack 4102 --force
portless alias apple 4103 --force
portless alias microsoft 4104 --force
portless alias stripe 4105 --force
portless alias clerk 4106 --force
portless alias okta 4107 --force
portless alias resend 4108 --force
```

Then start the stack behind the aliases (`just tel-up`, `just emu-start`, or
`just emu-api`). Check the routes with `portless list`, or print one alias URL with
`portless get <name> --no-worktree` (without the flag, a git worktree adds a
branch prefix to the name). In an app, read the URL from an env var named after the
alias, for example `FIREBASE_URL=https://firebase.localhost`.

When a port changes, change its line here. The emulate ports are the base port
plus the position of each service in `just emu-api`'s `--service` order
(github, google, slack, apple, microsoft, stripe, clerk, okta, resend; checked
on emulate@0.8.0). If you change that order, change these ports too. The
emulate aliases answer only while `just emu-api` runs.

## Not aliased

portless proxies HTTP(S) only, not raw TCP. These wire protocols stay on their
`127.0.0.1` ports: postgres 5433, pgadapter 55432, neo4j bolt 7687, bigtable
gRPC 8086, spanner gRPC 9010, qdrant gRPC 6334, and elasticsearch transport
9300.

## Remove the aliases

Run `portless alias --remove <name>` for each alias, then `portless proxy stop`.
