"""Bigtable CLI CRUD E2E.

Flow
- init instance/cluster (idempotent)
- create table
- put cell
- get cell
- list tables
- delete table
"""

import pytest


def _rand(n: int = 6) -> str:
    import random as _r
    import string as _s

    return "".join(_r.choices(_s.ascii_lowercase + _s.digits, k=n))


@pytest.mark.e2e
def test_bigtable_cli_roundtrip(ensure_network, require_services, build_image, run_cli):
    ensure_network()
    require_services(["bigtable-emulator"])
    build_image(path="bigtable-cli", tag="bigtable-cli:local")

    table = f"e2e_{_rand()}"
    script = f"""
help
init
create {table} cf1
put {table} r1 cf1:name Alice
get {table} r1 cf1:name
tables
delete {table}
exit
"""

    env = {
        "BIGTABLE_EMULATOR_HOST": "bigtable-emulator:8086",
        "BIGTABLE_PROJECT": "test-project",
        "BIGTABLE_INSTANCE": "test-instance",
    }
    out = run_cli("bigtable-cli:local", "bigtable-cli", script, env)
    low = out.lower()
    assert "bigtable cli" in low or "available commands" in low
    assert "alice" in low
    assert table in out
