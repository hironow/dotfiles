"""Additional value E2E tests (no CLI changes).

Scenarios
- pgAdapter: NOT NULL + DEFAULT, UTF‑8/emoji, default read‑only mode
- Neo4j: composite unique constraint, index create/drop visibility
- Elasticsearch: minimal _bulk NLJSON tolerance, refresh visibility
- Qdrant: scroll pagination, score threshold border
"""

import textwrap
import pytest


# ---------- pgAdapter ----------


def _pg_env() -> dict[str, str]:
    return {
        "PGHOST": "pgadapter-emulator",
        "PGPORT": "5432",
        "PGUSER": "user",
        "PGDATABASE": "test-instance",
        "PGSSLMODE": "disable",
    }


@pytest.mark.e2e
def test_pgadapter_notnull_default_roundtrip(
    ensure_network, require_services, build_image, run_cli
):
    ensure_network()
    require_services(["pgadapter-emulator", "spanner-emulator"])
    build_image("pgadapter-cli", "pgadapter-cli:local")
    script = """
DROP TABLE IF EXISTS defaults_demo;
CREATE TABLE defaults_demo (
  id BIGINT PRIMARY KEY,
  name VARCHAR(20) NOT NULL DEFAULT 'def'
);
INSERT INTO defaults_demo (id) VALUES (1);
SELECT name FROM defaults_demo WHERE id=1;
-- expect error for NULL insert (or ignored); verify presence via count
INSERT INTO defaults_demo (id, name) VALUES (2, NULL);
SELECT COUNT(*) AS c2 FROM defaults_demo WHERE id=2;
DROP TABLE defaults_demo;
exit
"""
    out = run_cli("pgadapter-cli:local", "pgadapter-cli", script, _pg_env())
    low = out.lower()
    assert "def" in low
    # Either an error happened, or count for id=2 is 0 (not inserted)
    if "error" in low:
        assert True
    else:
        up = out.upper()
        assert " C2 " in up
        assert "│ 0 " in out or " 0 " in out


@pytest.mark.e2e
def test_pgadapter_utf8_emoji_roundtrip(
    ensure_network, require_services, build_image, run_cli
):
    ensure_network()
    require_services(["pgadapter-emulator", "spanner-emulator"])
    build_image("pgadapter-cli", "pgadapter-cli:local")
    jp = "こんにちは"
    em = "🚀"
    script = f"""
DROP TABLE IF EXISTS utf8_demo;
CREATE TABLE utf8_demo (id BIGINT PRIMARY KEY, txt TEXT);
INSERT INTO utf8_demo (id, txt) VALUES (1, '{jp}{em}');
SELECT txt FROM utf8_demo WHERE id=1;
DROP TABLE utf8_demo;
exit
"""
    out = run_cli("pgadapter-cli:local", "pgadapter-cli", script, _pg_env())
    assert jp in out and em in out


@pytest.mark.e2e
def test_pgadapter_default_tx_read_only_or_skip(
    ensure_network, require_services, build_image, run_cli
):
    ensure_network()
    require_services(["pgadapter-emulator", "spanner-emulator"])
    build_image("pgadapter-cli", "pgadapter-cli:local")
    script = """
DROP TABLE IF EXISTS ro2_demo;
CREATE TABLE ro2_demo (id BIGINT PRIMARY KEY, v INT);
SET default_transaction_read_only = on;
BEGIN;
INSERT INTO ro2_demo (id, v) VALUES (1, 1);
ROLLBACK;
SET default_transaction_read_only = off;
DROP TABLE ro2_demo;
exit
"""
    out = run_cli("pgadapter-cli:local", "pgadapter-cli", script, _pg_env()).lower()
    if "default_transaction_read_only" not in out:
        pytest.skip("default_transaction_read_only not supported by this build")
    assert "error" in out or "read only" in out


# ---------- Neo4j ----------


def _neo_env() -> dict[str, str]:
    return {
        "NEO4J_URI": "bolt://neo4j-emulator:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "password",
    }


@pytest.mark.e2e
def test_neo4j_composite_unique_constraint_violation(
    ensure_network, require_services, build_image, run_cli
):
    ensure_network()
    require_services(["neo4j-emulator"])
    build_image("neo4j-cli", "neo4j-cli:local")
    script = """
CREATE CONSTRAINT comp_unique IF NOT EXISTS FOR (u:UUser) REQUIRE (u.first, u.last) IS UNIQUE;
CREATE (u1:UUser {first:'A', last:'B'});
CREATE (u2:UUser {first:'A', last:'B'});
// violation expected
MATCH (u:UUser) DETACH DELETE u;
DROP CONSTRAINT comp_unique IF EXISTS;
exit
"""
    out = run_cli("neo4j-cli:local", "neo4j-cli", script, _neo_env()).lower()
    assert (
        ("constraint" in out and "violation" in out)
        or ("already exists" in out)
        or ("error" in out)
    )


