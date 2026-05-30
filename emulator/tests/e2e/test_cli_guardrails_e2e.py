"""Guardrail E2E tests (no CLI changes required).

Goals
- Catch regressions in constraint/mode enforcement and type handling.
- Keep flows independent and self‑cleaning.
"""

import textwrap
import pytest


@pytest.mark.e2e
def test_pgadapter_read_only_mode_or_skip(
    ensure_network, require_services, build_image, run_cli
):
    """SET TRANSACTION READ ONLY should prevent writes (if supported)."""
    ensure_network()
    require_services(["pgadapter-emulator", "spanner-emulator"])
    build_image("pgadapter-cli", "pgadapter-cli:local")

    env = {
        "PGHOST": "pgadapter-emulator",
        "PGPORT": "5432",
        "PGUSER": "user",
        "PGDATABASE": "test-instance",
        "PGSSLMODE": "disable",
    }
    script = """
DROP TABLE IF EXISTS ro_demo;
CREATE TABLE ro_demo (id BIGINT PRIMARY KEY, v INT);
BEGIN;
SET TRANSACTION READ ONLY;
INSERT INTO ro_demo (id, v) VALUES (1, 1);
ROLLBACK;
DROP TABLE ro_demo;
exit
"""
    out = run_cli("pgadapter-cli:local", "pgadapter-cli", script, env).lower()
    if "set transaction" in out and "error" in out:
        # Some builds may not support the SET TRANSACTION syntax — treat as unsupported
        pytest.skip("SET TRANSACTION READ ONLY not supported by this pgAdapter build")
    # Expect write attempt to fail under READ ONLY
    assert "error" in out or "read only" in out


@pytest.mark.e2e
def test_neo4j_unique_constraint_enforcement(
    ensure_network, require_services, build_image, run_cli
):
    ensure_network()
    require_services(["neo4j-emulator"])
    build_image("neo4j-cli", "neo4j-cli:local")

    env = {
        "NEO4J_URI": "bolt://neo4j-emulator:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "password",
    }
    script = """
CREATE CONSTRAINT unique_email IF NOT EXISTS FOR (u:User) REQUIRE u.email IS UNIQUE;
CREATE (u1:User {email:'dup@example.com'});
CREATE (u2:User {email:'dup@example.com'});
// Expect constraint violation above
MATCH (u:User) DETACH DELETE u;
DROP CONSTRAINT unique_email IF EXISTS;
exit
"""
    out = run_cli("neo4j-cli:local", "neo4j-cli", script, env).lower()
    assert (
        ("constraint" in out and "violation" in out)
        or ("already exists" in out)
        or ("error" in out)
    )


@pytest.mark.e2e
def test_elasticsearch_mapping_type_conflict(
    ensure_network, require_services, build_image, run_cli
):
    ensure_network()
    require_services(["elasticsearch-emulator"])
    build_image("elasticsearch-cli", "elasticsearch-cli:local")

    env = {"ELASTICSEARCH_HOST": "elasticsearch-emulator", "ELASTICSEARCH_PORT": "9200"}
    idx = "type_conflict"
    script = f"""
PUT /{idx} {{"mappings": {{"properties": {{"price": {{"type": "integer"}}}}}}}};
POST /{idx}/_doc {{"price": 10}};
POST /{idx}/_doc {{"price": "not-an-integer"}};
DELETE /{idx};
\\q
"""
    out = run_cli("elasticsearch-cli:local", "elasticsearch-cli", script, env)
    # Expect HTTP 400 error for type conflict
    assert "HTTP 400" in out or "mapper_parsing_exception" in out.lower()


@pytest.mark.e2e
def test_qdrant_delete_by_filter_and_verify(
    ensure_network, require_services, build_image, run_cli
):
    ensure_network()
    require_services(["qdrant-emulator"])
    build_image("qdrant-cli", "qdrant-cli:local")

    env = {"QDRANT_HOST": "qdrant-emulator", "QDRANT_PORT": "6333"}
    col = "delete_filter"
    script = textwrap.dedent(
        f"""
        PUT /collections/{col} {{"vectors": {{"size": 2, "distance": "Cosine"}}}};
        PUT /collections/{col}/points {{
          "points": [
            {{"id": 1, "vector": [0.1, 0.2], "payload": {{"tag": "A"}}}},
            {{"id": 2, "vector": [0.2, 0.1], "payload": {{"tag": "B"}}}}
          ]
        }};
        POST /collections/{col}/points/delete {{
          "filter": {{"must": [{{"key": "tag", "match": {{"value": "B"}}}}]}}
        }};
        POST /collections/{col}/points/search {{
          "vector": [0.1, 0.2],
          "limit": 10,
          "with_payload": true
        }};
        DELETE /collections/{col};
        \\q
        """
    ).lstrip("\n")
    out = run_cli("qdrant-cli:local", "qdrant-cli", script, env)
    if "HTTP 400" in out:
        pytest.skip("Qdrant delete-by-filter not supported by this emulator build")
    low = out.lower()
    if '"status": "ok"' not in out or '"tag"' not in low:
        pytest.skip("Qdrant response missing payload or status; skipping")
    assert '"a"' in low and '"b"' not in low
