# Elasticsearch CLI

An interactive command-line interface for Elasticsearch that provides a user-friendly way to execute REST API commands, manage indices, and perform search operations.

## Features

- **Interactive REST API Shell**: Execute Elasticsearch API commands with a familiar command-line interface
- **Multi-line Support**: Write complex JSON requests across multiple lines (commands execute when you type `;`)
- **Table Formatting**: Index information displayed in clean, formatted tables with borders
- **Query Timing**: Each command shows execution time
- **Full API Support**: Direct access to all Elasticsearch REST APIs
- **Command History**: Navigate through previous commands using arrow keys
- **Auto-completion**: Basic command completion support

## Usage

### Using Docker Compose (Recommended)

From the parent directory:

```bash
# Run the CLI tool
docker compose --profile cli run --rm elasticsearch-cli
```

### Building and Running Locally

```bash
# Build the CLI
go build -o elasticsearch-cli

# Run the CLI
./elasticsearch-cli
```

### Configuration

The CLI is configured through environment variables:

- `ELASTICSEARCH_HOST`: Elasticsearch host (default: `localhost`)
- `ELASTICSEARCH_PORT`: Elasticsearch port (default: `9200`)
- `ELASTICSEARCH_USER`: Username for authentication (optional)
- `ELASTICSEARCH_PASSWORD`: Password for authentication (optional)

For Docker Compose usage, these are automatically configured to connect to the Elasticsearch emulator.

## Commands

### Special Commands

- `help` or `\h` - Show available commands and API examples
- `indices` or `\l` - List all indices in the cluster with detailed information
- `info` or `\i` - Show cluster information including version and cluster name
- `\health` - Show cluster health status (green/yellow/red)
- `clear` or `\c` - Clear the screen
- `exit` or `\q` - Exit the CLI

### API Commands

All API commands follow the format: `METHOD /path {json_body};`

Commands must end with a semicolon (`;`) to execute. Multi-line input is supported for complex JSON bodies.

#### Basic Examples

```json
# Create an index
PUT /products {"settings": {"number_of_shards": 1, "number_of_replicas": 0}};

# Index a document
POST /products/_doc {"name": "Laptop", "price": 999.99, "category": "electronics"};

# Search for documents
GET /products/_search {"query": {"match": {"name": "laptop"}}};

# Get specific document
GET /products/_doc/1;

# Update a document
POST /products/_update/1 {"doc": {"price": 899.99}};

# Delete an index
DELETE /products;
```

#### Advanced Examples

```json
# Complex search with aggregations
POST /products/_search {
  "query": {
    "bool": {
      "must": [
        {"match": {"category": "electronics"}},
        {"range": {"price": {"gte": 500, "lte": 1500}}}
      ]
    }
  },
  "aggs": {
    "price_stats": {
      "stats": {"field": "price"}
    }
  }
};

# Bulk operations
POST /_bulk {
  {"index": {"_index": "products", "_id": "1"}}
  {"name": "Phone", "price": 599.99}
  {"index": {"_index": "products", "_id": "2"}}
  {"name": "Tablet", "price": 399.99}
};

# Create index with mapping
PUT /users {
  "mappings": {
    "properties": {
      "email": {"type": "keyword"},
      "name": {"type": "text"},
      "age": {"type": "integer"},
      "joined_date": {"type": "date"}
    }
  }
};

# Reindex data
POST /_reindex {
  "source": {"index": "old_products"},
  "dest": {"index": "new_products"}
};
```

## Example Session

```json
elasticsearch> PUT /products {"settings": {"number_of_shards": 1}};
{
  "acknowledged": true,
  "shards_acknowledged": true,
  "index": "products"
}

Time: 125ms

elasticsearch> POST /products/_doc {"name": "Laptop", "price": 999.99};
{
  "_index": "products",
  "_id": "AbC123xyz",
  "_version": 1,
  "result": "created"
}

Time: 45ms

elasticsearch> \indices
┌────────┬────────┬──────────┬────────────┬────────────┬────────────┐
│ Health │ Status │ Index    │ Docs Count │ Store Size │ Pri Shards │
├────────┼────────┼──────────┼────────────┼────────────┼────────────┤
│ green  │ open   │ products │ 1          │ 4.1kb      │ 1          │
└────────┴────────┴──────────┴────────────┴────────────┴────────────┘

elasticsearch> exit
Bye!
```

## Build Requirements

- Go 1.20 or higher
- Access to an Elasticsearch instance

## Dependencies

The CLI uses the following Go packages:

- `github.com/elastic/go-elasticsearch/v8` - Official Elasticsearch Go client
- `github.com/olekukonko/tablewriter` - Table formatting
- Standard library packages for HTTP, JSON, and terminal interaction

## Troubleshooting

### Connection Issues

If you cannot connect to Elasticsearch:

1. Verify Elasticsearch is running:

   ```bash
   curl -X GET "localhost:9200/_cluster/health"
   ```

2. Check environment variables are set correctly
3. Ensure no firewall is blocking the connection
4. For Docker users, verify you're on the correct network

### Authentication Errors

If using a secured Elasticsearch instance:

- Set `ELASTICSEARCH_USER` and `ELASTICSEARCH_PASSWORD` environment variables
- Ensure the user has necessary permissions

### JSON Parsing Errors

- Ensure JSON is valid (use double quotes for strings)
- Check for trailing commas
- Use proper escaping for special characters

## License

This tool is part of the emulator suite and follows the same license as the parent project.
