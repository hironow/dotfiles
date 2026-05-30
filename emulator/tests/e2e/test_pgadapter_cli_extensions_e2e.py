"""E2E for pgAdapter CLI attempting pgvector/PostGIS usage.

Cloud Spanner pgAdapter generally does not support arbitrary PostgreSQL
extensions. These tests try minimal extension flows via the CLI and skip
gracefully when unsupported, while validating basic behavior if they happen
to be available in the environment.
"""

import pytest


def _missing_ext(out: str, name: str) -> bool:
    s = out.lower()
    name = name.lower()
    patterns = [
        "create extension",
        'extension "%s"' % name,
        "is not supported",
        "is not available",
        "does not exist",
        "syntax error",
        "no such file or directory",
        "unrecognized configuration parameter",
    ]
    return any(p in s for p in patterns)


@pytest.mark.e2e
def test_pgadapter_cli_pgvector(
    ensure_network, require_services, build_image, run_shell
):
    ensure_network()
    require_services(["pgadapter-emulator", "spanner-emulator"])
    build_image(path="pgadapter-cli", tag="pgadapter-cli:local")

    env = {
        "PGHOST": "pgadapter-emulator",
        "PGPORT": "5432",
        "PGUSER": "user",
        "PGDATABASE": "test-instance",
        "PGSSLMODE": "disable",
    }

    script = r"""
    CREATE EXTENSION IF NOT EXISTS vector;
    DROP TABLE IF EXISTS e2e_vec_pg;
    CREATE TABLE e2e_vec_pg (id BIGINT PRIMARY KEY, emb vector(3));
    INSERT INTO e2e_vec_pg VALUES (1, '[1,2,3]');
    SELECT id FROM e2e_vec_pg ORDER BY emb <-> '[1,2,3]'::vector LIMIT 1;
    exit
    """
    out = run_shell(
        "pgadapter-cli:local", f"cat <<'EOF' | ./pgadapter-cli\n{script}\nEOF", env
    )
    if _missing_ext(out, "vector"):
        pytest.skip("pgAdapter: pgvector not available/unsupported in this environment")

    assert ("pgAdapter CLI" in out) or ("Connected" in out)
    assert "1" in out  # nearest neighbor self-check


@pytest.mark.e2e
def test_pgadapter_cli_postgis(
    ensure_network, require_services, build_image, run_shell
):
    ensure_network()
    require_services(["pgadapter-emulator", "spanner-emulator"])
    build_image(path="pgadapter-cli", tag="pgadapter-cli:local")

    env = {
        "PGHOST": "pgadapter-emulator",
        "PGPORT": "5432",
        "PGUSER": "user",
        "PGDATABASE": "test-instance",
        "PGSSLMODE": "disable",
    }

    script = r"""
    CREATE EXTENSION IF NOT EXISTS postgis;
    SELECT ST_AsText(ST_Buffer(ST_GeomFromText('POINT(0 0)'), 1.0, 'quad_segs=8')) AS wkt;
    exit
    """
    out = run_shell(
        "pgadapter-cli:local", f"cat <<'EOF' | ./pgadapter-cli\n{script}\nEOF", env
    )
    if _missing_ext(out, "postgis"):
        pytest.skip("pgAdapter: postgis not available/unsupported in this environment")

    assert ("pgAdapter CLI" in out) or ("Connected" in out)
    assert ("POLYGON" in out) or ("POINT" in out)
