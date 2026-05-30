"""CRUD happy‑path E2E for each CLI.

Purpose
- Exercise end‑to‑end create/read flows with minimal complexity.
- Keep scenarios fast and deterministic; include cleanup after assertions.

Scope
- pgAdapter: CREATE → INSERT → SELECT → DROP
- Neo4j: CREATE node → MATCH → DELETE
- Elasticsearch: CREATE index → INDEX doc → SEARCH → DELETE index
- Qdrant: CREATE collection → UPSERT point → SEARCH → DELETE collection
"""

import random
import string
import pytest


def _rand_suffix(n: int = 6) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


@pytest.mark.e2e
def test_pgadapter_cli_roundtrip(
    ensure_network, require_services, build_image, run_cli
):
    ensure_network()
    require_services(["pgadapter-emulator", "spanner-emulator"])
    build_image(path="pgadapter-cli", tag="pgadapter-cli:local")

    suffix = _rand_suffix()
    table = f"e2e_items_{suffix}"
    script = f"""
help
CREATE TABLE {table} (
  id BIGINT PRIMARY KEY,
  name VARCHAR(50)
);
INSERT INTO {table} (id, name) VALUES (1, 'one');
SELECT name FROM {table} WHERE id = 1;
tables
DROP TABLE {table};
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
    # SELECT の結果のみを検証。tables コマンドはスキーマ表示の差異で空になる場合がある。
    assert "one" in out


@pytest.mark.e2e
def test_neo4j_cli_roundtrip(ensure_network, require_services, build_image, run_cli):
    ensure_network()
    require_services(["neo4j-emulator"])
    build_image(path="neo4j-cli", tag="neo4j-cli:local")

    label = f"E2E_{_rand_suffix()}"
    script = f"""
help
CREATE (n:{label} {{name: 'Alice', age: 30}});
MATCH (n:{label}) RETURN n.name LIMIT 1;
labels
MATCH (n:{label}) DETACH DELETE n;
exit
"""

    env = {
        "NEO4J_URI": "bolt://neo4j-emulator:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "password",
    }
    out = run_cli("neo4j-cli:local", "neo4j-cli", script, env)
    assert "Alice" in out
    assert label in out


@pytest.mark.e2e
def test_elasticsearch_cli_roundtrip(
    ensure_network, require_services, build_image, run_cli
):
    ensure_network()
    require_services(["elasticsearch-emulator"])
    build_image(path="elasticsearch-cli", tag="elasticsearch-cli:local")

    index = f"e2e_products_{_rand_suffix()}"
    script = f"""
PUT /{index} {{"settings": {{"number_of_shards": 1, "number_of_replicas": 0}}}};
POST /{index}/_doc {{"name": "Laptop", "price": 999.99}};
GET /{index}/_search {{"query": {{"match": {{"name": "Laptop"}}}}}};
DELETE /{index};
\\i
\\q
"""

    env = {
        "ELASTICSEARCH_HOST": "elasticsearch-emulator",
        "ELASTICSEARCH_PORT": "9200",
    }
    out = run_cli("elasticsearch-cli:local", "elasticsearch-cli", script, env)
    assert "acknowledged" in out
    assert "created" in out or "hits" in out


@pytest.mark.e2e
def test_qdrant_cli_roundtrip(ensure_network, require_services, build_image, run_cli):
    ensure_network()
    require_services(["qdrant-emulator"])
    build_image(path="qdrant-cli", tag="qdrant-cli:local")

    collection = f"e2e_{_rand_suffix()}"
    script = f"""
PUT /collections/{collection} {{"vectors": {{"size": 4, "distance": "Cosine"}}}};
PUT /collections/{collection}/points {{"points": [{{"id": 1, "vector": [0.1, 0.2, 0.3, 0.4], "payload": {{"name": "A"}}}}]}};
POST /collections/{collection}/points/search {{"vector": [0.1, 0.2, 0.3, 0.4], "limit": 1}};
DELETE /collections/{collection};
\\collections
\\q
"""

    env = {
        "QDRANT_HOST": "qdrant-emulator",
        "QDRANT_PORT": "6333",
    }
    out = run_cli("qdrant-cli:local", "qdrant-cli", script, env)
    assert "status" in out and "ok" in out
    assert '"id": 1' in out or '"score"' in out
