FROM docker.io/library/golang:1.27.3-alpine AS builder
WORKDIR /src
COPY go.mod main.go ./
RUN CGO_ENABLED=0 GOTOOLCHAIN=local GOPROXY=off GOSUMDB=off \
    go build -mod=readonly -trimpath -o /tcp-healthcheck .

FROM gcr.io/cloud-spanner-emulator/emulator:1.5.57 AS spanner
COPY --from=builder /tcp-healthcheck /usr/local/bin/tcp-healthcheck

FROM gcr.io/cloud-spanner-pg-adapter/pgadapter AS pgadapter
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && command -v pg_isready \
    && pg_isready --version \
    && rm -rf /var/lib/apt/lists/*
