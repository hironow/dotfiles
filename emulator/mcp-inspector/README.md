# MCP Inspector

Model Context Protocol (MCP) debugging and inspection tool.

## Overview

MCP Inspector is an interactive developer tool for testing and debugging MCP
servers. It provides a web-based UI for connecting to MCP servers, inspecting
resources, testing prompts, and executing tools.

## Ports

| Port | Service | Description |
|------|---------|-------------|
| 6274 | Client UI | Web interface for inspection |
| 6277 | Proxy Server | Internal proxy (not exposed externally) |

## Usage

Start with Docker Compose:

```bash
docker compose up -d mcp-inspector
```

Access the UI:

```bash
open http://localhost:6274
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_INSPECTOR_PORT` | 6274 | Host port for client UI |
| `MCP_INSPECTOR_REPO` | GitHub URL | Git repository to clone |
| `MCP_INSPECTOR_REF` | main | Git ref (branch/tag/commit) |

## Connecting to Host Services

When connecting to MCP servers running on your host machine from within the
Inspector UI, use `host.docker.internal` instead of `localhost`.

Example: `http://host.docker.internal:3000`

## Features

- Connect to MCP servers via STDIO, SSE, or Streamable HTTP
- Browse and test resources
- Execute prompts with parameters
- Call tools and inspect results
- View server capabilities and metadata

## Source

<https://github.com/modelcontextprotocol/inspector>
