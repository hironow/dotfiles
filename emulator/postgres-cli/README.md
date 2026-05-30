# PostgreSQL 18 CLI

Interactive CLI for the local PostgreSQL 18 service in this emulator stack. Provides multiline input, basic commands, and tabular output similar to the other CLIs.

## Run (Docker Compose profile)

```bash
docker compose --profile cli run --rm postgres-cli
```

## Connection (defaults)

- `PGHOST=postgres` (container name)
- `PGPORT=5432`
- `PGUSER=postgres`
- `PGDATABASE=postgres`
- `PGPASSWORD=password`

For host access (outside Docker), the Postgres service is mapped to `localhost:${POSTGRES_PORT:-5433}`.

## Commands

- `help` or `\h` — Show help
- `tables` or `\dt` — List user tables
- `clear` or `\c` — Clear screen
- `exit` or `\q` — Exit
