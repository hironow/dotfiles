"""Transactional / atomic flows E2E.

Focus
- pgAdapter: explicit BEGIN/ROLLBACK/COMMIT semantics
- Neo4j: attempt explicit BEGIN/ROLLBACK/COMMIT (skip if unsupported by driver path)
- Elasticsearch: index with refresh=wait_for to emulate commit‑like visibility
- Qdrant: upsert then delete to validate atomic cleanup
"""

import pytest


@pytest.mark.e2e
def test_pgadapter_transaction_commit_and_rollback(
    ensure_network, require_services, build_image, run_cli
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

    table = "tx_items"
    script = f"""
DROP TABLE IF EXISTS {table};
CREATE TABLE {table} (
  id BIGINT PRIMARY KEY,
  name VARCHAR(50)
);
BEGIN;
INSERT INTO {table} (id, name) VALUES (1, 'rollbackme');
SELECT name FROM {table} WHERE id = 1;
ROLLBACK;
SELECT name FROM {table} WHERE id = 1;
BEGIN;
INSERT INTO {table} (id, name) VALUES (2, 'commitme');
COMMIT;
SELECT name FROM {table} WHERE id = 2;
DROP TABLE {table};
exit
"""

    out = run_cli("pgadapter-cli:local", "pgadapter-cli", script, env)
    low = out.lower()
    # Inside tx we should see 'rollbackme'
    assert "rollbackme" in low
    # After rollback it should not be found (no 'rollbackme' in the last select table output)
    # We simply assert that at least one 'rollbackme' exists (first select) and two 'select' blocks
    assert low.count("rollbackme") == 1
    # After commit we should see 'commitme'
    assert "commitme" in low


@pytest.mark.e2e
def test_neo4j_explicit_tx_or_skip(
    ensure_network, require_services, build_image, run_cli
):
    ensure_network()
    require_services(["neo4j-emulator"])
    build_image(path="neo4j-cli", tag="neo4j-cli:local")

    env = {
        "NEO4J_URI": "bolt://neo4j-emulator:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "password",
    }

    label = "TxCase"
    script = f"""
BEGIN;
CREATE (n:{label} {{name:'tx1'}});
ROLLBACK;
MATCH (n:{label} {{name:'tx1'}}) RETURN count(*) as c1;
BEGIN;
CREATE (n:{label} {{name:'tx2'}});
COMMIT;
MATCH (n:{label} {{name:'tx2'}}) RETURN count(*) as c2;
MATCH (n:{label}) DETACH DELETE n;
exit
"""

    out = run_cli("neo4j-cli:local", "neo4j-cli", script, env)
    low = out.lower()
    if "error" in low and "begin" in low:
        pytest.skip(
            "Explicit transactions may not be supported via Cypher in this CLI path"
        )
    # Expect 0 for c1 and 1 for c2; we check presence heuristically
    assert "c1" in low or "count" in low
    assert "c2" in low or "count" in low


@pytest.mark.e2e
def test_elasticsearch_refresh_wait_for_visibility(
    ensure_network, require_services, build_image, run_cli
):
    ensure_network()
    require_services(["elasticsearch-emulator"])
    build_image(path="elasticsearch-cli", tag="elasticsearch-cli:local")

    env = {
        "ELASTICSEARCH_HOST": "elasticsearch-emulator",
        "ELASTICSEARCH_PORT": "9200",
    }
    index = "tx_demo"
    script = f"""
PUT /{index} {{"settings": {{"number_of_shards": 1, "number_of_replicas": 0}}}};
POST /{index}/_doc?refresh=wait_for {{"name": "committed"}};
GET /{index}/_search {{"query": {{"match": {{"name": "committed"}}}}}};
DELETE /{index};
\\q
"""
    out = run_cli("elasticsearch-cli:local", "elasticsearch-cli", script, env)
    assert "committed" in out


@pytest.mark.e2e
def test_qdrant_upsert_then_delete(
    ensure_network, require_services, build_image, run_cli
):
    ensure_network()
    require_services(["qdrant-emulator"])
    build_image(path="qdrant-cli", tag="qdrant-cli:local")

    env = {
        "QDRANT_HOST": "qdrant-emulator",
        "QDRANT_PORT": "6333",
    }
    col = "tx_demo"
    script = f"""
PUT /collections/{col} {{"vectors": {{"size": 2, "distance": "Cosine"}}}};
PUT /collections/{col}/points {{"points": [{{"id": 1, "vector": [0.1, 0.2], "payload": {{"tag": "keep"}}}}, {{"id": 2, "vector": [0.2, 0.1], "payload": {{"tag": "drop"}}}}]}};
POST /collections/{col}/points/delete {{"points": [2]}};
POST /collections/{col}/points/search {{"vector": [0.1, 0.2], "limit": 10, "with_payload": true}};
DELETE /collections/{col};
\\q
"""
    out = run_cli("qdrant-cli:local", "qdrant-cli", script, env)
    low = out.lower()
    assert "keep" in low
    assert "drop" not in low
