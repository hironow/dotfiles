# Qdrant CLI

A command-line interface for interacting with Qdrant vector database.

## Features

- Interactive REPL interface
- Support for all Qdrant REST API operations
- Pretty-printed JSON output
- Table formatting for collections list
- Multi-line query support

## Usage

### Using Docker Compose

```bash
# Start Qdrant and the CLI
docker compose --profile cli up qdrant-cli

# Or run the CLI separately after Qdrant is running
docker compose run --rm qdrant-cli
```

### Environment Variables

- `QDRANT_HOST`: Qdrant server hostname (default: localhost)
- `QDRANT_PORT`: Qdrant server port (default: 6333)

### Commands

#### Special Commands

- `\h` or `\help`: Show help message
- `\q` or `\quit`: Exit the CLI
- `\c` or `\clear`: Clear the screen
- `\l` or `\collections`: List all collections
- `\i` or `\info`: Show cluster information

#### API Commands

All API commands follow the format: `METHOD /path [body];`

Examples:

```bash
# Create a collection
PUT /collections/test_collection {"vectors": {"size": 4, "distance": "Cosine"}};

# List all collections
GET /collections;

# Get collection info
GET /collections/test_collection;

# Add points to collection
PUT /collections/test_collection/points {
  "points": [
    {"id": 1, "vector": [0.1, 0.2, 0.3, 0.4]},
    {"id": 2, "vector": [0.2, 0.3, 0.4, 0.5]}
  ]
};

# Search for similar vectors
POST /collections/test_collection/points/search {
  "vector": [0.1, 0.2, 0.3, 0.4],
  "limit": 5
};

# Delete a collection
DELETE /collections/test_collection;
```

### Multi-line Queries

For complex JSON bodies, you can use multi-line mode by not ending the line with a semicolon:

```text
qdrant> PUT /collections/my_collection {
...   "vectors": {
...     "size": 768,
...     "distance": "Cosine"
...   }
... };
```
