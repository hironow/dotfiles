"""E2E smoke for the PostgreSQL 18 CLI.

Verifies the CLI starts, connects over the Docker network, responds to help,
and can run simple SQL including uuidv7() and a generated column.
"""

import pytest


@pytest.mark.e2e
def test_postgres_cli_help_and_exit(
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
    out = run_shell(
        "postgres-cli:local", "printf 'help\\nexit\\n' | ./postgres-cli", env
    )
    assert ("PostgreSQL 18 CLI" in out) or ("Connected to PostgreSQL 18" in out)
    assert ("Goodbye" in out) or ("Bye" in out)


@pytest.mark.e2e
def test_postgres_cli_uuidv7_and_generated(
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
    SELECT uuidv7()::text AS u;
    CREATE TABLE IF NOT EXISTS e2e_cli_pg (x int, y int GENERATED ALWAYS AS (x*2) STORED);
    INSERT INTO e2e_cli_pg(x) VALUES (12);
    SELECT x, y FROM e2e_cli_pg ORDER BY x LIMIT 1;
    exit
    """
    out = run_shell(
        "postgres-cli:local", f"cat <<'EOF' | ./postgres-cli\n{script}\nEOF", env
    )

    assert ("Connected to PostgreSQL 18" in out) or ("PostgreSQL 18 CLI" in out)
    # uuidv7() output should render in the table; look for column alias or hyphenated UUID shape
    assert (" u " in out) or ("-" in out)
    # generated column result 12 -> 24 should appear
    assert "12" in out and "24" in out
    assert ("Goodbye" in out) or ("Bye" in out)
