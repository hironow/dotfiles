"""Smoke‑level E2E for each CLI (help/exit/info).

Fast connectivity checks to ensure the CLIs start, connect, and respond to
basic commands. Deeper scenarios live in test_cli_crud_e2e.py and
test_cli_features_e2e.py.
"""

import pytest


@pytest.mark.e2e
def test_pgadapter_cli_help_and_exit(
    docker_client,
    ensure_network,
    require_services,
    build_image,
    run_shell,
):
    ensure_network()
    require_services(
        [
            "pgadapter-emulator",
            "spanner-emulator",
        ]
    )
    build_image(path="pgadapter-cli", tag="pgadapter-cli:local")
    env = {
        "PGHOST": "pgadapter-emulator",
        "PGPORT": "5432",
        "PGUSER": "user",
        "PGDATABASE": "test-instance",
        "PGSSLMODE": "disable",
    }
    out = run_shell(
        "pgadapter-cli:local", "printf 'help\\nexit\\n' | ./pgadapter-cli", env
    )
    assert ("pgAdapter CLI" in out) or ("📚 Available Commands" in out)
    assert ("Goodbye" in out) or ("Bye" in out)


@pytest.mark.e2e
def test_neo4j_cli_help_and_exit(
    ensure_network, require_services, build_image, run_shell
):
    ensure_network()
    require_services(["neo4j-emulator"])
    build_image(path="neo4j-cli", tag="neo4j-cli:local")
    env = {
        "NEO4J_URI": "bolt://neo4j-emulator:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "password",
    }
    out = run_shell("neo4j-cli:local", "printf 'help\\nexit\\n' | ./neo4j-cli", env)
    assert ("Neo4j CLI" in out) or ("📚 Available Commands" in out)
    assert ("Goodbye" in out) or ("Bye" in out)


@pytest.mark.e2e
def test_elasticsearch_cli_info_and_quit(
    ensure_network, require_services, build_image, run_shell
):
    ensure_network()
    require_services(["elasticsearch-emulator"])
    build_image(path="elasticsearch-cli", tag="elasticsearch-cli:local")
    env = {
        "ELASTICSEARCH_HOST": "elasticsearch-emulator",
        "ELASTICSEARCH_PORT": "9200",
    }
    out = run_shell(
        "elasticsearch-cli:local",
        "printf '\\\\i\\n\\\\q\\n' | ./elasticsearch-cli",
        env,
    )
    assert ("Connected to Elasticsearch" in out) or ("Cluster Information" in out)


@pytest.mark.e2e
def test_qdrant_cli_info_and_quit(
    ensure_network, require_services, build_image, run_shell
):
    ensure_network()
    require_services(["qdrant-emulator"])
    build_image(path="qdrant-cli", tag="qdrant-cli:local")
    env = {
        "QDRANT_HOST": "qdrant-emulator",
        "QDRANT_PORT": "6333",
    }
    out = run_shell("qdrant-cli:local", "printf '\\\\i\\n\\\\q\\n' | ./qdrant-cli", env)
    assert ("Connected to Qdrant" in out) or ("Cluster Information" in out)


@pytest.mark.e2e
def test_bigtable_cli_help_and_exit(
    ensure_network, require_services, build_image, run_shell
):
    ensure_network()
    require_services(["bigtable-emulator"])
    build_image(path="bigtable-cli", tag="bigtable-cli:local")
    env = {
        "BIGTABLE_EMULATOR_HOST": "bigtable-emulator:8086",
        "BIGTABLE_PROJECT": "test-project",
        "BIGTABLE_INSTANCE": "test-instance",
    }
    out = run_shell(
        "bigtable-cli:local", "printf 'help\\nexit\\n' | ./bigtable-cli", env
    )
    assert ("Bigtable CLI" in out) or ("📚 Available Commands" in out)
    assert ("Goodbye" in out) or ("Bye" in out)
