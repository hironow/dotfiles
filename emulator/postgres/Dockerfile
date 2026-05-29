FROM postgres:18

USER root

RUN set -eux; \
    apt-get update; \
    # Install PostGIS and pgvector tied to the server major version
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        postgis \
        postgresql-$PG_MAJOR-postgis-3 \
        postgresql-$PG_MAJOR-postgis-3-scripts \
        postgresql-$PG_MAJOR-pgvector; \
    rm -rf /var/lib/apt/lists/*

# Optional: keep default postgres user
USER postgres

# Create extensions on first init
COPY docker-entrypoint-initdb.d/ /docker-entrypoint-initdb.d/

