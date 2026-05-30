# Bigtable CLI

Interactive CLI for Google Cloud Bigtable Emulator.

Features

- Help/REPL with simple commands
- List tables, create/delete table, read/write cells, scan rows
- Works against emulator via `BIGTABLE_EMULATOR_HOST`

Usage (Docker Compose)

```bash
# From repo root
docker compose --profile cli run --rm bigtable-cli
```

Environment

- `BIGTABLE_EMULATOR_HOST` (e.g., `bigtable-emulator:8086` or `localhost:8086`)
- `BIGTABLE_PROJECT` (default: `test-project`)
- `BIGTABLE_INSTANCE` (default: `test-instance`)

Commands

- `help` or `\h` — Show help
- `tables` or `\lt` — List tables
- `create <table> [cf]` — Create table and column family (default `cf1`)
- `delete <table>` — Delete table
- `put <table> <row> <family:col> <value>` — Write one cell
- `get <table> <row> [family:col]` — Read row or a specific cell
- `scan <table> [limit]` — Scan first N rows (default 10)
- `exit` or `\q` — Quit

Notes

- Emulator must be running. Ensure instance exists (e.g., `test-instance`).
- If instance/table do not exist, create them using `create`.
