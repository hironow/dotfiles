import os

import asyncpg


def conn_params() -> dict:
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
