import re

import pytest

from tests.utils.postgres import connect, ensure_generated_table


UUID_V7_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


@pytest.mark.asyncio
async def test_postgres18_version_major_is_18() -> None:
    conn = await connect()
    try:
        row = await conn.fetchrow("SHOW server_version;")
        version = row["server_version"] if row and "server_version" in row else row[0]
        major = int(str(version).split(".")[0])
        assert major == 18, f"expected major 18, got: {version}"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_uuidv7_exists_and_returns_valid_uuid() -> None:
    conn = await connect()
    try:
        row = await conn.fetchrow("SELECT uuidv7()::text AS u;")
        val = row["u"]
        assert isinstance(val, str)
        assert UUID_V7_RE.match(val), f"not a valid uuidv7: {val}"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_generated_column_virtual_or_stored_behaves() -> None:
    conn = await connect()
    try:
        kind = await ensure_generated_table(conn, "pg18_gen_test_py")
        assert kind in {"v", "s"}, f"unexpected attgenerated kind: {kind!r}"

        await conn.execute("INSERT INTO pg18_gen_test_py(x) VALUES (5);")
        row = await conn.fetchrow("SELECT x, y FROM pg18_gen_test_py LIMIT 1;")
        assert row["x"] == 5
        assert row["y"] == 10
    finally:
        await conn.close()
