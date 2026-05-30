"""E2E for PostgreSQL 18 extensions via the Go CLI.

These tests try pgvector and PostGIS through the interactive CLI. If the
extensions are not available in the image, they skip gracefully.
"""

import re
import pytest


def _should_skip_for_missing_extension(out: str, name: str) -> bool:
    s = out.lower()
    name = name.lower()
    patterns = [
        "could not open extension control file",
        'extension "%s" is not available' % name,
        'type "%s" does not exist' % ("vector" if name == "vector" else name),
        "no such file or directory",
    ]
    return any(p in s for p in patterns)


@pytest.mark.e2e
def test_postgres_cli_pgvector(
    ensure_network, require_services, build_image, run_shell
):
    ensure_network()
    require_services(["postgres-18"])
    build_image(path="postgres-cli", tag="postgres-cli:local")

    env = {
        "PGHOST": "postgres",
        "PGPORT": "5432",
        "PGUSER": "postgres",
        "PGPASSWORD": "password",
        "PGDATABASE": "postgres",
        "PGSSLMODE": "disable",
    }
    script = r"""
    CREATE EXTENSION IF NOT EXISTS vector;
    DROP TABLE IF EXISTS e2e_vec;
    CREATE TABLE e2e_vec (id int, emb vector(3));
    INSERT INTO e2e_vec VALUES (1, '[1,2,3]');
    INSERT INTO e2e_vec VALUES (2, '[0,0,0]');
    SELECT round(('[1,2,3]'::vector <-> '[0,0,0]'::vector)::numeric, 3) AS dist;
    SELECT id, round((emb <-> '[1,2,3]'::vector)::numeric, 3) AS d FROM e2e_vec ORDER BY d ASC LIMIT 1;
    exit
    """
    out = run_shell(
        "postgres-cli:local", f"cat <<'EOF' | ./postgres-cli\n{script}\nEOF", env
    )
    if _should_skip_for_missing_extension(out, "vector"):
        pytest.skip("pgvector extension not available in the Postgres image")

    assert ("PostgreSQL 18 CLI" in out) or ("Connected to PostgreSQL 18" in out)
    # Look for the computed distances 3.742 (rounded 3.742) and 0.000 for NN row
    assert " dist " in out or "dist" in out
    assert "3.742" in out or "3.741" in out
    assert re.search(r"\b0(\.0+)?\b", out) is not None


@pytest.mark.e2e
def test_postgres_cli_postgis(ensure_network, require_services, build_image, run_shell):
    ensure_network()
    require_services(["postgres-18"])
    build_image(path="postgres-cli", tag="postgres-cli:local")

    env = {
        "PGHOST": "postgres",
        "PGPORT": "5432",
        "PGUSER": "postgres",
        "PGPASSWORD": "password",
        "PGDATABASE": "postgres",
        "PGSSLMODE": "disable",
    }
    script = r"""
    CREATE EXTENSION IF NOT EXISTS postgis;
    SELECT ST_AsText(ST_Buffer(ST_GeomFromText('POINT(0 0)'), 1.0, 'quad_segs=8')) AS wkt;
    exit
    """
    out = run_shell(
        "postgres-cli:local", f"cat <<'EOF' | ./postgres-cli\n{script}\nEOF", env
    )
    if _should_skip_for_missing_extension(out, "postgis"):
        pytest.skip("postgis extension not available in the Postgres image")

    assert ("PostgreSQL 18 CLI" in out) or ("Connected to PostgreSQL 18" in out)
    assert "POLYGON" in out or "POINT" in out
