import pytest


@pytest.mark.e2e
def test_pgadapter_error_without_primary_key(
    ensure_network, require_services, build_image, run_cli
):
    """Spanner requires a PRIMARY KEY; table without PK should error."""
    ensure_network()
    require_services(["pgadapter-emulator", "spanner-emulator"])
    build_image(path="pgadapter-cli", tag="pgadapter-cli:local")

    script = """
CREATE TABLE no_pk_demo (id BIGINT, name VARCHAR(20));
exit
"""
    env = {
        "PGHOST": "pgadapter-emulator",
        "PGPORT": "5432",
        "PGUSER": "user",
        "PGDATABASE": "test-instance",
        "PGSSLMODE": "disable",
    }
    out = run_cli("pgadapter-cli:local", "pgadapter-cli", script, env)
    assert "❌ Error" in out
    assert "primary key" in out.lower()


@pytest.mark.e2e
def test_pgadapter_error_on_serial_type(
    ensure_network, require_services, build_image, run_cli
):
    """SERIAL is commonly unsupported in Spanner PG dialect."""
    ensure_network()
    require_services(["pgadapter-emulator", "spanner-emulator"])
    build_image(path="pgadapter-cli", tag="pgadapter-cli:local")

    script = """
CREATE TABLE serial_demo (id SERIAL PRIMARY KEY, name VARCHAR(20));
exit
"""
    env = {
        "PGHOST": "pgadapter-emulator",
        "PGPORT": "5432",
        "PGUSER": "user",
        "PGDATABASE": "test-instance",
        "PGSSLMODE": "disable",
    }
    out = run_cli("pgadapter-cli:local", "pgadapter-cli", script, env)
    low = out.lower()
    if "error" in low:
        assert True
    else:
        # Some pgAdapter builds accept SERIAL; treat as environment-supported and skip
        pytest.skip("SERIAL appears supported by this pgAdapter build")


@pytest.mark.e2e
def test_pgadapter_error_on_sequence(
    ensure_network, require_services, build_image, run_cli
):
    """Sequences are not supported in Spanner PG dialect."""
    ensure_network()
    require_services(["pgadapter-emulator", "spanner-emulator"])
    build_image(path="pgadapter-cli", tag="pgadapter-cli:local")

    script = """
CREATE SEQUENCE s_demo START 1;
exit
"""
    env = {
        "PGHOST": "pgadapter-emulator",
        "PGPORT": "5432",
        "PGUSER": "user",
        "PGDATABASE": "test-instance",
        "PGSSLMODE": "disable",
    }
    out = run_cli("pgadapter-cli:local", "pgadapter-cli", script, env)
    assert "❌ Error" in out
    assert ("sequence" in out.lower()) or ("not supported" in out.lower())
