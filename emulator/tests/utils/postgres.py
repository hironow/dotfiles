import os

import asyncpg

from tests.utils.helpers import run_manifest


def conn_params() -> dict:
    manifest = run_manifest()
    if manifest:
        if manifest.get("services", {}).get(
            "emulator/postgres"
        ) != "postgres-18" or "postgres-18" not in manifest.get(
            "selected_containers", []
        ):
            raise RuntimeError("Manifest must select emulator/postgres")
        record = manifest.get("postgres_connection", {})
        if (
            not isinstance(record, dict)
            or record.get("host") != "127.0.0.1"
            or type(record.get("port")) is not int
            or not 1 <= record["port"] <= 65535
            or record["port"] != manifest.get("host_ports", {}).get("5433")
            or any(
                not isinstance(record.get(key), str)
                or not record[key]
                or "$" in record[key]
                for key in ("user", "password", "database")
            )
        ):
            raise RuntimeError("Invalid complete PostgreSQL manifest connection record")
        for variable, field in (
            ("POSTGRES_HOST", "host"),
            ("POSTGRES_PORT", "port"),
            ("POSTGRES_USER", "user"),
            ("POSTGRES_PASSWORD", "password"),
            ("POSTGRES_DB", "database"),
        ):
            value = os.environ.get(variable)
            equivalents = {str(record[field])}
            if field == "host":
                equivalents.add("localhost")
            elif field == "port":
                equivalents.add("5433")
            if value is not None and value not in equivalents:
                raise RuntimeError(
                    f"Conflicting {variable}; remove inherited configuration"
                )
        return {
            key: record[key] for key in ("host", "port", "user", "password", "database")
        }
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = int(os.environ.get("POSTGRES_PORT", "5433"))
    user = os.environ.get("POSTGRES_USER", "postgres")
    password = os.environ.get("POSTGRES_PASSWORD", "password")
    database = os.environ.get("POSTGRES_DB", "postgres")
    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "database": database,
    }


async def connect() -> asyncpg.Connection:
    return await asyncpg.connect(**conn_params())


async def ensure_generated_table(conn: asyncpg.Connection, table: str) -> str:
    """Create a table with a generated column.

    Tries VIRTUAL first; falls back to STORED if VIRTUAL is unsupported.
    Returns the attgenerated flag: 'v' (virtual) or 's' (stored).
    """
    await conn.execute(f"DROP TABLE IF EXISTS {table};")
    ddl_virtual = (
        f"CREATE TABLE {table} (x int, y int GENERATED ALWAYS AS (x*2) VIRTUAL);"
    )
    ddl_stored = (
        f"CREATE TABLE {table} (x int, y int GENERATED ALWAYS AS (x*2) STORED);"
    )
    try:
        await conn.execute(ddl_virtual)
    except Exception:
        await conn.execute(ddl_stored)

    # Determine generated kind
    row = await conn.fetchrow(
        """
        SELECT a.attgenerated::text AS attgenerated
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = 'y'
        WHERE n.nspname = current_schema() AND c.relname = $1
        """,
        table,
    )
    raw = row["attgenerated"] if row else None
    if raw is None:
        return ""
    if isinstance(raw, (bytes, bytearray)):
        try:
            return raw.decode()
        except Exception:
            return str(raw)
    return str(raw)
