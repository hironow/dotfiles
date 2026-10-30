# syntax=docker/dockerfile:1.22

ARG A2A_INSPECTOR_REPO=https://github.com/a2aproject/a2a-inspector.git
# v0.2.0, the first release of the Go rewrite (a2aproject/a2a-inspector#221):
# one static binary with the UI embedded. A commit, not a branch, so an
# upstream layout change cannot break the build unannounced. Any commit, tag or
# branch works as an override; keep compose.yaml in step.
ARG A2A_INSPECTOR_REF=275f52360168f49d359eaf390cc8ffe848cc291f

# The stages below repeat upstream's own Dockerfile at that ref, so the base
# images stay pinned here and under Dependabot. Differences: the UI builds on
# Node 26 (the current LTS, as in this repo's image) and the binary on Go 1.27
# (this repo's Go minimum); upstream uses 24 and 1.26.

# Stage 0: fetch source once and reuse from later stages
FROM alpine/git AS source
ARG A2A_INSPECTOR_REPO
ARG A2A_INSPECTOR_REF
WORKDIR /src
# init + fetch instead of `clone --branch`: --branch takes no commit SHA
RUN git init -q repo && \
    git -C repo remote add origin "${A2A_INSPECTOR_REPO}" && \
    git -C repo fetch --depth 1 origin "${A2A_INSPECTOR_REF}" && \
    git -C repo -c advice.detachedHead=false checkout -q FETCH_HEAD

# Stage 1: build the UI
FROM node:26-slim AS ui
WORKDIR /src/ui
COPY --from=source /src/repo/ui/package.json /src/repo/ui/package-lock.json ./
RUN npm ci
COPY --from=source /src/repo/ui/ ./
RUN npm run build

# Stage 2: build the binary, with the UI from stage 1 embedded
FROM golang:1.27 AS go
WORKDIR /src
COPY --from=source /src/repo/go.mod /src/repo/go.sum ./
RUN go mod download
COPY --from=source /src/repo/main.go ./
COPY --from=source /src/repo/inspector/ inspector/
COPY --from=source /src/repo/internal/ internal/
COPY --from=source /src/repo/ui/embed.go ui/
COPY --from=ui /src/ui/dist ui/dist
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /a2a-inspector .

# Stage 3: run it. Distroless has no shell and no curl, so compose.yaml has no
# in-container healthcheck; scripts/wait-for-services.sh checks the UI from
# the host. The UI at / needs no token (only the API does), so a plain GET works.
FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=go /a2a-inspector /a2a-inspector
EXPOSE 8080
ENTRYPOINT ["/a2a-inspector", "--host", "0.0.0.0", "--port", "8080", "--no-open"]