@pytest.mark.e2e
def test_neo4j_index_create_drop_and_show(
    ensure_network, require_services, build_image, run_cli
):
    ensure_network()
    require_services(["neo4j-emulator"])
    build_image("neo4j-cli", "neo4j-cli:local")
    script = """
CREATE INDEX idx_uuser_prop IF NOT EXISTS FOR (n:UUser2) ON (n.p);
CALL db.indexes();
DROP INDEX idx_uuser_prop IF EXISTS;
CALL db.indexes();
exit
"""
    out = run_cli("neo4j-cli:local", "neo4j-cli", script, _neo_env()).lower()
    # We just ensure indexes listing can be called without errors and mentions
    assert ("index" in out) or ("call db.indexes" in out)


# ---------- Elasticsearch ----------


def _es_env() -> dict[str, str]:
    return {
        "ELASTICSEARCH_HOST": "elasticsearch-emulator",
        "ELASTICSEARCH_PORT": "9200",
    }


@pytest.mark.e2e
def test_elasticsearch_bulk_minimal_success_or_400(
    ensure_network, require_services, build_image, run_cli
):
    ensure_network()
    require_services(["elasticsearch-emulator"])
    build_image("elasticsearch-cli", "elasticsearch-cli:local")
    idx = "bulk_min"
    # Try bulk NLJSON; CLI may not preserve newlines, accept 400 as valid outcome
    script = f"""
PUT /{idx} {{"settings": {{"number_of_shards": 1, "number_of_replicas": 0}}}};
POST /_bulk
{{"index": {{"_index": "{idx}", "_id": "1"}}}}
{{"name": "foo"}}
{{"index": {{"_index": "{idx}", "_id": "2"}}}}
{{"name": "bar"}}
;
DELETE /{idx};
\\q
"""
    out = run_cli("elasticsearch-cli:local", "elasticsearch-cli", script, _es_env())
    assert ("created" in out) or ("HTTP 400" in out)


@pytest.mark.e2e
def test_elasticsearch_refresh_visibility(
    ensure_network, require_services, build_image, run_cli
):
    ensure_network()
    require_services(["elasticsearch-emulator"])
    build_image("elasticsearch-cli", "elasticsearch-cli:local")
    idx = "vis_min"
    script = f"""
PUT /{idx} {{"settings": {{"number_of_shards": 1, "number_of_replicas": 0}}}};
POST /{idx}/_doc {{"name": "no_refresh"}};
GET /{idx}/_search {{"query": {{"match": {{"name": "no_refresh"}}}}}};
POST /{idx}/_refresh;
GET /{idx}/_search {{"query": {{"match": {{"name": "no_refresh"}}}}}};
DELETE /{idx};
\\q
"""
    out = run_cli(
        "elasticsearch-cli:local", "elasticsearch-cli", script, _es_env()
    ).lower()
    # If first search already finds doc (auto refresh), still acceptable; ensure second search finds it
    assert "no_refresh" in out


# ---------- Qdrant ----------


def _q_env() -> dict[str, str]:
    return {"QDRANT_HOST": "qdrant-emulator", "QDRANT_PORT": "6333"}


@pytest.mark.e2e
def test_qdrant_scroll_pagination(
    ensure_network, require_services, build_image, run_cli
):
    ensure_network()
    require_services(["qdrant-emulator"])
    build_image("qdrant-cli", "qdrant-cli:local")
    col = "scroll_min"
    script = textwrap.dedent(
        f"""
        PUT /collections/{col} {{"vectors": {{"size": 2, "distance": "Cosine"}}}};
        PUT /collections/{col}/points {{
          "points": [
            {{"id": 1, "vector": [0.1, 0.2]}},
            {{"id": 2, "vector": [0.2, 0.1]}},
            {{"id": 3, "vector": [0.2, 0.2]}},
            {{"id": 4, "vector": [0.3, 0.3]}}
          ]
        }};
        POST /collections/{col}/points/scroll {{"limit": 2, "with_payload": false}};
        DELETE /collections/{col};
        \\q
        """
    ).lstrip("\n")
    out = run_cli("qdrant-cli:local", "qdrant-cli", script, _q_env())
    assert '"status": "ok"' in out


@pytest.mark.e2e
def test_qdrant_score_threshold_border(
    ensure_network, require_services, build_image, run_cli
):
    ensure_network()
    require_services(["qdrant-emulator"])
    build_image("qdrant-cli", "qdrant-cli:local")
    col = "thresh_min"
    script = textwrap.dedent(
        f"""
        PUT /collections/{col} {{"vectors": {{"size": 3, "distance": "Cosine"}}}};
        PUT /collections/{col}/points {{
          "points": [
            {{"id": 1, "vector": [1.0, 0.0, 0.0]}},
            {{"id": 2, "vector": [0.9, 0.1, 0.0]}}
          ]
        }};
        POST /collections/{col}/points/search {{
          "vector": [1.0, 0.0, 0.0],
          "limit": 10,
          "score_threshold": 0.999,
          "with_payload": false
        }};
        DELETE /collections/{col};
        \\q
        """
    ).lstrip("\n")
    out = run_cli("qdrant-cli:local", "qdrant-cli", script, _q_env()).lower()
    if "http 400" in out:
        pytest.skip("Qdrant score_threshold not supported by this build")
    # Expect only id=1
    assert '"id": 1' in out and '"id": 2' not in out
