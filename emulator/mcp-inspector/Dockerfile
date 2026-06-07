# syntax=docker/dockerfile:1.22

ARG MCP_INSPECTOR_REPO=https://github.com/modelcontextprotocol/inspector.git
ARG MCP_INSPECTOR_REF=main

# Stage 0: fetch source
FROM alpine/git AS source
ARG MCP_INSPECTOR_REPO
ARG MCP_INSPECTOR_REF
WORKDIR /src
RUN git clone --depth 1 --branch "${MCP_INSPECTOR_REF}" "${MCP_INSPECTOR_REPO}" repo

# Stage 1: build
FROM node:26-alpine AS builder
WORKDIR /app
COPY --from=source /src/repo/package*.json ./
COPY --from=source /src/repo/client/package*.json ./client/
COPY --from=source /src/repo/server/package*.json ./server/
COPY --from=source /src/repo/cli/package*.json ./cli/
RUN npm ci --ignore-scripts
COPY --from=source /src/repo/ ./
RUN npm run build

# Stage 2: runtime
FROM node:26-slim
WORKDIR /app

# curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/package*.json ./
COPY --from=builder /app/client/package*.json ./client/
COPY --from=builder /app/server/package*.json ./server/
COPY --from=builder /app/cli/package*.json ./cli/
RUN npm ci --omit=dev --ignore-scripts
COPY --from=builder /app/client/dist ./client/dist
COPY --from=builder /app/client/bin ./client/bin
COPY --from=builder /app/server/build ./server/build
COPY --from=builder /app/cli/build ./cli/build

ENV CLIENT_PORT=6274
ENV SERVER_PORT=6277
ENV HOST=0.0.0.0
EXPOSE 6274 6277

CMD ["npm", "start"]
